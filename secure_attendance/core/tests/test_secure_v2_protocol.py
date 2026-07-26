import json
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.db import IntegrityError
from core.models import (
    User,
    AttendanceSession,
    AttendanceAttempt,
    AttendanceRecord,
    PasskeyCredential,
    AttendanceAuditEntry,
    AttemptStatus,
    LivenessStatus,
    SecurityMode
)
from core.session_service import create_attendance_session
from core.secure_presence_v2_service import (
    start_attendance_attempt,
    process_liveness_verification,
    issue_signing_challenge_v2,
    submit_attendance_v2
)
from core.presence_service import record_presence_heartbeat
from core.liveness import LivenessDecision, UnconfiguredLivenessVerifier
from core.audit_service import verify_v2_session_integrity


class SecureV2ProtocolTests(TestCase):

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
            credential_id="test_credential_id_12345",
            public_key="test_public_key_b64",
            sign_counter=1
        )
        self.session = create_attendance_session(
            professor=self.professor,
            course_code="CS201",
            gateway_ip="192.168.1.1",
            subnet_range="192.168.1.0/24",
            security_mode=SecurityMode.SECURE_PRESENCE_V2
        )

    def test_global_feature_flag_disabled(self):
        with override_settings(SECURE_PRESENCE_V2_ENABLED=False):
            success, attempt, msg = start_attendance_attempt(
                user=self.student,
                session_id=str(self.session.id),
                client_ip="192.168.1.50"
            )
            self.assertFalse(success)
            self.assertIn("globally disabled", msg)

    def test_network_subnet_restriction(self):
        # Allowed IP in subnet
        success, attempt, msg = start_attendance_attempt(
            user=self.student,
            session_id=str(self.session.id),
            client_ip="192.168.1.100"
        )
        self.assertTrue(success)
        self.assertEqual(attempt.status, AttemptStatus.LIVENESS_PENDING)

        # Disallowed IP outside subnet
        success_bad, attempt_bad, msg_bad = start_attendance_attempt(
            user=self.student,
            session_id=str(self.session.id),
            client_ip="10.0.0.5"
        )
        self.assertFalse(success_bad)
        self.assertIn("authorized classroom network", msg_bad)

    def test_unconfigured_liveness_verifier_fails_closed(self):
        success, attempt, _ = start_attendance_attempt(
            user=self.student,
            session_id=str(self.session.id),
            client_ip="192.168.1.50"
        )
        self.assertTrue(success)

        # Default verifier is UnconfiguredLivenessVerifier
        success_live, verification, msg_live = process_liveness_verification(
            attempt_id=str(attempt.id),
            user=self.student,
            image_payload="data:image/jpeg;base64,AAAA"
        )
        self.assertFalse(success_live)
        self.assertEqual(verification.status, LivenessStatus.FAILED)
        self.assertEqual(verification.reason_code, "liveness_verifier_not_configured")

        # Attempt status set to REJECTED
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.REJECTED)

    def test_challenge_issuance_requires_liveness_success(self):
        success, attempt, _ = start_attendance_attempt(
            user=self.student,
            session_id=str(self.session.id),
            client_ip="192.168.1.50"
        )
        # Attempt is in LIVENESS_PENDING state
        success_chal, options, msg = issue_signing_challenge_v2(
            attempt_id=str(attempt.id),
            user=self.student
        )
        self.assertFalse(success_chal)
        self.assertIn("liveness verification first", msg)

    @patch("core.secure_presence_v2_service.get_liveness_verifier")
    @patch("core.secure_presence_v2_service.verify_passkey_authentication")
    def test_full_secure_v2_successful_lifecycle(self, mock_webauthn, mock_get_verifier):
        # Setup mock verifier
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = LivenessDecision(
            passed=True,
            score=0.95,
            reason="liveness_and_face_verified",
            verifier_version="test-1.0",
            verifier_name="MockVerifier"
        )
        mock_get_verifier.return_value = mock_verifier

        # Setup mock WebAuthn authentication
        mock_webauthn.return_value = (True, self.passkey, "Authentication successful")

        # Step 1: Start Attempt
        success, attempt, _ = start_attendance_attempt(
            user=self.student,
            session_id=str(self.session.id),
            client_ip="192.168.1.50"
        )
        self.assertTrue(success)

        # Step 2: Record Heartbeat
        record_presence_heartbeat(attempt, self.student, "192.168.1.50")

        # Step 3: Process Liveness
        success_live, verification, _ = process_liveness_verification(
            attempt_id=str(attempt.id),
            user=self.student,
            image_payload="data:image/jpeg;base64,validdata"
        )
        self.assertTrue(success_live)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.BIOMETRIC_VERIFIED)

        # Step 4: Issue Challenge
        success_chal, options, _ = issue_signing_challenge_v2(
            attempt_id=str(attempt.id),
            user=self.student
        )
        self.assertTrue(success_chal)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.CHALLENGE_ISSUED)

        # Step 5: Atomic Submit
        success_sub, msg_sub = submit_attendance_v2(
            user=self.student,
            attempt_id=str(attempt.id),
            credential_payload={"id": "test_cred"},
            client_ip="192.168.1.50"
        )
        self.assertTrue(success_sub)
        self.assertEqual(msg_sub, "Secure V2 attendance recorded successfully.")

        # Verify database record and audit entry created
        record = AttendanceRecord.objects.get(student=self.student, session=self.session)
        self.assertIsNotNone(record)
        audit_entry = AttendanceAuditEntry.objects.get(record=record)
        self.assertIsNotNone(audit_entry)

    @patch("core.secure_presence_v2_service.get_liveness_verifier")
    @patch("core.secure_presence_v2_service.verify_passkey_authentication")
    def test_audit_chain_tampering_detection(self, mock_webauthn, mock_get_verifier):
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = LivenessDecision(
            passed=True, score=0.9, reason="passed", verifier_version="1.0", verifier_name="Mock"
        )
        mock_get_verifier.return_value = mock_verifier
        mock_webauthn.return_value = (True, self.passkey, "Success")

        success, attempt, _ = start_attendance_attempt(self.student, str(self.session.id), "192.168.1.50")
        record_presence_heartbeat(attempt, self.student, "192.168.1.50")
        process_liveness_verification(str(attempt.id), self.student, "data:image/jpeg;base64,data")
        issue_signing_challenge_v2(str(attempt.id), self.student)
        submit_attendance_v2(self.student, str(attempt.id), {"id": "cred"}, "192.168.1.50")

        # Initial integrity check passes
        integrity_before = verify_v2_session_integrity(str(self.session.id))
        self.assertTrue(integrity_before["valid"])

        # Tamper with canonical report hash in database
        audit_entry = AttendanceAuditEntry.objects.filter(session=self.session).first()
        audit_entry.canonical_report_hash = "0" * 64
        audit_entry.save(update_fields=['canonical_report_hash'])

        # Integrity check detects tampering
        integrity_after = verify_v2_session_integrity(str(self.session.id))
        self.assertFalse(integrity_after["valid"])

    def test_rate_limiting_endpoint(self):
        self.client.login(email="student@university.edu", password="StudentPassword123!")
        
        # Endpoint with limit=5 per 60s
        for _ in range(5):
            res = self.client.post(
                reverse("start_attempt_v2"),
                data=json.dumps({"session_id": str(self.session.id)}),
                content_type="application/json",
                REMOTE_ADDR="192.168.1.50"
            )
        
        # 6th request should hit rate limit (status 429)
        over_res = self.client.post(
            reverse("start_attempt_v2"),
            data=json.dumps({"session_id": str(self.session.id)}),
            content_type="application/json",
            REMOTE_ADDR="192.168.1.50"
        )
        self.assertEqual(over_res.status_code, 429)


class SecureV2ConcurrencyTests(TransactionTestCase):

    def test_unique_constraint_concurrency_prevention(self):
        professor = User.objects.create_user(
            email="prof_conc@university.edu", password="Pass", role="professor"
        )
        student = User.objects.create_user(
            email="student_conc@university.edu", password="Pass", role="student"
        )
        session = AttendanceSession.objects.create(
            professor=professor,
            course_code="CS301",
            expiry=timezone.now() + timedelta(minutes=30),
            network_nonce="nonce",
            session_signature="sig",
            gateway_ip="192.168.1.1",
            subnet_range="192.168.1.0/24",
            active=True,
            security_mode=SecurityMode.SECURE_PRESENCE_V2
        )

        AttendanceRecord.objects.create(
            student=student,
            session=session,
            client_ip="192.168.1.50",
            record_hash="hash1",
            chained_hash="chain1"
        )

        # Attempt to insert second record for same student and session
        with self.assertRaises(IntegrityError):
            AttendanceRecord.objects.create(
                student=student,
                session=session,
                client_ip="192.168.1.50",
                record_hash="hash2",
                chained_hash="chain2"
            )
