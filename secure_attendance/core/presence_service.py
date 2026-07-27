import ipaddress
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from core.models import AttendanceSession, AttendanceAttempt, PresenceHeartbeat, User


def verify_network_subnet(client_ip: str, session: AttendanceSession) -> bool:
    """
    Validates that the student's IP address belongs to the classroom hotspot/subnet.
    """
    if not client_ip or not session or not session.subnet_range:
        return False
    try:
        student_ip_obj = ipaddress.ip_address(client_ip)
        network_obj = ipaddress.ip_network(session.subnet_range, strict=False)

        if student_ip_obj not in network_obj:
            return False

        # Validate gateway IP if defined
        if session.gateway_ip:
            gateway_obj = ipaddress.ip_address(session.gateway_ip)
            if gateway_obj not in network_obj:
                return False

        return True
    except (ValueError, TypeError):
        return False


def record_presence_heartbeat(attempt: AttendanceAttempt, user: User, client_ip: str) -> PresenceHeartbeat:
    """
    Records an authenticated HTTP presence heartbeat for an ongoing attendance attempt.
    """
    is_valid = verify_network_subnet(client_ip, attempt.session)
    heartbeat = PresenceHeartbeat.objects.create(
        attempt=attempt,
        student=user,
        client_ip=client_ip,
        valid=is_valid
    )
    return heartbeat


def has_recent_valid_heartbeat(
    attempt: AttendanceAttempt,
    user: User,
    max_age_seconds: int = None
) -> bool:
    """
    Checks if the student attempt has a recorded valid presence heartbeat within the maximum age window.
    """
    if max_age_seconds is None:
        max_age_seconds = getattr(settings, "PRESENCE_HEARTBEAT_MAX_AGE_SECONDS", 15)

    cutoff = timezone.now() - timedelta(seconds=max_age_seconds)
    return PresenceHeartbeat.objects.filter(
        attempt=attempt,
        student=user,
        valid=True,
        timestamp__gte=cutoff
    ).exists()
