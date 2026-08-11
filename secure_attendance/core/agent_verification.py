"""
agent_verification.py — Django-side verification of Attendance Agent challenge proofs.

Flow:
  1. Student fetches challenge from Agent (HTTP LAN): { nonce, timestamp, proof, agent_sig }
  2. Student submits attendance to Django (HTTPS) including the challenge bundle.
  3. Django calls verify_agent_challenge() BEFORE passkey, face, and liveness checks.

Verification steps:
  a. Timestamp freshness (within CHALLENGE_TTL_SECONDS)
  b. Nonce not replayed (checked against Django cache)
  c. Ed25519 agent signature valid (proves Agent issued the challenge, not a fake)
  d. HMAC-SHA256 proof valid (proves student was physically on the LAN when challenge was issued)

Note on HMAC verification:
  Django stores SHA256(session_secret) — NOT the plaintext session_secret.
  The HMAC proof is computed by the Agent using plaintext session_secret.
  Django CANNOT independently recompute HMAC from the hash alone.
  Therefore, the Ed25519 agent signature is the primary trust anchor on the Django side.
  The HMAC proof is verified by the Agent itself (via the /challenge endpoint replay-detection).
  Django trusts the Agent's signature over the challenge payload as proof of LAN presence.
"""
import hashlib
import hmac as hmac_lib
import logging
import time

from django.conf import settings
from django.core.cache import cache

from core.models import AttendanceSession, AttendanceAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHALLENGE_TTL_SECONDS: int = getattr(settings, "ATTENDANCE_AGENT_CHALLENGE_TTL_SECONDS", 30)
NONCE_CACHE_PREFIX = "agent_nonce_used:"
NONCE_CACHE_TTL = CHALLENGE_TTL_SECONDS * 2  # Keep used nonces for 2× TTL to catch replays


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_agent_challenge(
    session: AttendanceSession,
    nonce: str,
    timestamp: int,
    proof: str,
    agent_sig: str,
) -> tuple[bool, str]:
    """
    Verify an Attendance Agent challenge bundle submitted by a student.

    Returns (True, "ok") on success.
    Returns (False, reason_str) on failure.
    """
    # Step 1: Timestamp freshness
    now = int(time.time())
    age = now - timestamp
    if age < 0 or age > CHALLENGE_TTL_SECONDS:
        logger.warning(
            "Agent challenge expired: nonce=%s age=%ds session=%s",
            nonce[:8], age, session.id,
        )
        return False, "challenge_expired"

    # Step 2: Replay detection — nonce must be one-time use
    cache_key = f"{NONCE_CACHE_PREFIX}{nonce}"
    if cache.get(cache_key):
        logger.warning("Replay attempt detected: nonce=%s session=%s", nonce[:8], session.id)
        return False, "replay_attack"

    # Step 3: Verify Ed25519 agent signature
    agent_record = _get_agent_for_session(session)
    if agent_record is None:
        logger.error(
            "No AttendanceAgent registered for session %s (professor %s). "
            "Run the Attendance Agent and register it first.",
            session.id, session.professor.email,
        )
        return False, "agent_not_registered"

    payload_str = f"{nonce}:{timestamp}:{str(session.id)}:{proof}"
    sig_valid = _verify_ed25519_signature(
        public_key_pem=agent_record.public_key_pem,
        payload=payload_str.encode("utf-8"),
        signature_hex=agent_sig,
    )
    if not sig_valid:
        logger.warning(
            "Agent signature invalid: nonce=%s session=%s agent=%s",
            nonce[:8], session.id, agent_record.agent_id,
        )
        return False, "invalid_agent_signature"

    # Step 4: Mark nonce as used (consume it)
    cache.set(cache_key, True, timeout=NONCE_CACHE_TTL)

    logger.info(
        "Agent challenge verified OK: session=%s nonce=%s agent=%s",
        session.id, nonce[:8], agent_record.agent_id,
    )
    return True, "ok"


def mark_nonce_used(nonce: str) -> None:
    """Explicitly mark a nonce as used (e.g. from tests or admin actions)."""
    cache_key = f"{NONCE_CACHE_PREFIX}{nonce}"
    cache.set(cache_key, True, timeout=NONCE_CACHE_TTL)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_agent_for_session(session: AttendanceSession):
    """
    Return the AttendanceAgent registered for the professor who owns this session.
    Falls back to looking up by session.agent_id, latest registered agent,
    or querying the local Attendance Agent HTTP endpoint if DB has no agent record.
    """
    if session.agent_id:
        agent = AttendanceAgent.objects.filter(agent_id=session.agent_id).first()
        if agent:
            return agent

    try:
        if hasattr(session.professor, "attendance_agent"):
            return session.professor.attendance_agent
    except Exception:
        pass

    agent = AttendanceAgent.objects.filter(professor=session.professor).first()
    if agent:
        return agent

    agent = AttendanceAgent.objects.order_by('-registered_at').first()
    if agent:
        return agent

    # Ultimate self-healing fallback: query local Attendance Agent HTTP server
    return _auto_discover_local_agent(session.professor)


def _auto_discover_local_agent(professor=None):
    """Query local Attendance Agent HTTP server to register its key dynamically."""
    import requests
    from django.conf import settings
    agent_url = getattr(settings, "ATTENDANCE_AGENT_URL", "http://127.0.0.1:5000").rstrip("/")
    try:
        resp = requests.get(f"{agent_url}/status", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            agent_id = data.get("agent_id")
            public_key_pem = data.get("public_key_pem")
            if agent_id and public_key_pem:
                agent_record, _ = AttendanceAgent.objects.update_or_create(
                    agent_id=agent_id,
                    defaults={
                        "public_key_pem": public_key_pem,
                        "professor": professor,
                    },
                )
                logger.info("Auto-discovered local Attendance Agent: agent_id=%s", agent_id[:8])
                return agent_record
    except Exception as exc:
        logger.debug("Auto-discovery of local agent failed: %s", exc)
    return None


def _verify_ed25519_signature(public_key_pem: str, payload: bytes, signature_hex: str) -> bool:
    """Verify Ed25519 signature using the cryptography library."""
    try:
        from cryptography.hazmat.primitives import serialization
        pub_key = serialization.load_pem_public_key(public_key_pem.encode())
        pub_key.verify(bytes.fromhex(signature_hex), payload)
        return True
    except Exception:
        return False
