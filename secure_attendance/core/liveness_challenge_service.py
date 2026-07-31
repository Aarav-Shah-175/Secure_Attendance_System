"""
liveness_challenge_service.py

Server-side liveness challenge issuance and nonce verification.

Flow:
  1. issue_liveness_challenge(attempt_id)
       → picks a random challenge type
       → generates a short-lived HMAC nonce stored in cache (TTL 60 s)
       → returns { challenge_type, nonce, time_limit }

  2. verify_liveness_nonce(attempt_id, nonce)
       → verifies the nonce is authentic (HMAC check)
       → verifies it has not been consumed yet (cache presence)
       → consumes the nonce (deletes from cache)
       → returns (ok: bool, reason: str)
"""

import hmac
import hashlib
import random
import time
import logging

from django.core.cache import cache #type: ignore
from django.conf import settings #type: ignore

logger = logging.getLogger(__name__)

# ── Challenge catalogue ────────────────────────────────────────────────────────

CHALLENGES = [
    {"type": "blink",    "text": "Blink 2 times",               "target": 2},
    {"type": "left",     "text": "Turn your head RIGHT",          "target": None},
    {"type": "right",    "text": "Turn your head LEFT",         "target": None},
    {"type": "straight", "text": "Look straight at the camera",  "target": None},
]

NONCE_TTL_SECONDS = 60   # nonce valid for 60 seconds
TIME_LIMIT_SECONDS = 7   # time given to student to complete challenge


def _get_secret() -> bytes:
    """Return a stable server secret for HMAC signing."""
    secret = getattr(settings, "LIVENESS_NONCE_SECRET", None)
    if secret:
        return secret.encode("utf-8") if isinstance(secret, str) else secret
    # Fall back to Django SECRET_KEY — never exposed to client
    return settings.SECRET_KEY.encode("utf-8")


def _make_nonce(attempt_id: str, challenge_type: str, timestamp: int) -> str:
    """Produce an HMAC-SHA256 nonce over attempt_id|challenge_type|timestamp."""
    message = f"{attempt_id}|{challenge_type}|{timestamp}".encode("utf-8")
    return hmac.new(_get_secret(), message, hashlib.sha256).hexdigest()


def _cache_key(attempt_id: str) -> str:
    return f"liveness_nonce:{attempt_id}"


# ── Public API ─────────────────────────────────────────────────────────────────

def issue_liveness_challenge(attempt_id: str) -> dict:
    """
    Issue a random liveness challenge for the given attempt.

    Returns a dict with:
        challenge_type     "blink" | "left" | "right" | "straight"
        challenge_text     human-readable instruction for the UI
        challenge_target   int (blink only) or None
        nonce              HMAC token the client must echo back
        time_limit         seconds the client has to complete the challenge
    """
    challenge = random.choice(CHALLENGES)
    timestamp = int(time.time())
    nonce = _make_nonce(attempt_id, challenge["type"], timestamp)

    # Store in cache so we can verify it is genuine and unspent
    cache_payload = {
        "challenge_type": challenge["type"],
        "nonce": nonce,
        "timestamp": timestamp,
    }
    cache.set(_cache_key(attempt_id), cache_payload, timeout=NONCE_TTL_SECONDS)

    logger.debug(
        "Issued liveness challenge attempt=%s type=%s", attempt_id, challenge["type"]
    )

    return {
        "challenge_type": challenge["type"],
        "challenge_text": challenge["text"],
        "challenge_target": challenge.get("target"),
        "nonce": nonce,
        "time_limit": TIME_LIMIT_SECONDS,
    }


def verify_liveness_nonce(attempt_id: str, nonce: str):
    """
    Verify the nonce returned by the client after completing the challenge.

    Returns (True, "ok") on success.
    Returns (False, reason_string) on failure.
    Consumes the nonce on success so it cannot be reused.
    """
    if not nonce:
        return False, "missing_nonce"

    cache_payload = cache.get(_cache_key(attempt_id))
    if cache_payload is None:
        return False, "nonce_expired_or_not_issued"

    stored_nonce = cache_payload.get("nonce", "")
    challenge_type = cache_payload.get("challenge_type", "")
    timestamp = cache_payload.get("timestamp", 0)

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(stored_nonce, nonce):
        return False, "nonce_invalid"

    # Double-check expiry (cache TTL is authoritative, but belt-and-suspenders)
    age = int(time.time()) - timestamp
    if age > NONCE_TTL_SECONDS:
        cache.delete(_cache_key(attempt_id))
        return False, "nonce_expired"

    # Consume the nonce — one-time use
    cache.delete(_cache_key(attempt_id))

    logger.debug(
        "Liveness nonce verified and consumed attempt=%s type=%s",
        attempt_id, challenge_type,
    )
    return True, "ok"
