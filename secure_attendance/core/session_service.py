"""
session_service.py — Attendance Session creation service.

In the new Agent-based architecture:
  - Hotspot IP detection has been REMOVED from Django.
  - The Attendance Agent is responsible for all network-layer verification.
  - gateway_ip and subnet_range are stored as 'agent' placeholders for
    backward compatibility with existing DB schema and export tooling.
  - session_secret is generated here and pushed to the Agent via HTTP.
"""
import os
import uuid
import secrets
import datetime
import requests
import logging
from django.utils import timezone
from django.conf import settings
from core.crypto_utils import sha256_hash, sign_data, aes_decrypt
from core.models import AttendanceSession, AttendanceAgent, SecurityMode

logger = logging.getLogger(__name__)


def create_attendance_session(
    professor,
    course_code: str,
    gateway_ip=None,
    subnet_range: str = "agent",
    security_mode=SecurityMode.SECURE_PRESENCE_V2,
    agent_id: str = "",
):
    """
    Create an AttendanceSession and push session_secret to the Attendance Agent.

    No longer requires gateway_ip or subnet_range — the Agent handles network verification.
    """
    v2_enabled = getattr(settings, "SECURE_PRESENCE_V2_ENABLED", True)
    if security_mode == SecurityMode.SECURE_PRESENCE_V2 and not v2_enabled:
        security_mode = SecurityMode.LEGACY

    # Close any existing active sessions for this professor
    AttendanceSession.objects.filter(professor=professor, active=True).update(active=False)

    session_id = str(uuid.uuid4())
    timestamp = timezone.now()
    expiry = timestamp + datetime.timedelta(minutes=30)

    # Generate session_secret (256-bit, RAM only — store only the hash in DB)
    session_secret = secrets.token_bytes(32)
    session_secret_hex = session_secret.hex()
    session_secret_hash = sha256_hash(session_secret_hex)

    # Session metadata signature (integrity)
    network_nonce = os.urandom(32).hex()
    metadata_string = session_id + course_code + str(timestamp) + str(expiry) + str(security_mode)
    metadata_hash = sha256_hash(metadata_string)

    private_key_pem = None
    if professor.private_key_encrypted:
        try:
            decrypted = aes_decrypt(professor.private_key_encrypted)
            if decrypted:
                private_key_pem = decrypted.decode("utf-8")
        except Exception as e:
            logger.warning("Could not decrypt professor private key for %s: %s", professor.email, e)

    if not private_key_pem:
        # Self-healing: auto-generate ECDSA keypair if missing or corrupted
        from core.crypto_utils import generate_ecdsa_keypair, aes_encrypt
        priv, pub = generate_ecdsa_keypair()
        professor.public_key = pub
        professor.private_key_encrypted = aes_encrypt(priv.encode("utf-8"))
        professor.save(update_fields=["public_key", "private_key_encrypted"])
        private_key_pem = priv

    signature = sign_data(private_key_pem, metadata_hash.encode("utf-8"))

    # Resolve agent_id: use provided, or look up the professor's registered agent
    if not agent_id:
        try:
            agent_record = professor.attendance_agent
            agent_id = agent_record.agent_id
        except Exception:
            # Fallback: look up unassigned or latest registered AttendanceAgent
            agent_record = AttendanceAgent.objects.filter(professor__isnull=True).order_by('-registered_at').first()
            if not agent_record:
                agent_record = AttendanceAgent.objects.order_by('-registered_at').first()

            if agent_record:
                agent_id = agent_record.agent_id
                if not agent_record.professor:
                    agent_record.professor = professor
                    agent_record.save(update_fields=['professor'])
            else:
                logger.warning(
                    "No Attendance Agent registered for professor %s. "
                    "Proceeding without agent (development mode).",
                    professor.email,
                )

    session = AttendanceSession.objects.create(
        id=session_id,
        professor=professor,
        course_code=course_code,
        expiry=expiry,
        network_nonce=network_nonce,
        session_signature=signature,
        gateway_ip=None,          # No longer used
        subnet_range="agent",     # Placeholder — agent handles network check
        session_secret_hash=session_secret_hash,
        agent_id=agent_id,
        active=True,
        security_mode=security_mode,
    )

    from django.core.cache import cache
    cache.set(f"session_secret:{session_id}", session_secret_hex, timeout=3600)

    # Push session_secret to the Agent
    _push_secret_to_agent(session, session_secret_hex, expiry)

    return session


def _push_secret_to_agent(session: AttendanceSession, session_secret_hex: str, expiry: datetime.datetime) -> None:
    """
    Push the plaintext session_secret (hex) to the Attendance Agent via HTTP.
    The Agent holds it in RAM only. Django keeps only SHA256(session_secret).
    """
    agent_url = getattr(settings, "ATTENDANCE_AGENT_URL", "http://127.0.0.1:5000")
    api_token = getattr(settings, "ATTENDANCE_AGENT_API_TOKEN", "")

    if not api_token:
        logger.warning("ATTENDANCE_AGENT_API_TOKEN not set — cannot push secret to agent.")
        return

    try:
        resp = requests.post(
            f"{agent_url}/start-session",
            json={
                "session_id": str(session.id),
                "session_secret_hex": session_secret_hex,
                "expires_at": expiry.timestamp(),
            },
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=5,
            verify=False,  # LAN HTTP; no TLS needed
        )
        if resp.status_code == 200:
            logger.info("Session secret pushed to agent for session %s", session.id)
        else:
            logger.error(
                "Agent secret push failed for session %s: %s %s",
                session.id, resp.status_code, resp.text[:200],
            )
    except requests.exceptions.ConnectionError:
        logger.warning(
            "Attendance Agent not reachable at %s. "
            "Session created but Agent not notified. Students cannot get challenges.",
            agent_url,
        )
    except Exception as exc:
        logger.error("Unexpected error pushing secret to agent: %s", exc)