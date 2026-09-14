"""
Face & Anti-Spoofing Inference Engine.
Combines MTCNN face detection/alignment, InceptionResNetV1 face recognition,
and MiniFASNet ensemble passive anti-spoofing with multi-scale cropping,
landmark rotation normalization, and close-distance anomaly protection.
"""

import os
import logging
from typing import List, Tuple, Optional, Union, Dict, Any
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
import torch
import torch.nn.functional as F
from facenet_pytorch import MTCNN, InceptionResnetV1

from core.face_system.models import (
    MiniFASNetV2,
    MiniFASNetV1SE,
    CropImage,
    OpenCVFaceDetector
)

logger = logging.getLogger(__name__)

CLASS_MAPPING = {
    0: "SPOOF (Print Attack)",
    1: "REAL (Genuine Face)",
    2: "SPOOF (Replay Attack)"
}


class FaceSystemEngine:
    """
    Singleton manager for MTCNN, InceptionResNetV1, and MiniFASNet models.
    Ensures models are initialized once and reused across requests.
    """
    _instance: Optional['FaceSystemEngine'] = None

    def __init__(self, device: Optional[str] = None):
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        logger.info("Initializing FaceSystemEngine on device: %s", self.device)

        # 1. Face Verification Models
        self.mtcnn = MTCNN(image_size=160, margin=0, keep_all=False, device=self.device)
        self.resnet = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)

        # 2. Helpers
        self.cropper = CropImage()
        self.fallback_detector = OpenCVFaceDetector()

        # 3. MiniFASNet Anti-Spoofing Checkpoints
        weights_dir = Path(__file__).resolve().parent / "weights"
        v2_path = weights_dir / "2.7_80x80_MiniFASNetV2.pth"
        v1se_path = weights_dir / "4_0_0_80x80_MiniFASNetV1SE.pth"

        self.minifasnet_v2 = self._load_checkpoint(MiniFASNetV2, v2_path)
        self.minifasnet_v1se = self._load_checkpoint(MiniFASNetV1SE, v1se_path)

        logger.info("FaceSystemEngine initialization complete.")

    @classmethod
    def get_instance(cls, device: Optional[str] = None) -> 'FaceSystemEngine':
        if cls._instance is None:
            cls._instance = FaceSystemEngine(device=device)
        return cls._instance

    def _load_checkpoint(self, model_cls, weight_path: Path):
        model = model_cls(embedding_size=128, conv6_kernel=(5, 5), num_classes=3).to(self.device)
        if not weight_path.exists():
            raise FileNotFoundError(f"MiniFASNet checkpoint not found at: {weight_path}")

        state_dict = torch.load(str(weight_path), map_location=self.device)
        new_state_dict = {
            k[7:] if k.startswith('module.') else k: v
            for k, v in state_dict.items()
        }
        model.load_state_dict(new_state_dict)
        model.eval()
        return model

    def normalize_embedding(self, emb: np.ndarray) -> np.ndarray:
        """L2 normalizes embedding vector."""
        flat = emb.flatten()
        norm = np.linalg.norm(flat)
        if norm == 0:
            return flat
        return flat / norm

    def extract_face_embedding(self, image_bgr: np.ndarray) -> Optional[np.ndarray]:
        """
        Extracts 512-dim face recognition embedding from a single BGR image.
        Returns normalized 512-dim numpy array or None if no face detected.
        """
        if image_bgr is None or image_bgr.size == 0:
            return None

        frame_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb).convert("RGB")

        face = self.mtcnn(pil_img)
        if face is None:
            return None

        face_tensor = face.unsqueeze(0).to(self.device)
        with torch.no_grad():
            embedding = self.resnet(face_tensor).cpu().numpy()

        return self.normalize_embedding(embedding)

    def predict_single_frame_spoof(self, image_bgr: np.ndarray) -> Optional[np.ndarray]:
        """
        Evaluates anti-spoofing probabilities for a single frame:
        1. MTCNN landmark detection & roll rotation calculation.
        2. Extreme tilt (>30 deg) spoof detection.
        3. 2D Affine rotation normalization if tilted (3 to 30 deg).
        4. Close-distance ratio check (ratio > 0.38 or bh > 0.65*h).
        5. Multi-scale MiniFASNet crops (scale 2.7 and 4.0).
        6. Returns 3-class softmax probability array [print, real, replay].
        """
        if image_bgr is None or image_bgr.size == 0:
            return None

        h, w = image_bgr.shape[:2]
        frame_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)

        # Detect face & 5-point facial landmarks
        boxes, probs, points = self.mtcnn.detect(pil_img, landmarks=True)

        bbox = None
        aligned_img = image_bgr.copy()

        if boxes is not None and len(boxes) > 0:
            b = boxes[0]
            x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
            bw, bh = x2 - x1, y2 - y1
            bbox = [max(0, x1), max(0, y1), max(1, bw), max(1, bh)]

            # Check rotation angle via eye landmarks
            if points is not None and len(points) > 0:
                landmarks = points[0]
                left_eye, right_eye = landmarks[0], landmarks[1]
                dy = right_eye[1] - left_eye[1]
                dx = right_eye[0] - left_eye[0]
                angle = float(np.degrees(np.arctan2(dy, dx)))

                # Extreme unnatural tilt check (>30 deg tilt typical of rotated phone attack)
                if abs(angle) > 30.0:
                    logger.warning("Extreme head tilt detected (%0.2f deg). Classified as spoof replay attack.", angle)
                    return np.array([0.05, 0.05, 0.90])

                # Perform affine rotation alignment to upright 0 deg if moderately tilted
                if abs(angle) > 3.0:
                    eye_center = (
                        float((left_eye[0] + right_eye[0]) / 2.0),
                        float((left_eye[1] + right_eye[1]) / 2.0)
                    )
                    M = cv2.getRotationMatrix2D(eye_center, angle, 1.0)
                    aligned_img = cv2.warpAffine(image_bgr, M, (w, h), flags=cv2.INTER_CUBIC)

        # Fallback to OpenCV cascade detector if MTCNN missed bbox
        if bbox is None:
            faces = self.fallback_detector.detect(image_bgr)
            if len(faces) > 0:
                bbox = faces[0]
            else:
                return None

        # Distance & Close-range check: Face filling >38% frame area or height >65% frame height
        bw, bh = bbox[2], bbox[3]
        area_ratio = (bw * bh) / float(w * h)
        if area_ratio > 0.38 or bh > 0.65 * h:
            logger.warning("Close-range distance anomaly detected (area ratio=%0.3f).", area_ratio)
            return np.array([0.05, 0.05, 0.90])

        # Multi-scale crops from normalized upright image
        crop_27 = self.cropper.crop(aligned_img, bbox, scale=2.7, out_w=80, out_h=80)
        crop_40 = self.cropper.crop(aligned_img, bbox, scale=4.0, out_w=80, out_h=80)

        t_27 = torch.from_numpy(crop_27.transpose((2, 0, 1))).float().unsqueeze(0).to(self.device)
        t_40 = torch.from_numpy(crop_40.transpose((2, 0, 1))).float().unsqueeze(0).to(self.device)

        with torch.no_grad():
            prob_v2 = F.softmax(self.minifasnet_v2(t_27), dim=1).cpu().numpy()
            prob_v1se = F.softmax(self.minifasnet_v1se(t_40), dim=1).cpu().numpy()

        combined_prob = (prob_v2 + prob_v1se) / 2.0
        return combined_prob[0]

    def anti_spoofing_detection(
        self,
        frames: Union[np.ndarray, List[np.ndarray]],
        threshold: float = 0.60,
        max_replay_thresh: float = 0.30
    ) -> Tuple[bool, str, float, Dict[str, float]]:
        """
        Evaluates multi-frame temporal anti-spoofing over a sequence of frames.
        Returns:
            (is_real: bool, class_label: str, real_score: float, scores_dict: dict)
        """
        if isinstance(frames, np.ndarray):
            frame_list = [frames]
        else:
            frame_list = [f for f in frames if f is not None and f.size > 0]

        if not frame_list:
            return False, "Invalid Input", 0.0, {"real": 0.0, "print": 0.0, "replay": 0.0}

        probs_list = []
        for frame in frame_list:
            prob = self.predict_single_frame_spoof(frame)
            if prob is not None:
                probs_list.append(prob)

        if not probs_list:
            return False, "No Face Detected", 0.0, {"real": 0.0, "print": 0.0, "replay": 0.0}

        # Temporal average across sampled burst frames
        avg_prob = np.mean(probs_list, axis=0)
        print_score = float(avg_prob[0])
        real_score = float(avg_prob[1])
        replay_score = float(avg_prob[2])

        pred_class = int(np.argmax(avg_prob))
        class_label = CLASS_MAPPING.get(pred_class, "SPOOF")

        scores = {
            "real": real_score,
            "print": print_score,
            "replay": replay_score,
            "sampled_frames": len(probs_list)
        }

        # Strict liveness condition
        is_real = (pred_class == 1 and real_score >= threshold and replay_score < max_replay_thresh)
        return is_real, class_label, real_score, scores

    def verify_face_embedding(
        self,
        frames: Union[np.ndarray, List[np.ndarray]],
        registered_embedding: np.ndarray,
        threshold: float = 0.65
    ) -> Tuple[bool, float, str]:
        """
        Extracts candidate face embedding from frames and verifies cosine similarity
        against registered embedding.
        Returns:
            (is_matched: bool, similarity: float, message: str)
        """
        if isinstance(frames, list):
            # Prefer last frame or middle frame
            candidate_frame = frames[-1] if len(frames) > 0 else None
        else:
            candidate_frame = frames

        if candidate_frame is None or candidate_frame.size == 0:
            return False, 0.0, "Invalid image input"

        cand_emb = self.extract_face_embedding(candidate_frame)
        if cand_emb is None:
            # Try searching other frames in list if last frame missed
            if isinstance(frames, list):
                for f in reversed(frames[:-1]):
                    cand_emb = self.extract_face_embedding(f)
                    if cand_emb is not None:
                        break

        if cand_emb is None:
            return False, 0.0, "No face detected in frames for recognition"

        reg_norm = self.normalize_embedding(registered_embedding)
        similarity = float(np.dot(cand_emb, reg_norm))
        is_matched = bool(similarity >= threshold)

        if is_matched:
            return True, similarity, "Face matched successfully."
        else:
            return False, similarity, f"Face match below threshold ({similarity:.3f} < {threshold:.3f})"

    def overall_verification(
        self,
        frames: Union[np.ndarray, List[np.ndarray]],
        registered_embedding: np.ndarray,
        similarity_threshold: float = 0.65,
        spoof_threshold: float = 0.60,
        max_replay_thresh: float = 0.30
    ) -> Dict[str, Any]:
        """
        Full integrated verification:
        1. Evaluates anti-spoofing across frames.
        2. Evaluates face matching against registered embedding.
        Returns overall status and details.
        """
        # Anti-spoofing
        liveness_ok, spoof_label, real_score, spoof_scores = self.anti_spoofing_detection(
            frames, threshold=spoof_threshold, max_replay_thresh=max_replay_thresh
        )

        # Face verification
        face_match_ok, sim_score, match_msg = self.verify_face_embedding(
            frames, registered_embedding, threshold=similarity_threshold
        )

        overall_passed = bool(liveness_ok and face_match_ok)

        if not liveness_ok:
            if spoof_label == "No Face Detected":
                reason = "no_face_detected"
            elif spoof_scores.get("replay", 0.0) >= max_replay_thresh:
                reason = "spoof_detected_replay"
            elif spoof_scores.get("print", 0.0) > real_score:
                reason = "spoof_detected_print"
            else:
                reason = "liveness_score_below_threshold"
        elif not face_match_ok:
            reason = "face_match_below_threshold"
        else:
            reason = "face_and_liveness_verified"

        return {
            "passed": overall_passed,
            "reason": reason,
            "liveness_passed": liveness_ok,
            "liveness_label": spoof_label,
            "real_score": real_score,
            "spoof_scores": spoof_scores,
            "face_matched": face_match_ok,
            "similarity_score": sim_score,
            "face_match_message": match_msg
        }
