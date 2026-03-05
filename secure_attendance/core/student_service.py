from core.crypto_utils import aes_encrypt
from core.models import StudentProfile
from core.models import Device
from core.crypto_utils import sha256_hash

def register_device(user, public_key_pem, device_info_string):
    fingerprint_hash = sha256_hash(device_info_string)

    device = Device.objects.create(
        student=user,
        public_key=public_key_pem,
        fingerprint_hash=fingerprint_hash,
        revoked=False
    )

    return device


def register_face_embedding(user, embedding_string):
    encrypted = aes_encrypt(embedding_string.encode())

    profile, created = StudentProfile.objects.update_or_create(
        user=user,
        defaults={'encrypted_face_embedding': encrypted}
    )

    return profile
