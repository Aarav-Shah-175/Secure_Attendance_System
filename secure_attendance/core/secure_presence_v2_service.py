from datetime import timedelta
from typing import Tuple, Optional, Dict, Any
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from core.models import (
    User,
    AttendanceSession,
    AttendanceAttempt,
    LivenessVerification,
    AttendanceRecord,
    PasskeyCredential,
    AttemptStatus,
    LivenessStatus,
    SecurityMode
)
from core.liveness import get_liveness_verifier
from core.webauthn_service import (
    generate_passkey_authentication_options,
    verify_passkey_authentication
)
from core.presence_service import (
    verify_network_subnet,
    has_recent_valid_heartbeat
)
from core.crypto_utils import sha256_hash
from core.audit_service import create_audit_entry_v2


def is_secure_v2_enabled() -> bool:
    return getattr(settings, "SECURE_PRESENCE_V2_ENABLED", True)


def start_attendance_attempt(
    user: User,
    session_id: str,
    client_ip: str
) -> Tuple[bool, Optional[AttendanceAttempt], str]:
    """
    Step 1 of Secure V2 flow: Initialize a short-lived attendance attempt for student.
    """
    if not is_secure_v2_enabled():
        return False, None, "Secure Presence V2 is globally disabled."

    session = AttendanceSession.objects.filter(id=session_id, active=True).first()
    if not session:
        return False, None, "Attendance session not found or inactive."

    if session.security_mode != SecurityMode.SECURE_PRESENCE_V2:
        return False, None, "Session is not configured for Secure Presence V2."

    if timezone.now() > session.expiry:
        return False, None, "Attendance session has expired."

    if not verify_network_subnet(client_ip, session):
        return False, None, "Not connected to authorized classroom network."

    # Check already marked attendance
    if AttendanceRecord.objects.filter(student=user, session=session).exists():
        return False, None, "Attendance already recorded for this session."

    # Check student passkey enrolment
    has_passkey = PasskeyCredential.objects.filter(student=user, revoked=False).exists()
    if not has_passkey:
        return False, None, "No active passkey enrolled. Please register a passkey first."

    attempt = AttendanceAttempt.objects.create(
        student=user,
        session=session,
        client_ip=client_ip,
        status=AttemptStatus.LIVENESS_PENDING,
        expires_at=timezone.now() + timedelta(minutes=5)
    )

    return True, attempt, "Attendance attempt initialized."


def process_liveness_verification(
    attempt_id: str,
    user: User,
    image_payload: str
) -> Tuple[bool, Optional[LivenessVerification], str]:
    """
    Step 2 of Secure V2 flow: Evaluate face+liveness verification for attempt.
    """
    attempt = AttendanceAttempt.objects.filter(id=attempt_id, student=user).first()
    if not attempt:
        return False, None, "Attempt not found."

    if attempt.status != AttemptStatus.LIVENESS_PENDING:
        return False, None, f"Invalid attempt state: {attempt.status}"

    if timezone.now() > attempt.expires_at:
        attempt.status = AttemptStatus.EXPIRED
        attempt.failure_reason = "attempt_expired"
        attempt.save(update_fields=['status', 'failure_reason'])
        return False, None, "Attempt expired."

    verifier = get_liveness_verifier()
    decision = verifier.verify(
        attempt_id=str(attempt.id),
        student_id=str(user.id),
        image_payload=image_payload,
        challenge=str(attempt.id)
    )

    liveness_status = LivenessStatus.PASSED if decision.passed else LivenessStatus.FAILED
    liveness_verification = LivenessVerification.objects.create(
        attempt=attempt,
        status=liveness_status,
        score=decision.score,
        verifier_name=decision.verifier_name,
        verifier_version=decision.verifier_version,
        reason_code=decision.reason,
        expires_at=timezone.now() + timedelta(minutes=5)
    )

    if decision.passed:
        attempt.status = AttemptStatus.BIOMETRIC_VERIFIED
        attempt.save(update_fields=['status'])
        return True, liveness_verification, "Biometric & liveness verification passed."
    else:
        attempt.status = AttemptStatus.REJECTED
        attempt.failure_reason = decision.reason
        attempt.save(update_fields=['status', 'failure_reason'])
        return False, liveness_verification, f"Liveness verification failed: {decision.reason}"


