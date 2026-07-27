import json
import base64
import os
from typing import Tuple, Dict, Any, Optional
from django.conf import settings
from django.utils import timezone
from core.models import User, PasskeyCredential
import webauthn
from webauthn.helpers.structs import (
    PublicKeyCredentialCreationOptions,
    PublicKeyCredentialRequestOptions,
    UserVerificationRequirement,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor, #type: ignore
    PublicKeyCredentialType, #type: ignore
) 


def get_rp_id() -> str:
    return getattr(settings, "WEBAUTHN_RP_ID", "localhost")


def get_rp_name() -> str:
    return getattr(settings, "WEBAUTHN_RP_NAME", "Secure Attendance System")


def get_origin() -> str:
    return getattr(settings, "WEBAUTHN_ORIGIN", "https://localhost:8000")


def generate_passkey_registration_options(user: User) -> Tuple[Dict[str, Any], str]:
    """
    Generates WebAuthn registration options for a student.
    Returns (options_dict, challenge_b64url).
    """
    user_id_bytes = str(user.id).encode("utf-8")
    
    existing_passkeys = PasskeyCredential.objects.filter(student=user, revoked=False)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(
            id=base64.b64decode(p.credential_id),
            type=PublicKeyCredentialType.PUBLIC_KEY
        )
        for p in existing_passkeys
        if p.credential_id
    ]

    options = webauthn.generate_registration_options(
        rp_id=get_rp_id(),
        rp_name=get_rp_name(),
        user_id=user_id_bytes,
        user_name=user.email,
        user_display_name=user.email,
        exclude_credentials=exclude_credentials if exclude_credentials else None,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED
        ),
    )

    options_dict = json.loads(webauthn.options_to_json(options))
    challenge_b64url = options_dict.get("challenge", "")
    return options_dict, challenge_b64url


def verify_passkey_registration(
    user: User,
    credential_payload: dict,
    expected_challenge: str
) -> Tuple[bool, Optional[PasskeyCredential], str]:
    """
    Verifies browser WebAuthn registration response and creates a PasskeyCredential entity.
    """
    try:
        # py-webauthn >= 2.0 accepts a plain dict directly — no parse_raw() needed.
        padded_challenge = expected_challenge + "=" * ((4 - len(expected_challenge) % 4) % 4)
        verification = webauthn.verify_registration_response(
            credential=credential_payload,
            expected_challenge=base64.urlsafe_b64decode(padded_challenge),
            expected_rp_id=get_rp_id(),
            expected_origin=get_origin(),
            require_user_verification=True,
        )

        credential_id_b64 = base64.urlsafe_b64encode(verification.credential_id).decode("utf-8").rstrip("=")
        public_key_b64 = base64.urlsafe_b64encode(verification.credential_public_key).decode("utf-8").rstrip("=")

        # Check if revoked or existing
        passkey, created = PasskeyCredential.objects.update_or_create(
            credential_id=credential_id_b64,
            defaults={
                'student': user,
                'public_key': public_key_b64,
                'sign_counter': verification.sign_count,
                'revoked': False,
                'credential_metadata': {
                    'fmt': verification.fmt,
                    'user_verified': verification.user_verified,
                }
            }
        )

        return True, passkey, "Registration successful"

    except Exception as e:
        return False, None, f"Passkey registration failed: {str(e)}"


def generate_passkey_authentication_options(user: User) -> Tuple[Dict[str, Any], str]:
    """
    Generates WebAuthn authentication options for an active student passkey.
    Returns (options_dict, challenge_b64url).
    """
    active_credentials = PasskeyCredential.objects.filter(student=user, revoked=False)
    if not active_credentials.exists():
        raise ValueError("No active passkey enrolled for user.")

    allowed_credentials = []
    for cred in active_credentials:
        try:
            # Decode b64url credential id
            padded_id = cred.credential_id + "=" * ((4 - len(cred.credential_id) % 4) % 4)
            cred_id_bytes = base64.urlsafe_b64decode(padded_id)
            allowed_credentials.append(
                PublicKeyCredentialDescriptor(
                    id=cred_id_bytes,
                    type=PublicKeyCredentialType.PUBLIC_KEY
                )
            )
        except Exception:
            continue

    options = webauthn.generate_authentication_options(
        rp_id=get_rp_id(),
        allow_credentials=allowed_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    options_dict = json.loads(webauthn.options_to_json(options))
    challenge_b64url = options_dict.get("challenge", "")
    return options_dict, challenge_b64url


def verify_passkey_authentication(
    user: User,
    credential_payload: dict,
    expected_challenge: str
) -> Tuple[bool, Optional[PasskeyCredential], str]:
    """
    Verifies browser WebAuthn assertion response against registered student passkeys.
    """
    try:
        # py-webauthn >= 2.0 accepts a plain dict directly — no parse_raw() needed.
        # Extract raw_id from the payload to look up the passkey record first.
        raw_id_b64 = credential_payload.get("rawId", credential_payload.get("id", ""))
        # Normalise: rawId may be base64url without padding
        padded = raw_id_b64 + "=" * ((4 - len(raw_id_b64) % 4) % 4)
        raw_id_bytes = base64.urlsafe_b64decode(padded)
        credential_id_b64 = base64.urlsafe_b64encode(raw_id_bytes).decode("utf-8").rstrip("=")

        passkey = PasskeyCredential.objects.filter(
            credential_id=credential_id_b64,
            student=user,
            revoked=False
        ).first()

        if not passkey:
            return False, None, "Passkey credential not found or revoked"

        padded_key = passkey.public_key + "=" * ((4 - len(passkey.public_key) % 4) % 4)
        public_key_bytes = base64.urlsafe_b64decode(padded_key)

        padded_challenge = expected_challenge + "=" * ((4 - len(expected_challenge) % 4) % 4)
        challenge_bytes = base64.urlsafe_b64decode(padded_challenge)

        verification = webauthn.verify_authentication_response(
            credential=credential_payload,
            expected_challenge=challenge_bytes,
            expected_rp_id=get_rp_id(),
            expected_origin=get_origin(),
            credential_public_key=public_key_bytes,
            credential_current_sign_count=passkey.sign_counter,
            require_user_verification=True,
        )

        passkey.sign_counter = verification.new_sign_count
        passkey.save(update_fields=['sign_counter', 'updated_at'])

        return True, passkey, "Authentication successful"

    except Exception as e:
        return False, None, f"Passkey assertion failed: {str(e)}"
