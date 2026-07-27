import json
import hashlib
from typing import Tuple, Dict, Any
from django.utils import timezone
from core.models import (
    AttendanceSession,
    AttendanceRecord,
    AttendanceAttempt,
    AttendanceAuditEntry,
    AttendanceSessionAuditRoot
)
from core.crypto_utils import sha256_hash, sign_data, aes_decrypt


def generate_canonical_report_v2(attempt: AttendanceAttempt) -> Tuple[dict, str, str]:
    """
    Generates canonical Secure V2 JSON report, UTF-8 encoded string, and SHA-256 hash.
    Ensures strict field key sorting and ISO-8601 timestamps.
    """
    liveness_id = str(attempt.liveness_verification.id) if hasattr(attempt, 'liveness_verification') and attempt.liveness_verification else ""
    credential_id = attempt.passkey_credential.credential_id if attempt.passkey_credential else ""

    report_dict = {
        "version": 2,
        "attempt_id": str(attempt.id),
        "session_id": str(attempt.session.id),
        "student_id": str(attempt.student.id),
        "credential_id": credential_id,
        "network_presence_id": str(attempt.id),
        "liveness_verification_id": liveness_id,
        "challenge_id": attempt.signing_challenge or "",
        "issued_at": attempt.challenge_issued_at.isoformat() if attempt.challenge_issued_at else "",
        "expires_at": attempt.expires_at.isoformat() if attempt.expires_at else "",
    }

    # Canonical UTF-8 JSON representation with sorted keys
    canonical_json_str = json.dumps(report_dict, sort_keys=True, separators=(',', ':'))
    canonical_hash = sha256_hash(canonical_json_str)

    return report_dict, canonical_json_str, canonical_hash


def create_audit_entry_v2(
    record: AttendanceRecord,
    attempt: AttendanceAttempt
) -> AttendanceAuditEntry:
    """
    Creates an append-only canonical audit entry linked to the session audit hash chain.
    Signed using the professor's private key.
    """
    session = attempt.session
    professor = session.professor

    report_dict, json_str, canonical_hash = generate_canonical_report_v2(attempt)

    # Get previous audit entry in chain
    previous_entry = AttendanceAuditEntry.objects.filter(session=session).order_by('-signed_at').first()
    previous_hash = previous_entry.canonical_report_hash if previous_entry else None

    # Payload to sign: report hash + previous hash link
    to_sign = f"{canonical_hash}:{previous_hash or 'GENESIS'}"
    
    private_key_pem = aes_decrypt(professor.private_key_encrypted).decode("utf-8")
    entry_signature = sign_data(private_key_pem, to_sign.encode("utf-8"))

    verification_refs = {
        "liveness_id": report_dict["liveness_verification_id"],
        "credential_id": report_dict["credential_id"],
        "client_ip": attempt.client_ip,
        "issued_at": report_dict["issued_at"],
    }

    audit_entry = AttendanceAuditEntry.objects.create(
        session=session,
        record=record,
        canonical_report_hash=canonical_hash,
        previous_entry_hash=previous_hash,
        entry_signature=entry_signature,
        verification_references=verification_refs,
    )

    return audit_entry


def close_session_audit_root(session: AttendanceSession) -> AttendanceSessionAuditRoot:
    """
    Finalizes and signs the session Merkle/root hash when a session is closed or audited.
    """
    entries = AttendanceAuditEntry.objects.filter(session=session).order_by('signed_at')
    
    hashes = [e.canonical_report_hash for e in entries]
    combined = "".join(hashes) if hashes else "EMPTY_SESSION"
    root_hash = sha256_hash(combined)

    private_key_pem = aes_decrypt(session.professor.private_key_encrypted).decode("utf-8")
    signature = sign_data(private_key_pem, root_hash.encode("utf-8"))

    audit_root, _ = AttendanceSessionAuditRoot.objects.update_or_create(
        session=session,
        defaults={
            'root_hash': root_hash,
            'signature': signature,
            'closed': True,
        }
    )
    return audit_root


def verify_v2_session_integrity(session_id: str) -> dict:
    """
    Verifies full canonical audit chain integrity for a Secure V2 session.
    """
    entries = AttendanceAuditEntry.objects.filter(session_id=session_id).order_by('signed_at')
    
    previous_hash = None
    corrupted = False
    details = []

    for entry in entries:
        attempt = AttendanceAttempt.objects.filter(
            session_id=session_id,
            student_id=entry.record.student_id,
            status="ACCEPTED"
        ).first()

        if not attempt:
            corrupted = True
            details.append(f"Entry {entry.id}: missing matching accepted attempt")
            continue

        _, _, expected_canonical_hash = generate_canonical_report_v2(attempt)

        if entry.canonical_report_hash != expected_canonical_hash:
            corrupted = True
            details.append(f"Entry {entry.id}: canonical report hash mismatch")

        if entry.previous_entry_hash != previous_hash:
            corrupted = True
            details.append(f"Entry {entry.id}: chain link hash mismatch (expected {previous_hash}, got {entry.previous_entry_hash})")

        previous_hash = entry.canonical_report_hash

    return {
        "valid": not corrupted,
        "entry_count": entries.count(),
        "details": details,
    }
