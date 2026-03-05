import os
import uuid
import datetime
from django.utils import timezone# type: ignore
from core.crypto_utils import sha256_hash, sign_data, aes_decrypt
from core.models import AttendanceSession
import socket
import ipaddress

def get_local_hotspot_ip():
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    # Reject loopback
    if local_ip.startswith("127."):
        # Fallback: iterate interfaces
        for ip in socket.getaddrinfo(hostname, None):
            addr = ip[4][0]
            if addr.startswith("192.168.") or addr.startswith("172.") or addr.startswith("10."):
                return addr
        return None

    return local_ip

def create_attendance_session(professor, course_code, gateway_ip, subnet_range):
    AttendanceSession.objects.filter(
        professor=professor,
        active=True
    ).update(active=False)

    # # 1. Automatic Network Detection
    # gateway_ip = get_local_hotspot_ip()
    # if not gateway_ip:
    #     raise Exception("Hotspot IP not detected. Please ensure your hotspot is turned on.")

    # Calculate subnet (e.g., 192.168.137.1 -> 192.168.137.0/24)
    network = ipaddress.ip_network(gateway_ip + '/24', strict=False)
    subnet_range = str(network)

    # 2. Session Metadata
    session_id = str(uuid.uuid4())
    timestamp = timezone.now()
    expiry = timestamp + datetime.timedelta(minutes=30)
    network_nonce = os.urandom(32).hex()

    # 3. Cryptographic Signing
    metadata_string = (session_id + course_code + str(timestamp) + str(expiry))
    metadata_hash = sha256_hash(metadata_string)
    
    private_key_pem = aes_decrypt(professor.private_key_encrypted).decode()
    signature = sign_data(private_key_pem, metadata_hash.encode())

    # 4. Save to Database
    session = AttendanceSession.objects.create(
        id=session_id,
        professor=professor,
        course_code=course_code,
        expiry=expiry,
        network_nonce=network_nonce,
        session_signature=signature,
        gateway_ip=gateway_ip,
        subnet_range=subnet_range,
        active=True
    )

    return session