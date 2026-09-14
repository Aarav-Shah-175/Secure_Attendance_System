import os
import json
import base64
import logging
from dataclasses import dataclass
from typing import Protocol, Optional, List
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

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
    Legacy/Mock verifier for challenge-response liveness protocol.
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


class ProductionFaceLivenessVerifier:
    """
    Production face verification and anti-spoofing pipeline.
    Combines MTCNN landmark detection & rotation normalization,
    close-distance anomaly protection, ensemble MiniFASNet (scale 2.7 & 4.0),
    multi-frame temporal smoothing, and InceptionResNetV1 face matching.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.65,
        spoof_threshold: float = 0.60,
        max_replay_thresh: float = 0.30
    ):
        self.similarity_threshold = similarity_threshold
        self.spoof_threshold = spoof_threshold
        self.max_replay_thresh = max_replay_thresh
        self.verifier_name = "ProductionFaceLivenessVerifier (MiniFASNet + FaceNet)"
        self.verifier_version = "2.0.0"

    def _decode_frame(self, b64_str: str):
        import cv2
        import numpy as np

        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]

        raw_bytes = base64.b64decode(b64_str)
        np_arr = np.frombuffer(raw_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return frame

    def _parse_frames(self, image_payload: str) -> List:
        """
        Parses base64 string or JSON payload containing a burst of frames.
        """
        import numpy as np
        frames = []
        if not image_payload or not isinstance(image_payload, str):
            return frames

        # Try parsing JSON array or dict with 'frames' / 'images'
        trimmed = image_payload.strip()
        if trimmed.startswith("{") or trimmed.startswith("["):
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, list):
                    raw_list = parsed
                elif isinstance(parsed, dict):
                    raw_list = parsed.get("frames") or parsed.get("images") or [parsed.get("image")]
                else:
                    raw_list = []

                for item in raw_list:
                    if isinstance(item, str):
                        f = self._decode_frame(item)
                        if f is not None and f.size > 0:
                            frames.append(f)
                return frames
            except Exception as e:
                logger.warning("Failed to parse JSON frames payload: %s", e)

        # Single base64 image string fallback
        try:
            f = self._decode_frame(trimmed)
            if f is not None and f.size > 0:
                frames.append(f)
        except Exception as e:
            logger.warning("Failed to decode single base64 image: %s", e)

        return frames

    def _get_stored_embedding(self, student_id: str):
        """Retrieves stored 512-dim embedding for student."""
        import numpy as np
        from core.student_service import FaceEmbeddingCache

        # 1. Memory cache
        cached = FaceEmbeddingCache.get(student_id)
        if cached is not None:
            return cached

        # 2. File storage
        embedding_path = os.path.join("embeddings", f"{student_id}.npy")
        if os.path.exists(embedding_path):
            try:
                emb = np.load(embedding_path)
                return emb
            except Exception as e:
                logger.error("Error loading embedding file for %s: %s", student_id, e)

        # 3. Database fallback
        try:
            from core.models import StudentProfile, User
            from core.crypto_utils import aes_decrypt
            user = User.objects.filter(id=student_id).first()
            if user:
                profile = StudentProfile.objects.filter(user=user).first()
                if profile and profile.encrypted_face_embedding:
                    decrypted_bytes = aes_decrypt(bytes(profile.encrypted_face_embedding))
                    emb = np.frombuffer(decrypted_bytes, dtype=np.float32)
                    if emb.size == 512:
                        return emb
        except Exception as e:
            logger.error("Error retrieving database embedding for %s: %s", student_id, e)

        return None

    def verify(
        self,
        *,
        attempt_id: str,
        student_id: str,
        image_payload: str,
        challenge: str
    ) -> LivenessDecision:
        if not image_payload:
            return LivenessDecision(
                passed=False,
                score=None,
                reason="invalid_image_payload",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        # Size limit (max 20MB payload)
        if len(image_payload) > 20_000_000:
            return LivenessDecision(
                passed=False,
                score=None,
                reason="payload_too_large",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        stored_embedding = self._get_stored_embedding(student_id)
        if stored_embedding is None:
            return LivenessDecision(
                passed=False,
                score=None,
                reason="face_not_registered",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        frames = self._parse_frames(image_payload)
        if not frames:
            return LivenessDecision(
                passed=False,
                score=None,
                reason="image_decode_failed",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        try:
            from core.face_system.engine import FaceSystemEngine

            engine = FaceSystemEngine.get_instance()
            result = engine.overall_verification(
                frames=frames,
                registered_embedding=stored_embedding,
                similarity_threshold=self.similarity_threshold,
                spoof_threshold=self.spoof_threshold,
                max_replay_thresh=self.max_replay_thresh
            )

            passed = bool(result["passed"])
            reason = result["reason"]
            score = float(result.get("real_score", 0.0))

            return LivenessDecision(
                passed=passed,
                score=score,
                reason=reason,
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )

        except Exception as e:
            logger.error("Production liveness verification error: %s", str(e), exc_info=True)
            return LivenessDecision(
                passed=False,
                score=None,
                reason="verifier_processing_error",
                verifier_version=self.verifier_version,
                verifier_name=self.verifier_name,
            )


# Alias FaceNetLivenessVerifier to ProductionFaceLivenessVerifier for backwards compatibility
FaceNetLivenessVerifier = ProductionFaceLivenessVerifier


def get_liveness_verifier() -> LivenessVerifier:
    """
    Factory function returning configured liveness verifier instance.
    Defaults to ProductionFaceLivenessVerifier.
    """
    verifier_type = getattr(settings, "LIVENESS_VERIFIER_TYPE", "new_face_system")
    if verifier_type in ("new_face_system", "production", "facenet"):
        return ProductionFaceLivenessVerifier()
    if verifier_type == "mediapipe":
        return MediaPipeLivenessVerifier()
    if verifier_type == "unconfigured":
        return UnconfiguredLivenessVerifier()
    return ProductionFaceLivenessVerifier()
