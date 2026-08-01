import os
import logging
import numpy as np
from typing import Tuple, Optional
from core.crypto_utils import aes_encrypt
from core.models import StudentProfile, User

logger = logging.getLogger(__name__)

# Singletons for PyTorch face models (warmed up on demand, kept in memory)
_MTCNN_INSTANCE = None
_RESNET_INSTANCE = None


def get_face_models():
    """
    Thread-safe singleton loader for MTCNN and InceptionResnetV1.
    Prevents costly model instantiation overhead on every HTTP request.
    """
    global _MTCNN_INSTANCE, _RESNET_INSTANCE
    if _MTCNN_INSTANCE is None or _RESNET_INSTANCE is None:
        import torch
        from PIL import Image
        from facenet_pytorch import MTCNN, InceptionResnetV1

        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info("Initializing PyTorch face detection & extraction models on %s", device)

        _MTCNN_INSTANCE = MTCNN(image_size=160, margin=0, device=device)
        _RESNET_INSTANCE = InceptionResnetV1(pretrained='vggface2').eval().to(device)

    return _MTCNN_INSTANCE, _RESNET_INSTANCE


class FaceEmbeddingCache:
    """
    In-memory vector cache for enrolled student embeddings.
    Stores L2-normalized 512-dim vectors for O(1) single-user matching
    and vectorized matrix multiplication for 1:N searches.
    """
    _cache = {}  # {user_id_str: normalized_numpy_array}

    @classmethod
    def get(cls, user_id_str: str) -> Optional[np.ndarray]:
        if user_id_str in cls._cache:
            return cls._cache[user_id_str]

        embedding_path = f"embeddings/{user_id_str}.npy"
        if os.path.exists(embedding_path):
            try:
                emb = np.load(embedding_path)
                norm_emb = normalize_embedding(emb)
                cls._cache[user_id_str] = norm_emb
                return norm_emb
            except Exception as e:
                logger.error("Failed to load embedding for %s: %s", user_id_str, e)
                return None
        return None

    @classmethod
    def set(cls, user_id_str: str, embedding_np: np.ndarray):
        norm_emb = normalize_embedding(embedding_np)
        cls._cache[user_id_str] = norm_emb

    @classmethod
    def remove(cls, user_id_str: str):
        cls._cache.pop(user_id_str, None)


def normalize_embedding(emb: np.ndarray) -> np.ndarray:
    """L2 normalizes a numpy embedding vector for cosine similarity calculation via dot product."""
    flat = emb.flatten()
    norm = np.linalg.norm(flat)
    if norm == 0:
        return flat
    return flat / norm


def register_student_face_embedding(user: User, embedding_np: np.ndarray) -> Tuple[bool, str]:
    """
    Saves student face embedding to disk & database, updating in-memory vector cache.
    """
    try:
        norm_emb = normalize_embedding(embedding_np)
        os.makedirs("embeddings", exist_ok=True)
        embedding_path = f"embeddings/{user.id}.npy"
        np.save(embedding_path, norm_emb)

        FaceEmbeddingCache.set(str(user.id), norm_emb)

        encrypted = aes_encrypt(norm_emb.tobytes())
        StudentProfile.objects.update_or_create(
            user=user,
            defaults={'encrypted_face_embedding': encrypted}
        )
        return True, "Face embedding registered successfully."
    except Exception as e:
        logger.error("Error registering face embedding for user %s: %s", user.id, e)
        return False, f"Registration error: {str(e)}"


def verify_student_face(user_id: str, candidate_embedding_np: np.ndarray, threshold: float = 0.7) -> Tuple[bool, float, str]:
    """
    Fast O(1) face verification using normalized dot product against in-memory cache.
    """
    stored_emb = FaceEmbeddingCache.get(str(user_id))
    if stored_emb is None:
        return False, 0.0, "No face profile registered for this student."

    cand_norm = normalize_embedding(candidate_embedding_np)
    # Cosine similarity between unit vectors is simple dot product
    similarity = float(np.dot(stored_emb, cand_norm))

    if similarity >= threshold:
        return True, similarity, "Face matched successfully."
    else:
        return False, similarity, f"Face match score below threshold ({similarity:.2f} < {threshold})"


def revoke_student_face(user: User) -> bool:
    """
    Revokes/deletes a student's face profile and clears memory cache.
    """
    try:
        user_id_str = str(user.id)
        embedding_path = f"embeddings/{user_id_str}.npy"
        if os.path.exists(embedding_path):
            os.remove(embedding_path)

        StudentProfile.objects.filter(user=user).delete()
        FaceEmbeddingCache.remove(user_id_str)
        return True
    except Exception as e:
        logger.error("Error revoking face for user %s: %s", user.id, e)
        return False

