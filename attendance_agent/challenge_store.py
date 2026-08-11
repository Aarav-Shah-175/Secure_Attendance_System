"""
challenge_store.py — In-memory, thread-safe store for issued challenge nonces.

Guarantees one-time use: every nonce is invalidated after first verification.
Expired entries are purged automatically to avoid unbounded memory growth.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class _ChallengeEntry:
    session_id: str
    expires_at: float  # Unix timestamp
    used: bool = False


class ChallengeStore:
    """
    Thread-safe, in-memory store for active challenge nonces.

    Lifecycle:
        issue(nonce, session_id, ttl)  →  store nonce
        verify(nonce, session_id)       →  True once; False on replay / expired
        purge_expired()                 →  called internally on every verify
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: Dict[str, _ChallengeEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def issue(self, nonce: str, session_id: str, ttl_seconds: int) -> None:
        """Register a freshly generated challenge nonce."""
        expires_at = time.time() + ttl_seconds
        with self._lock:
            self._store[nonce] = _ChallengeEntry(
                session_id=session_id,
                expires_at=expires_at,
            )

    def verify_and_consume(self, nonce: str, session_id: str) -> tuple[bool, str]:
        """
        Verify a nonce presented by a student.

        Returns (True, "ok") on first valid use.
        Returns (False, reason) on replay, expiry, session mismatch, or unknown nonce.
        """
        with self._lock:
            self._purge_expired_locked()

            entry = self._store.get(nonce)

            if entry is None:
                return False, "unknown_nonce"

            if entry.session_id != session_id:
                return False, "session_id_mismatch"

            if time.time() > entry.expires_at:
                del self._store[nonce]
                return False, "challenge_expired"

            if entry.used:
                return False, "replay_attack"

            # Mark consumed — do NOT delete yet so replay within TTL is caught
            entry.used = True
            return True, "ok"

    def is_active_session(self, session_id: str) -> bool:
        """Return True if at least one valid challenge exists for the session."""
        with self._lock:
            return any(
                e.session_id == session_id and not e.used and time.time() <= e.expires_at
                for e in self._store.values()
            )

    def revoke_session(self, session_id: str) -> None:
        """Invalidate all outstanding challenges for a session (called on session end)."""
        with self._lock:
            to_delete = [n for n, e in self._store.items() if e.session_id == session_id]
            for n in to_delete:
                del self._store[n]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _purge_expired_locked(self) -> None:
        """Remove entries that are past their TTL. Must be called under lock."""
        now = time.time()
        expired = [n for n, e in self._store.items() if now > e.expires_at]
        for n in expired:
            del self._store[n]
