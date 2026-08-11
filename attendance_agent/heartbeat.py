"""
heartbeat.py — Background thread that sends periodic heartbeats to Django.

If the Agent dies or the heartbeat stops, Django automatically closes
the attendance session after ATTENDANCE_AGENT_HEARTBEAT_MAX_AGE_SECONDS.
"""
import time
import logging
import threading
from typing import Optional

import requests  # type: ignore

logger = logging.getLogger(__name__)


class HeartbeatSender(threading.Thread):
    """
    Background daemon thread.
    Sends POST /agent/heartbeat/ to Django every `interval_seconds`.
    Stops cleanly when stop() is called.
    """

    def __init__(
        self,
        django_url: str,
        api_token: str,
        agent_id: str,
        get_active_sessions,   # callable -> list[str]
        interval_seconds: int = 30,
        verify_ssl: bool = False,
        register_func=None,    # optional callable -> bool
    ) -> None:
        super().__init__(name="AgentHeartbeat", daemon=True)
        self._django_url = django_url.rstrip("/")
        self._api_token = api_token
        self._agent_id = agent_id
        self._get_active_sessions = get_active_sessions
        self._interval = interval_seconds
        self._verify_ssl = verify_ssl
        self._register_func = register_func
        self._registered = False
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the heartbeat loop to stop."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def run(self) -> None:
        logger.info("Heartbeat sender started (interval=%ds)", self._interval)
        while not self._stop_event.wait(timeout=self._interval):
            if not self._registered and self._register_func:
                try:
                    self._registered = self._register_func()
                except Exception as exc:
                    logger.debug("Retry registration failed: %s", exc)

            self._send_heartbeat()
        logger.info("Heartbeat sender stopped.")

    def _send_heartbeat(self) -> None:
        active_sessions = self._get_active_sessions()
        if not active_sessions:
            return  # Nothing to ping

        url = f"{self._django_url}/agent/heartbeat/"
        for session_id in active_sessions:
            try:
                resp = requests.post(
                    url,
                    json={
                        "agent_id": self._agent_id,
                        "session_id": session_id,
                        "alive": True,
                    },
                    headers={"Authorization": f"Bearer {self._api_token}"},
                    verify=self._verify_ssl,
                    timeout=8,
                )
                if resp.status_code == 200:
                    logger.debug("Heartbeat OK for session %s", session_id)
                else:
                    logger.warning(
                        "Heartbeat rejected for session %s: %s %s",
                        session_id, resp.status_code, resp.text[:120],
                    )
            except requests.exceptions.ConnectionError:
                logger.warning("Heartbeat: Django unreachable (session %s)", session_id)
            except Exception as exc:
                logger.error("Heartbeat error for session %s: %s", session_id, exc)
