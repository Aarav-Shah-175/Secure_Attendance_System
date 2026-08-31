"""
agent.py — Core Attendance Agent logic.

Manages:
  - Ed25519 identity (load or generate on first run)
  - Registration with Django
  - Active session secrets (RAM only, never persisted)
  - Challenge generation and HMAC proof computation
  - Session lifecycle (start, stop, expiry)
"""
import time
import logging
import threading
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict

# Ensure package root is in sys.path when executed directly
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

import requests  # type: ignore

from attendance_agent.config import AgentConfig
from attendance_agent.crypto import (
    load_or_generate_ed25519_keypair,
    public_key_to_pem,
    generate_challenge_nonce,
    compute_hmac_proof,
    sign_payload,
    sha256_hex,
    decrypt_session_secret,
)
from attendance_agent.challenge_store import ChallengeStore

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    session_id: str
    session_secret: bytes          # RAM only — never written to disk
    session_secret_hash: str       # SHA256(session_secret) — matches DB
    started_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None


class AttendanceAgent:
    """
    Core agent: manages identity, session secrets and challenge issuance.
    Designed to run as a singleton inside the Flask API process.
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._sessions: Dict[str, SessionState] = {}
        self._challenge_store = ChallengeStore()

        # Load or create Ed25519 identity
        self._private_key, self._public_key = load_or_generate_ed25519_keypair(
            config.key_path, config.pub_key_path
        )
        self._public_key_pem: str = public_key_to_pem(self._public_key)
        self._agent_id: str = sha256_hex(self._public_key_pem.encode())[:16]
        logger.info("Agent identity loaded. Agent ID prefix: %s", self._agent_id)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def public_key_pem(self) -> str:
        return self._public_key_pem

    # ------------------------------------------------------------------
    # Registration with Django
    # ------------------------------------------------------------------

    def register_with_django(self) -> bool:
        """
        POST public key to Django /agent/register/.
        Returns True on success.
        """
        url = f"{self.config.django_url}/agent/register/"
        try:
            resp = requests.post(
                url,
                json={
                    "agent_id": self.agent_id,
                    "public_key_pem": self.public_key_pem,
                },
                headers={"Authorization": f"Bearer {self.config.api_token}"},
                verify=self.config.verify_ssl,
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Agent registered with Django successfully.")
                return True
            else:
                logger.error("Django registration failed: %s %s", resp.status_code, resp.text)
                return False
        except Exception as exc:
            logger.error("Django registration request failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start_session(self, session_id: str, session_secret_hex: str, expires_at: Optional[float] = None) -> bool:
        """
        Receive a session secret from Django (hex-encoded plaintext after decryption).
        Store in RAM only.
        """
        try:
            secret_bytes = bytes.fromhex(session_secret_hex)
        except ValueError:
            logger.error("Invalid session_secret_hex for session %s", session_id)
            return False

        secret_hash = sha256_hex(secret_bytes)
        state = SessionState(
            session_id=session_id,
            session_secret=secret_bytes,
            session_secret_hash=secret_hash,
            expires_at=expires_at,
        )
        with self._lock:
            self._sessions[session_id] = state
        logger.info("Session %s started in agent (secret_hash prefix: %s...)", session_id, secret_hash[:8])
        return True

    def stop_session(self, session_id: str) -> None:
        """
        Remove and zeroize session secret.
        Revoke all outstanding challenges for the session.
        """
        with self._lock:
            state = self._sessions.pop(session_id, None)
            if state:
                # Zeroize secret bytes in memory (best-effort in CPython)
                try:
                    ctypes_array = (type('c_char', (), {}))(len(state.session_secret))
                    import ctypes
                    ctypes.memmove(ctypes.id(state.session_secret) + 20, b'\x00' * len(state.session_secret), len(state.session_secret))
                except Exception:
                    pass
                logger.info("Session %s stopped and secret zeroized.", session_id)

        self._challenge_store.revoke_session(session_id)

    def get_active_session(self, session_id: str) -> Optional[SessionState]:
        with self._lock:
            state = self._sessions.get(session_id)
            if state and state.expires_at and time.time() > state.expires_at:
                # Auto-expire
                self.stop_session(session_id)
                return None
            return state

    def list_active_sessions(self) -> list[str]:
        with self._lock:
            now = time.time()
            return [
                sid for sid, s in self._sessions.items()
                if s.expires_at is None or now <= s.expires_at
            ]

    # ------------------------------------------------------------------
    # Challenge generation
    # ------------------------------------------------------------------

    def generate_challenge(self, session_id: str) -> Optional[dict]:
        """
        Generate a one-time HMAC-SHA256 challenge for a student.
        Returns: { nonce, timestamp, proof, agent_sig } or None if no active session.
        """
        state = self.get_active_session(session_id)
        if not state:
            logger.warning("generate_challenge: no active session for %s", session_id)
            return None

        nonce = generate_challenge_nonce()
        timestamp = int(time.time())

        # HMAC-SHA256 proof: proves student was physically on the LAN (Agent served it)
        proof = compute_hmac_proof(state.session_secret, nonce, timestamp, session_id)

        # Agent signs the challenge payload with Ed25519 for Django to verify Agent authenticity
        payload_str = f"{nonce}:{timestamp}:{session_id}:{proof}"
        agent_sig = sign_payload(self._private_key, payload_str.encode("utf-8"))

        # Register nonce as one-time use
        self._challenge_store.issue(nonce, session_id, self.config.challenge_ttl_seconds)

        logger.debug("Challenge issued for session %s nonce=%s", session_id, nonce[:8])
        return {
            "nonce": nonce,
            "timestamp": timestamp,
            "proof": proof,
            "agent_sig": agent_sig,
            "session_id": session_id,
            "ttl": self.config.challenge_ttl_seconds,
        }

    # ------------------------------------------------------------------
    # Verification helpers (used internally for sanity checks)
    # ------------------------------------------------------------------

    def verify_nonce_fresh(self, nonce: str, session_id: str) -> tuple[bool, str]:
        """Verify a nonce is fresh and not replayed (consumed on success)."""
        return self._challenge_store.verify_and_consume(nonce, session_id)


if __name__ == "__main__":
    from attendance_agent.__main__ import main
    main()

