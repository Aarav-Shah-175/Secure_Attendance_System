"""
presence_service.py — Student presence heartbeat service.

In the new Agent-based architecture:
  - Network subnet validation has been REMOVED.
  - Heartbeats are still recorded for audit purposes.
  - valid=True is set unconditionally; actual network presence
    is now proven by the Attendance Agent challenge-response mechanism.
"""
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from core.models import AttendanceSession, AttendanceAttempt, PresenceHeartbeat, User


def record_presence_heartbeat(attempt: AttendanceAttempt, user: User, client_ip: str) -> PresenceHeartbeat:
    """
    Records an authenticated HTTP presence heartbeat for an ongoing attendance attempt.

    Note: valid is always True — presence is now guaranteed by the Agent
    HMAC-SHA256 challenge rather than IP subnet matching.
    """
    heartbeat = PresenceHeartbeat.objects.create(
        attempt=attempt,
        student=user,
        client_ip=client_ip,
        valid=True,
    )
    return heartbeat


def has_recent_valid_heartbeat(
    attempt: AttendanceAttempt,
    user: User,
    max_age_seconds: int = None,
) -> bool:
    """
    Checks if the student attempt has a recorded valid presence heartbeat
    within the maximum age window.
    """
    if max_age_seconds is None:
        max_age_seconds = getattr(settings, "PRESENCE_HEARTBEAT_MAX_AGE_SECONDS", 45)

    cutoff = timezone.now() - timedelta(seconds=max_age_seconds)
    return PresenceHeartbeat.objects.filter(
        attempt=attempt,
        student=user,
        valid=True,
        timestamp__gte=cutoff,
    ).exists()
