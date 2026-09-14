import json
import base64
import numpy as np
import cv2
import torch
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import User, AttendanceSession, AttendanceAttempt, PasskeyCredential, AttemptStatus, LivenessStatus, SecurityMode
from core.session_service import create_attendance_session
from core.face_system.engine import FaceSystemEngine
from core.face_system.models import MiniFASNetV2, MiniFASNetV1SE, CropImage
from core.student_service import register_student_face_embedding, verify_student_face, FaceEmbeddingCache
from core.liveness import ProductionFaceLivenessVerifier, get_liveness_verifier
from core.secure_presence_v2_service import start_attendance_attempt, process_liveness_verification


def create_dummy_face_image_bgr(w=200, h=200):
    """Generates a synthetic image with a basic face-like structure for unit testing."""
    img = np.zeros((h, w, 3), dtype=np.uint8) + 120
    # Draw simple head ellipse
    cv2.ellipse(img, (w // 2, h // 2), (w // 4, h // 3), 0, 0, 360, (200, 180, 160), -1)
    # Eyes
    cv2.circle(img, (w // 2 - 25, h // 2 - 20), 8, (50, 50, 50), -1)
    cv2.circle(img, (w // 2 + 25, h // 2 - 20), 8, (50, 50, 50), -1)
    # Mouth
    cv2.ellipse(img, (w // 2, h // 2 + 30), (20, 8), 0, 0, 180, (50, 50, 150), 3)
    return img


def bgr_to_base64(img_bgr):
    _, buf = cv2.imencode('.jpg', img_bgr)
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode('utf-8')


@override_settings(ATTENDANCE_AGENT_DEV_BYPASS=True, LIVENESS_VERIFIER_TYPE="new_face_system")
class FaceSystemUnitTests(TestCase):

    def setUp(self):
        self.engine = FaceSystemEngine.get_instance()

    def test_singleton_engine_loaded(self):
        self.assertIsNotNone(self.engine.mtcnn)
        self.assertIsNotNone(self.engine.resnet)
        self.assertIsNotNone(self.engine.minifasnet_v2)
        self.assertIsNotNone(self.engine.minifasnet_v1se)

    def test_minifasnet_models_forward(self):
        # 80x80 crop input
        t_dummy = torch.randn(1, 3, 80, 80, device=self.engine.device)
        with torch.no_grad():
            out_v2 = self.engine.minifasnet_v2(t_dummy)
            out_v1se = self.engine.minifasnet_v1se(t_dummy)

        self.assertEqual(out_v2.shape, (1, 3))
        self.assertEqual(out_v1se.shape, (1, 3))

    def test_cropper_scale_expansion(self):
        cropper = CropImage()
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        bbox = [100, 100, 80, 80]
        crop_27 = cropper.crop(img, bbox, scale=2.7, out_w=80, out_h=80)
        crop_40 = cropper.crop(img, bbox, scale=4.0, out_w=80, out_h=80)

        self.assertEqual(crop_27.shape, (80, 80, 3))
        self.assertEqual(crop_40.shape, (80, 80, 3))

    def test_embedding_normalization(self):
        raw = np.array([3.0, 4.0, 0.0])
        norm = self.engine.normalize_embedding(raw)
        self.assertAlmostEqual(float(np.linalg.norm(norm)), 1.0, places=5)
        self.assertAlmostEqual(norm[0], 0.6, places=5)
        self.assertAlmostEqual(norm[1], 0.8, places=5)


@override_settings(ATTENDANCE_AGENT_DEV_BYPASS=True, LIVENESS_VERIFIER_TYPE="new_face_system")
class ProductionFaceLivenessVerifierTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.professor = User.objects.create_user(
            email="prof@university.edu",
            password="ProfPassword123!",
            role="professor"
        )
        self.student = User.objects.create_user(
            email="student@university.edu",
            password="StudentPassword123!",
            role="student"
        )
        self.passkey = PasskeyCredential.objects.create(
            student=self.student,
            credential_id="test_credential_id_face",
            public_key="test_public_key",
            sign_counter=1
        )
        self.session = create_attendance_session(
            professor=self.professor,
            course_code="CS301",
            security_mode=SecurityMode.SECURE_PRESENCE_V2
        )
        # Register synthetic 512-dim embedding for student
        self.dummy_emb = np.random.randn(512).astype(np.float32)
        register_student_face_embedding(self.student, self.dummy_emb)

    def test_unregistered_student_rejected(self):
        unregistered = User.objects.create_user(
            email="unregistered@university.edu",
            password="Password123!",
            role="student"
        )
        verifier = ProductionFaceLivenessVerifier()
        decision = verifier.verify(
            attempt_id="test_attempt",
            student_id=str(unregistered.id),
            image_payload="data:image/jpeg;base64,AAAA",
            challenge="challenge"
        )
        self.assertFalse(decision.passed)
        self.assertEqual(decision.reason, "face_not_registered")

    def test_invalid_image_payload_rejected(self):
        verifier = ProductionFaceLivenessVerifier()
        decision = verifier.verify(
            attempt_id="test_attempt",
            student_id=str(self.student.id),
            image_payload="invalid_garbage",
            challenge="challenge"
        )
        self.assertFalse(decision.passed)
        self.assertEqual(decision.reason, "image_decode_failed")

    @patch.object(FaceSystemEngine, "overall_verification")
    def test_face_match_and_liveness_success(self, mock_overall):
        mock_overall.return_value = {
            "passed": True,
            "reason": "face_and_liveness_verified",
            "liveness_passed": True,
            "liveness_label": "REAL (Genuine Face)",
            "real_score": 0.92,
            "face_matched": True,
            "similarity_score": 0.85
        }

        # Start attempt
        success, attempt, _ = start_attendance_attempt(
            user=self.student,
            session_id=str(self.session.id),
            client_ip="192.168.1.50"
        )
        self.assertTrue(success)

        # Process liveness with 7-frame payload
        dummy_b64 = bgr_to_base64(create_dummy_face_image_bgr())
        frames_payload = json.dumps({"attempt_id": str(attempt.id), "frames": [dummy_b64] * 7})

        success_live, verification, msg_live = process_liveness_verification(
            attempt_id=str(attempt.id),
            user=self.student,
            image_payload=frames_payload
        )

        self.assertTrue(success_live)
        self.assertEqual(verification.status, LivenessStatus.PASSED)
        self.assertEqual(verification.reason_code, "face_and_liveness_verified")

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.BIOMETRIC_VERIFIED)

    @patch.object(FaceSystemEngine, "overall_verification")
    def test_face_mismatch_rejected(self, mock_overall):
        mock_overall.return_value = {
            "passed": False,
            "reason": "face_match_below_threshold",
            "liveness_passed": True,
            "liveness_label": "REAL (Genuine Face)",
            "real_score": 0.88,
            "face_matched": False,
            "similarity_score": 0.32
        }

        success, attempt, _ = start_attendance_attempt(
            user=self.student,
            session_id=str(self.session.id),
            client_ip="192.168.1.50"
        )
        self.assertTrue(success)

        dummy_b64 = bgr_to_base64(create_dummy_face_image_bgr())
        frames_payload = json.dumps({"attempt_id": str(attempt.id), "frames": [dummy_b64] * 7})

        success_live, verification, msg_live = process_liveness_verification(
            attempt_id=str(attempt.id),
            user=self.student,
            image_payload=frames_payload
        )

        self.assertFalse(success_live)
        self.assertEqual(verification.status, LivenessStatus.FAILED)
        self.assertEqual(verification.reason_code, "face_match_below_threshold")

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.REJECTED)

    @patch.object(FaceSystemEngine, "overall_verification")
    def test_spoof_attack_rejected(self, mock_overall):
        mock_overall.return_value = {
            "passed": False,
            "reason": "spoof_detected_replay",
            "liveness_passed": False,
            "liveness_label": "SPOOF (Replay Attack)",
            "real_score": 0.15,
            "face_matched": True,
            "similarity_score": 0.78
        }

        success, attempt, _ = start_attendance_attempt(
            user=self.student,
            session_id=str(self.session.id),
            client_ip="192.168.1.50"
        )
        self.assertTrue(success)

        dummy_b64 = bgr_to_base64(create_dummy_face_image_bgr())
        frames_payload = json.dumps({"attempt_id": str(attempt.id), "frames": [dummy_b64] * 7})

        success_live, verification, msg_live = process_liveness_verification(
            attempt_id=str(attempt.id),
            user=self.student,
            image_payload=frames_payload
        )

        self.assertFalse(success_live)
        self.assertEqual(verification.status, LivenessStatus.FAILED)
        self.assertEqual(verification.reason_code, "spoof_detected_replay")

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.REJECTED)