def issue_signing_challenge_v2(
    attempt_id: str,
    user: User
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Step 3 of Secure V2 flow: Issue a short-lived WebAuthn authentication challenge.
    Requires server-recorded liveness success and a recent presence heartbeat.
    """
    attempt = AttendanceAttempt.objects.filter(id=attempt_id, student=user).first()
    if not attempt:
        return False, None, "Attempt not found."

    if attempt.status != AttemptStatus.BIOMETRIC_VERIFIED:
        return False, None, f"Attempt must complete liveness verification first. Current status: {attempt.status}"

    if timezone.now() > attempt.expires_at:
        attempt.status = AttemptStatus.EXPIRED
        attempt.save(update_fields=['status'])
        return False, None, "Attempt expired."

    if not has_recent_valid_heartbeat(attempt, user):
        return False, None, "Missing active presence heartbeat. Ensure you are connected to the classroom hotspot."

    options_dict, challenge_b64url = generate_passkey_authentication_options(user)

    now = timezone.now()
    attempt.signing_challenge = challenge_b64url
    attempt.challenge_issued_at = now
    attempt.challenge_expires_at = now + timedelta(seconds=120)
    attempt.status = AttemptStatus.CHALLENGE_ISSUED
    attempt.save(update_fields=[
        'signing_challenge',
        'challenge_issued_at',
        'challenge_expires_at',
        'status'
    ])

    return True, options_dict, "Signing challenge issued."


def submit_attendance_v2(
    user: User,
    attempt_id: str,
    credential_payload: dict,
    client_ip: str
) -> Tuple[bool, str]:
    """
    Step 4 of Secure V2 flow: Atomically verify WebAuthn assertion and record attendance.
    """
    with transaction.atomic():
        attempt = AttendanceAttempt.objects.select_for_update().filter(
            id=attempt_id,
            student=user
        ).first()

        if not attempt:
            return False, "Attempt not found."

        if attempt.status != AttemptStatus.CHALLENGE_ISSUED:
            return False, f"Invalid attempt state: {attempt.status}"

        if not attempt.challenge_expires_at or timezone.now() > attempt.challenge_expires_at:
            attempt.status = AttemptStatus.EXPIRED
            attempt.failure_reason = "challenge_expired"
            attempt.save(update_fields=['status', 'failure_reason'])
            return False, "Signing challenge expired."

        # Lock session to check active state & concurrency
        session = AttendanceSession.objects.select_for_update().get(id=attempt.session_id)
        if not session.active or timezone.now() > session.expiry:
            attempt.status = AttemptStatus.REJECTED
            attempt.failure_reason = "session_expired_or_inactive"
            attempt.save(update_fields=['status', 'failure_reason'])
            return False, "Session inactive or expired."

        if AttendanceRecord.objects.filter(student=user, session=session).exists():
            attempt.status = AttemptStatus.REJECTED
            attempt.failure_reason = "duplicate_attendance"
            attempt.save(update_fields=['status', 'failure_reason'])
            return False, "Duplicate attendance."

        if not verify_network_subnet(client_ip, session):
            attempt.status = AttemptStatus.REJECTED
            attempt.failure_reason = "subnet_mismatch"
            attempt.save(update_fields=['status', 'failure_reason'])
            return False, "Network subnet mismatch."

        if not has_recent_valid_heartbeat(attempt, user):
            attempt.status = AttemptStatus.REJECTED
            attempt.failure_reason = "heartbeat_expired"
            attempt.save(update_fields=['status', 'failure_reason'])
            return False, "Presence heartbeat expired."

        # Verify WebAuthn passkey assertion
        success, passkey, msg = verify_passkey_authentication(
            user=user,
            credential_payload=credential_payload,
            expected_challenge=attempt.signing_challenge
        )

        if not success:
            attempt.status = AttemptStatus.REJECTED
            attempt.failure_reason = msg
            attempt.save(update_fields=['status', 'failure_reason'])
            return False, f"Passkey assertion failed: {msg}"

        # Record hash calculations for legacy/V2 link
        record_hash = sha256_hash(str(user.id) + str(session.id))
        previous_record = AttendanceRecord.objects.filter(session=session).order_by('-timestamp').first()
        chained_hash = sha256_hash(record_hash + previous_record.chained_hash) if previous_record else sha256_hash(record_hash)

        # Mark attempt accepted
        attempt.status = AttemptStatus.ACCEPTED
        attempt.passkey_credential = passkey
        attempt.consumed_at = timezone.now()
        attempt.save(update_fields=['status', 'passkey_credential', 'consumed_at'])

        record = AttendanceRecord.objects.create(
            student=user,
            session=session,
            client_ip=client_ip,
            record_hash=record_hash,
            chained_hash=chained_hash
        )

        # Append canonical audit entry
        create_audit_entry_v2(record, attempt)

        return True, "Secure V2 attendance recorded successfully."
