import os
import base64
import hashlib
import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption,
    load_pem_private_key,
    load_pem_public_key,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

logger = logging.getLogger(__name__)


# ---------- ECDSA KEY GENERATION ----------

def generate_ecdsa_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        NoEncryption()
    )

    public_bytes = public_key.public_bytes(
        Encoding.PEM,
        PublicFormat.SubjectPublicKeyInfo
    )

    return private_bytes.decode("utf-8"), public_bytes.decode("utf-8")


# ---------- SIGNING ----------

def sign_data(private_key_pem, data: bytes):
    private_key = load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
        backend=default_backend()
    )

    signature = private_key.sign(
        data,
        ec.ECDSA(hashes.SHA256())
    )

    return base64.b64encode(signature).decode("utf-8")


def verify_signature(public_key_pem, message_bytes, signed_nonce):
    try:
        signature_raw = base64.b64decode(signed_nonce)
        
        # Web Crypto returns raw r||s (64 bytes)
        if len(signature_raw) == 64:
            r = int.from_bytes(signature_raw[:32], byteorder="big")
            s = int.from_bytes(signature_raw[32:], byteorder="big")
            signature_der = encode_dss_signature(r, s)
        else:
            # Standard DER format signature
            signature_der = signature_raw

        public_key = load_pem_public_key(public_key_pem.encode("utf-8"))

        public_key.verify(
            signature_der,
            message_bytes,
            ec.ECDSA(hashes.SHA256())
        )
        return True
    except Exception as e:
        logger.debug("Signature verification failed: %s", str(e))
        return False


# ---------- AES-256-GCM ENCRYPTION ----------

def _get_aes_key() -> bytes:
    key_str = os.getenv("AES_MASTER_KEY")
    if not key_str:
        raise ValueError("AES_MASTER_KEY is not set in environment.")
    try:
        key = base64.b64decode(key_str)
        if len(key) == 32:
            return key
    except Exception:
        pass
    return hashlib.sha256(key_str.encode("utf-8")).digest()


def aes_encrypt(plaintext: bytes):
    key = _get_aes_key()
    aesgcm = AESGCM(key)

    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def aes_decrypt(ciphertext_b64: str):
    key = _get_aes_key()
    data = base64.b64decode(ciphertext_b64)

    nonce = data[:12]
    ciphertext = data[12:]

    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


# ---------- SHA-256 ----------

def sha256_hash(data: str):
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
