from django.utils import timezone# type: ignore
from django.core.exceptions import ObjectDoesNotExist#type: ignore
from core.models import AttendanceSession, AttendanceRecord, Device
from core.crypto_utils import verify_signature, sha256_hash
import ipaddress


def verify_network(student_ip, session):
    try:
        student_ip_obj = ipaddress.ip_address(student_ip)
        network_obj = ipaddress.ip_network(session.subnet_range, strict=False)

        # Check subnet membership
        if student_ip_obj not in network_obj:
            return False

        # Check gateway match
        if str(network_obj.network_address + 1) != session.gateway_ip:
            return False
        

        return True

    except ValueError:
        return False
def verify_session_integrity(session_id):
    records = AttendanceRecord.objects.filter(
        session_id=session_id
    ).order_by("timestamp")

    previous_hash = None

    for record in records:
        expected_record_hash = sha256_hash(
            str(record.student.id) + str(record.session.id)
        )

        if record.record_hash != expected_record_hash:
            return False

        if previous_hash:
            expected_chain = sha256_hash(record.record_hash + previous_hash)
            if record.chained_hash != expected_chain:
                return False
        else:
            if record.chained_hash != sha256_hash(record.record_hash):
                return False

        previous_hash = record.chained_hash

    return True


def submit_attendance(user, session_id, signed_nonce, client_ip):
    session = AttendanceSession.objects.get(id=session_id, active=True)

    if not session.active:
        return False, "Session inactive"


    if timezone.now() > session.expiry:
        return False, "Session expired"

    if not verify_network(client_ip, session):
        return False, "Not connected to hotspot"

    device = Device.objects.filter(student=user, revoked=False).first()

    if not device:
        return False, "No valid device"

    valid = verify_signature(
        device.public_key,
        session.network_nonce.encode(),
        signed_nonce
    )

    if not valid:
        return False, "Invalid signature"

    record_hash = sha256_hash(str(user.id) + str(session.id))

    if AttendanceRecord.objects.filter(record_hash=record_hash).exists():
        return False, "Duplicate attendance"

    previous_record = AttendanceRecord.objects.filter(session=session).order_by('-timestamp').first()

    if previous_record:
        chained_hash = sha256_hash(record_hash + previous_record.chained_hash)
    else:
        chained_hash = sha256_hash(record_hash)

    AttendanceRecord.objects.create(
        student=user,
        session=session,
        client_ip=client_ip,
        record_hash=record_hash,
        chained_hash=chained_hash
    )

    return True, "Attendance recorded"
