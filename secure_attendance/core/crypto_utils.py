import os
import base64
import hashlib
from cryptography.hazmat.primitives import hashes# type: ignore
from cryptography.hazmat.primitives.asymmetric import ec# type: ignore
from cryptography.hazmat.primitives.serialization import (# type: ignore
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption,
    load_pem_private_key,
    load_pem_public_key,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM# type: ignore
from cryptography.hazmat.backends import default_backend# type: ignore
from dotenv import load_dotenv# type: ignore
import base64
from cryptography.hazmat.primitives import hashes# type: ignore
from cryptography.hazmat.primitives.asymmetric import ec# type: ignore
from cryptography.hazmat.primitives.serialization import load_pem_public_key# type: ignore
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature#type: ignore


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

    return private_bytes.decode(), public_bytes.decode()


# ---------- SIGNING ----------

def sign_data(private_key_pem, data: bytes):
    private_key = load_pem_private_key(
        private_key_pem.encode(),
        password=None,
        backend=default_backend()
    )

    signature = private_key.sign(
        data,
        ec.ECDSA(hashes.SHA256())
    )

    return base64.b64encode(signature).decode()


def verify_signature(public_key_pem, message_bytes, signed_nonce):
    try:
        print("Message bytes hex:", message_bytes.hex())
        print("Message decoded string:", message_bytes.decode())

        print("Message raw repr:", message_bytes)
        print("Message raw length:", len(message_bytes))
        signature_raw = base64.b64decode(signed_nonce)

        print("Raw signature length:", len(signature_raw))

        r_bytes = signature_raw[:32]
        s_bytes = signature_raw[32:]

        print("r bytes len:", len(r_bytes))
        print("s bytes len:", len(s_bytes))

        r = int.from_bytes(r_bytes, "big")
        s = int.from_bytes(s_bytes, "big")

        print("r int:", r)
        print("s int:", s)

        signature_der = encode_dss_signature(r, s)
        signature_raw = base64.b64decode(signed_nonce)

        # Web Crypto returns raw r||s (64 bytes)
        r = int.from_bytes(signature_raw[:32], byteorder="big")
        s = int.from_bytes(signature_raw[32:], byteorder="big")

        # Convert to DER format expected by cryptography
        signature_der = encode_dss_signature(r, s)

        public_key = load_pem_public_key(public_key_pem.encode())

        public_key.verify(
            signature_der,
            message_bytes,
            ec.ECDSA(hashes.SHA256())
        )

        print("Message raw repr:", message_bytes)
        print("Message raw length:", len(message_bytes))


        return True

    except Exception as e:
        print("Verification exception type:", type(e))
        print("Verification exception:", repr(e))



# ---------- AES-256-GCM ENCRYPTION ----------

def aes_encrypt(plaintext: bytes):
    key_str = os.getenv("AES_MASTER_KEY")
    key = base64.b64decode(key_str)
    aesgcm = AESGCM(key)

    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    return base64.b64encode(nonce + ciphertext).decode()


def aes_decrypt(ciphertext_b64: str):
    key_str = os.getenv("AES_MASTER_KEY")
    key = base64.b64decode(key_str)
    data = base64.b64decode(ciphertext_b64)

    nonce = data[:12]
    ciphertext = data[12:]

    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


# ---------- SHA-256 ----------

def sha256_hash(data: str):
    return hashlib.sha256(data.encode()).hexdigest()
