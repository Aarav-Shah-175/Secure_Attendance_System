# Secure Presence Phase 2 (V2) Architecture Specification

This document provides the architecture specification, data models, state machines, protocol payloads, cryptographic audit design, and rollback procedures for **Secure Presence Phase 2 (V2)**.

---

## 1. Overview & Objectives

Secure Presence Phase 2 upgrades the classroom attendance protocol to eliminate browser-exported private key storage and enforce server-controlled liveness and passkey authentication.

### Key Enhancements over Legacy Flow
- **WebAuthn Passkeys:** Replaces client `localStorage` ECDSA keys with hardware/OS-backed passkeys (`userVerification="required"`).
- **Injectable Liveness Boundary:** Biometric frame verification occurs server-side and binds to a specific `AttendanceAttempt`. Fails closed if unconfigured.
- **Strict Sequence:** Signing challenges are issued **only after** server-recorded liveness success and active presence heartbeats.
- **Canonical UTF-8 Audit Chain:** Replaces simple `SHA256(student_id + session_id)` with a signed canonical JSON report chain.
- **Race Condition Prevention:** Database `UniqueConstraint(fields=['student', 'session'])` enforced at the database level.

---

## 2. Request Sequence & Protocol Flow

```
Student Client                 Django Web / Services               WebAuthn / DB
      |                                 |                                |
      |--- 1. POST /start-attempt/ ---->|                                |
      |                                 |-- Validate Subnet & Passkey -->|
      |                                 |-- Create AttendanceAttempt --->|
      |<-- Return attempt_id -----------| (status: LIVENESS_PENDING)     |
      |                                 |                                |
      |--- 2. POST /heartbeat/ -------->|                                |
      |                                 |-- Record PresenceHeartbeat --->|
      |<-- Return valid: true ----------|                                |
      |                                 |                                |
      |--- 3. POST /verify-liveness/ -->|                                |
      |    (image payload + attempt_id) |-- Call LivenessVerifier ------>|
      |                                 |-- Record LivenessVerification->|
      |<-- Return liveness passed ------| (status: BIOMETRIC_VERIFIED)   |
      |                                 |                                |
      |--- 4. POST /request-challenge/ >|                                |
      |                                 |-- Verify Recent Heartbeat ---->|
      |                                 |-- Issue WebAuthn Challenge --->|
      |<-- Return WebAuthn Options -----| (status: CHALLENGE_ISSUED)     |
      |                                 |                                |
      |--- 5. WebAuthn Assertion ------>|                                |
      |    (navigator.credentials.get)  |                                |
      |                                 |                                |
      |--- 6. POST /submit/ ----------->|                                |
      |    (assertion + attempt_id)     |-- transaction.atomic() ------->|
      |                                 |-- Verify Assertion & Counter ->|
      |                                 |-- Create AttendanceRecord ---->|
      |                                 |-- Append AuditEntry Chain ---->|
      |<-- Return Attendance Recorded --| (status: ACCEPTED)             |
```

---

## 3. Data Models & Database Schema

### `AttendanceSession`
- `security_mode`: `legacy` | `secure_presence_v2` (default: `legacy`).

### `PasskeyCredential`
- `id`: UUID Primary Key
- `student`: FK to `User`
- `credential_id`: Unique String (base64url)
- `public_key`: Base64url encoded public key
- `sign_counter`: BigInt counter tracking passkey assertions
- `revoked`: Boolean flag for credential revocation

### `AttendanceAttempt`
- `status`: `PENDING` | `LIVENESS_PENDING` | `BIOMETRIC_VERIFIED` | `CHALLENGE_ISSUED` | `ACCEPTED` | `REJECTED` | `EXPIRED`
- `expires_at`: Attempt expiry timestamp (5 minutes)
- `signing_challenge`: One-time WebAuthn challenge string
- `challenge_expires_at`: Challenge expiry timestamp (120 seconds)

### `LivenessVerification`
- `attempt`: One-to-One with `AttendanceAttempt`
- `status`: `PASSED` | `FAILED` | `ERROR`
- `score`: Float score (null if unconfigured)
- `verifier_name` / `verifier_version`: Identification metadata

### `AttendanceAuditEntry`
- `session`: FK to `AttendanceSession`
- `record`: One-to-One with `AttendanceRecord`
- `canonical_report_hash`: SHA-256 hash of canonical JSON report
- `previous_entry_hash`: SHA-256 hash link to previous audit entry in session
- `entry_signature`: Signature over `canonical_report_hash:previous_entry_hash` by professor key

---

## 4. Canonical Audit Protocol Payload

Secure V2 attendance entries format the accepted report into canonical UTF-8 JSON with sorted keys:

```json
{
  "attempt_id": "8f3b2c1a-...",
  "challenge_id": "challenge_b64url",
  "credential_id": "passkey_cred_b64url",
  "expires_at": "2026-07-26T19:50:00+00:00",
  "issued_at": "2026-07-26T19:45:00+00:00",
  "liveness_verification_id": "7a2b1c3d-...",
  "network_presence_id": "8f3b2c1a-...",
  "session_id": "4e5f6a7b-...",
  "student_id": "1a2b3c4d-...",
  "version": 2
}
```

- Canonical Report Hash: `H_report = SHA256(Canonical_JSON_Bytes)`
- Chain Link: `H_chain = SHA256(H_report + H_previous)`
- Entry Signature: `ECDSA_Sign(Professor_Private_Key, H_report + ":" + H_previous)`

---

## 5. Configuration & Feature Flags

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `SECURE_PRESENCE_V2_ENABLED` | bool | `True` | Global feature toggle for Secure V2 |
| `PRESENCE_HEARTBEAT_MAX_AGE_SECONDS` | int | `15` | Max age for heartbeat validity |
| `WEBAUTHN_RP_ID` | str | `"localhost"` | WebAuthn Relying Party Identifier |
| `WEBAUTHN_ORIGIN` | str | `"https://localhost:8000"` | WebAuthn expected origin URL |
| `LIVENESS_VERIFIER_TYPE` | str | `"unconfigured"` | Liveness adapter choice (`"facenet"` or `"unconfigured"`) |

---

## 6. Threat Model & Residual Risk Analysis

### Threat Mitigation
1. **Private Key Export Leakage:** Replaced browser `localStorage` private keys with hardware/OS passkeys.
2. **Replay & Assertion Reuse:** Challenges are short-lived, single-use, and stored on the server.
3. **Database Attacker Tampering:** Signed canonical hash chain detects modified records or deleted entries.
4. **Race Conditions:** Database `UniqueConstraint` on `(student, session)` prevents double submission under concurrent requests.

### Residual Risks
> [!CAUTION]
> **Real-Time Tunnel / Proxy Relay:** LAN subnet restrictions and HTTP heartbeats verify network attachment to the classroom hotspot, but cannot prevent an on-site proxy student from forwarding biometric frames or WebAuthn prompts to a remote student via a real-time network tunnel.

---

## 7. Upgrade & Rollback Procedures

### Upgrade
1. Apply migration `0006_attendanceattempt_attendanceauditentry_and_more.py`.
2. Keep `SECURE_PRESENCE_V2_ENABLED = True`.
3. Existing legacy sessions continue operating under legacy rules.

### Rollback
1. To disable Secure V2 system-wide without data loss, set `SECURE_PRESENCE_V2_ENABLED = False` in settings/env.
2. All new sessions will automatically default to `legacy` mode.
3. Database tables (`PasskeyCredential`, `AttendanceAttempt`, etc.) remain in place safely for future re-enabling.
