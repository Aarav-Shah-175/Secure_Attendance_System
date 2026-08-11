"""
crypto.py — Cryptographic primitives for the Attendance Agent.

Primitives used:
  - Ed25519   : Agent identity key-pair (signing)
  - X25519    : ECDH key exchange for session-secret delivery
  - HMAC-SHA256 : Challenge proof generation/verification
  - SHA-256   : Hashing
  - secrets   : CSPRNG for all random values
"""
import hmac
import hashlib
import secrets
import json
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------------------------
# Ed25519 Identity Management
# ---------------------------------------------------------------------------

def generate_ed25519_keypair(key_path: Path, pub_path: Path) -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Generate a new Ed25519 keypair and persist it to disk (perm 600)."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    key_path.parent.mkdir(parents=True, exist_ok=True)

    # Write private key PEM (unencrypted; file perms provide protection)
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)

    # Write public key PEM
    pub_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    pub_path.chmod(0o644)

    return private_key, public_key


def load_ed25519_private_key(key_path: Path) -> Ed25519PrivateKey:
    """Load Ed25519 private key from PEM file."""
    return serialization.load_pem_private_key(key_path.read_bytes(), password=None)


def load_or_generate_ed25519_keypair(key_path: Path, pub_path: Path) -> Tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Load existing keypair or generate a new one."""
    if key_path.exists():
        private_key = load_ed25519_private_key(key_path)
        public_key = private_key.public_key()
        return private_key, public_key
    return generate_ed25519_keypair(key_path, pub_path)


def public_key_to_pem(public_key: Ed25519PublicKey) -> str:
    """Serialize Ed25519 public key to PEM string."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def sign_payload(private_key: Ed25519PrivateKey, payload: bytes) -> str:
    """Sign arbitrary bytes with Ed25519 private key. Returns hex signature."""
    return private_key.sign(payload).hex()


def verify_ed25519_signature(public_key_pem: str, payload: bytes, signature_hex: str) -> bool:
    """Verify Ed25519 signature. Returns True if valid."""
    try:
        pub_key = serialization.load_pem_public_key(public_key_pem.encode())
        pub_key.verify(bytes.fromhex(signature_hex), payload)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Session Secret Delivery via X25519 ECDH
# ---------------------------------------------------------------------------

def encrypt_for_agent(agent_public_key_pem: str, plaintext: bytes) -> dict:
    """
    Encrypt session_secret for delivery to the Agent using X25519 ECDH + AES-GCM.
    Returns a dict with: ephemeral_pub, nonce, ciphertext (all hex-encoded).
    """
    # Load agent's Ed25519 public key and derive X25519 from it
    # NOTE: For simplicity we carry an X25519 key for encryption separate from Ed25519 identity.
    # Django generates an ephemeral X25519 keypair, performs ECDH with agent's X25519 pub key.
    ephemeral_private = X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key()

    agent_x25519_pub = serialization.load_pem_public_key(agent_public_key_pem.encode())
    shared_secret = ephemeral_private.exchange(agent_x25519_pub)

    # Derive AES-256 key via HKDF
    aes_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"attendance-agent-session-secret",
    ).derive(shared_secret)

    # Encrypt with AES-256-GCM
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    return {
        "ephemeral_pub": ephemeral_public.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode(),
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
    }


def decrypt_session_secret(x25519_private_key: X25519PrivateKey, envelope: dict) -> bytes:
    """
    Decrypt the session_secret envelope using the Agent's X25519 private key.
    """
    ephemeral_pub = serialization.load_pem_public_key(envelope["ephemeral_pub"].encode())
    shared_secret = x25519_private_key.exchange(ephemeral_pub)

    aes_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"attendance-agent-session-secret",
    ).derive(shared_secret)

    nonce = bytes.fromhex(envelope["nonce"])
    ciphertext = bytes.fromhex(envelope["ciphertext"])

    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, ciphertext, None)


# ---------------------------------------------------------------------------
# HMAC-SHA256 Challenge Proof
# ---------------------------------------------------------------------------

def generate_challenge_nonce() -> str:
    """Generate a cryptographically random 128-bit hex challenge nonce."""
    return secrets.token_hex(16)


def compute_hmac_proof(session_secret: bytes, nonce: str, timestamp: int, session_id: str) -> str:
    """
    Compute HMAC-SHA256 proof over the challenge material.
    message = nonce || ":" || timestamp || ":" || session_id
    Returns lowercase hex digest.
    """
    message = f"{nonce}:{timestamp}:{session_id}".encode("utf-8")
    return hmac.new(session_secret, message, hashlib.sha256).hexdigest()


def verify_hmac_proof(session_secret_hash_hex: str, nonce: str, timestamp: int, session_id: str, proof: str) -> bool:
    """
    Verify HMAC proof on the Django side.
    Django stores SHA256(session_secret) — it cannot re-derive the HMAC directly.
    Instead the Agent signs the challenge with its Ed25519 key; Django verifies the signature.

    For the HMAC step: Django trusts Agent's signature over the challenge payload.
    This function is a convenience for unit-testing with plaintext secret.
    """
    message = f"{nonce}:{timestamp}:{session_id}".encode("utf-8")
    expected = hmac.new(
        bytes.fromhex(session_secret_hash_hex),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, proof)


def sha256_hex(data: bytes) -> str:
    """Return lowercase hex SHA-256 of data."""
    return hashlib.sha256(data).hexdigest()
