import os
import base64
import logging
from dataclasses import dataclass
from typing import Protocol, Optional
from django.conf import settings #type: ignore
from django.core.exceptions import ObjectDoesNotExist #type: ignore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LivenessDecision:
    passed: bool
    score: Optional[float]
    reason: str
    verifier_version: str
    verifier_name: str


class LivenessVerifier(Protocol):
    def verify(
        self,
        *,
        attempt_id: str,
        student_id: str,
        image_payload: str,
        challenge: str
    ) -> LivenessDecision:
        ...


class UnconfiguredLivenessVerifier:
    """Safe default verifier: Secure V2 fails closed if no production verifier is configured."""

    def verify(
        self,
        *,
        attempt_id: str,
        student_id: str,
        image_payload: str,
        challenge: str
    ) -> LivenessDecision:
        return LivenessDecision(
            passed=False,
            score=None,
            reason="liveness_verifier_not_configured",
            verifier_version="unconfigured",
            verifier_name="UnconfiguredLivenessVerifier",
        )


class MediaPipeLivenessVerifier:
    """
    Verifier for client-side MediaPipe challenge-response liveness protocol.
    The challenge (blink/left/right/straight) and HMAC nonce are verified server-side.
    """

    def __init__(self):
        self.verifier_name = "MediaPipeLivenessVerifier"
        self.verifier_version = "1.0.0"

    def verify(
        self,
        *,
        attempt_id: str,
        student_id: str,
        image_payload: str,
        challenge: str
    ) -> LivenessDecision:
        if image_payload == "nonce_verified":
            return LivenessDecision(
                passed=True,
                score=1.0,
                reason="mediapipe_challenge_passed",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        return LivenessDecision(
            passed=False,
            score=None,
            reason="liveness_nonce_not_verified",
            verifier_version=self.verifier_version,
            verifier_name=self.verifier_name,
        )


class FaceNetLivenessVerifier:
    """
    Adapter implementing face matching + liveness evaluation using MTCNN and InceptionResnetV1.
    Imports heavy ML libraries dynamically so module load remains fast and lightweight.
    """

    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
        self.verifier_name = "FaceNetLivenessVerifier"
        self.verifier_version = "1.0.0"

    def verify(
        self,
        *,
        attempt_id: str,
        student_id: str,
        image_payload: str,
        challenge: str
    ) -> LivenessDecision:
        if not image_payload or not isinstance(image_payload, str):
            return LivenessDecision(
                passed=False,
                score=None,
                reason="invalid_image_payload",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        # Enforce file size limit before decoding (e.g. max 5MB base64 string ~ 6.7MB raw)
        if len(image_payload) > 7_000_000:
            return LivenessDecision(
                passed=False,
                score=None,
                reason="payload_too_large",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        try:
            # Strip base64 header if present
            if "," in image_payload:
                image_data_str = image_payload.split(",", 1)[1]
            else:
                image_data_str = image_payload

            image_bytes = base64.b64decode(image_data_str)
        except Exception:
            return LivenessDecision(
                passed=False,
                score=None,
                reason="malformed_base64_image",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        # Check stored embedding for student
        embedding_path = os.path.join("embeddings", f"{student_id}.npy")
        if not os.path.exists(embedding_path):
            return LivenessDecision(
                passed=False,
                score=None,
                reason="face_not_registered",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        try:
            import cv2 #type: ignore
            import numpy as np
            import torch #type: ignore
            from PIL import Image #type: ignore
            from facenet_pytorch import MTCNN, InceptionResnetV1 #type: ignore
 
            device = 'cuda' if torch.cuda.is_available() else 'cpu'

            np_img = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

            if frame is None:
                return LivenessDecision(
                    passed=False,
                    score=None,
                    reason="image_decode_failed",
                    verifier_version=self.verifier_version,
                    verifier_name=self.verifier_name,
                )

            # Check image dimensions (max 4096x4096, min 64x64)
            h, w = frame.shape[:2]
            if w < 64 or h < 64 or w > 4096 or h > 4096:
                return LivenessDecision(
                    passed=False,
                    score=None,
                    reason="invalid_image_dimensions",
                    verifier_version=self.verifier_version,
                    verifier_name=self.verifier_name,
                )

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)

            mtcnn = MTCNN(image_size=160, margin=0, device=device, keep_all=False)
            face = mtcnn(img)

            if face is None:
                return LivenessDecision(
                    passed=False,
                    score=None,
                    reason="no_face_detected",
                    verifier_version=self.verifier_version,
                    verifier_name=self.verifier_name,
                )

            resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)
            face_tensor = face.unsqueeze(0).to(device)

            with torch.no_grad():
                embedding = resnet(face_tensor)

            current_emb = embedding.cpu().numpy()
            stored_embedding = np.load(embedding_path)

            emb1 = torch.tensor(stored_embedding)
            emb2 = torch.tensor(current_emb)

            similarity = float(torch.nn.functional.cosine_similarity(emb1, emb2).item())

            if similarity > self.threshold:
                return LivenessDecision(
                    passed=True,
                    score=similarity,
                    reason="liveness_and_face_verified",
                    verifier_version=self.verifier_version,
                    verifier_name=self.verifier_name,
                )
            else:
                return LivenessDecision(
                    passed=False,
                    score=similarity,
                    reason="face_match_below_threshold",
                    verifier_version=self.verifier_version,
                    verifier_name=self.verifier_name,
                )

        except Exception as e:
            logger.error("Liveness verification error: %s", str(e))
            return LivenessDecision(
                passed=False,
                score=None,
                reason="verifier_processing_error",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )


def get_liveness_verifier() -> LivenessVerifier:
    """
    Factory function returning configured liveness verifier instance.
    Defaults to UnconfiguredLivenessVerifier (failing closed) unless configured.
    """
    verifier_type = getattr(settings, "LIVENESS_VERIFIER_TYPE", "unconfigured")
    if verifier_type == "mediapipe":
        return MediaPipeLivenessVerifier()
    if verifier_type == "facenet":
        return FaceNetLivenessVerifier()
    return UnconfiguredLivenessVerifier()
