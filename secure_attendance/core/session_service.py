import os
import uuid
import datetime
import socket
import ipaddress
from django.utils import timezone
from django.conf import settings
from core.crypto_utils import sha256_hash, sign_data, aes_decrypt
from core.models import AttendanceSession, SecurityMode


def get_local_hotspot_ip():
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    if local_ip.startswith("127."):
        for ip in socket.getaddrinfo(hostname, None):
            addr = ip[4][0]
            if addr.startswith("192.168.") or addr.startswith("172.") or addr.startswith("10."):
                return addr
        return None

    return local_ip


def create_attendance_session(
    professor,
    course_code,
    gateway_ip,
    subnet_range,
    security_mode=SecurityMode.LEGACY
):
    # Enforce global feature flag for Secure V2
    v2_enabled = getattr(settings, "SECURE_PRESENCE_V2_ENABLED", True)
    if security_mode == SecurityMode.SECURE_PRESENCE_V2 and not v2_enabled:
        security_mode = SecurityMode.LEGACY

    AttendanceSession.objects.filter(
        professor=professor,
        active=True
    ).update(active=False)

    network = ipaddress.ip_network(gateway_ip + '/24', strict=False)
    subnet_range = str(network)

    session_id = str(uuid.uuid4())
    timestamp = timezone.now()
    expiry = timestamp + datetime.timedelta(minutes=30)
    network_nonce = os.urandom(32).hex()

    metadata_string = (session_id + course_code + str(timestamp) + str(expiry) + str(security_mode))
    metadata_hash = sha256_hash(metadata_string)

    private_key_pem = aes_decrypt(professor.private_key_encrypted).decode("utf-8")
    signature = sign_data(private_key_pem, metadata_hash.encode("utf-8"))

    session = AttendanceSession.objects.create(
        id=session_id,
        professor=professor,
        course_code=course_code,
        expiry=expiry,
        network_nonce=network_nonce,
        session_signature=signature,
        gateway_ip=gateway_ip,
        subnet_range=subnet_range,
        active=True,
        security_mode=security_mode
    )

    return session