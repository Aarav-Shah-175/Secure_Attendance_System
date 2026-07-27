# Secure Attendance System

A security-focused classroom attendance platform built with Django. It is designed for hotspot/LAN classroom environments and combines authentication, WebAuthn passkeys/device binding, facial verification & liveness evaluation, network presence checks, and tamper-evident audit chains.

---

## Table of Contents
- [Overview](#overview)
- [Key Capabilities](#key-capabilities)
- [Security Modes](#security-modes)
  - [Legacy Mode](#legacy-mode)
  - [Secure Presence Phase 2 (V2)](#secure-presence-phase-2-v2)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Installation and Setup](#installation-and-setup)
- [Configuration & Feature Flags](#configuration--feature-flags)
- [Automated & Manual Testing](#automated--manual-testing)
- [Threat Model & Residual Risks](#threat-model--residual-risks)
- [Architecture Document](#architecture-document)

---

## Overview
Traditional attendance systems are vulnerable to proxy attendance, remote relays, and tampering. This project provides multi-proof verification before attendance is accepted:
1. Authenticated user account (`student` / `professor`)
2. Approved classroom hotspot/subnet location
3. Active presence heartbeats
4. Server-verified biometric match & injectable liveness evaluation
5. WebAuthn passkey assertion (hardware/OS-backed)
6. Canonical SHA-256 audit hash chain signed by professor key

---

## Key Capabilities
- **Dual Security Modes:** Support legacy browser-key sessions while deploying Secure Presence Phase 2 (V2).
- **WebAuthn / Passkey Support:** Enrol hardware/OS-backed authenticators (`userVerification="required"`).
- **Decoupled Injectable Liveness Interface:** Clean `LivenessVerifier` protocol that fails closed if unconfigured.
- **HTTP Presence Heartbeats:** Lightweight polling to maintain active local presence over classroom LAN.
- **Strict State Machine:** `AttendanceAttempt` ensures signing challenges are issued only after server-recorded liveness success.
- **Canonical Hash Chain:** Audit log linking each record to a canonical JSON representation signed by the professor's key.
- **Concurrency & Replay Controls:** Database `UniqueConstraint` on `(student, session)` preventing double-record insertion.

---

## Security Modes

### Legacy Mode (`legacy`)
- Default mode for backward compatibility.
- Uses browser-generated ECDSA P-256 keys saved in `localStorage`.
- Student signs a session-wide network nonce.

### Secure Presence Phase 2 (V2) (`secure_presence_v2`)
- Upgraded protocol providing zero browser-exported private key leakage.
- Multi-step protocol flow:
  1. **Start Attempt:** Student initiates attempt on active V2 session over allowed subnet.
  2. **Presence Heartbeat:** Server validates active HTTP heartbeat from student IP.
  3. **Server Liveness:** Camera image evaluated against enrolled profile via injectable `LivenessVerifier`.
  4. **Signing Challenge:** One-time WebAuthn challenge issued upon liveness success.
  5. **Passkey Assertion:** Student completes WebAuthn assertion prompt.
  6. **Atomic Submission:** Server verifies assertion, updates passkey counter, and appends signed audit entry.

---

## Technology Stack
- **Backend:** Python 3.10+, Django 5.2, Django REST Framework
- **Passkeys / WebAuthn:** `webauthn==2.5.0`
- **Security & Cryptography:** `cryptography==46.0.5`, `pyOpenSSL`, `cbor2`, `asn1crypto`
- **Biometrics:** `torch`, `facenet-pytorch`, `opencv-python`, `pillow` (loaded dynamically)
- **Database:** PostgreSQL (`psycopg2-binary`)
- **Reporting:** `openpyxl` (XLSX), CSV

---

## Installation and Setup

1. **Activate virtual environment:**
   ```powershell
   ..\venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Run database migrations:**
   ```powershell
   python manage.py migrate
   ```

4. **Run server:**
   ```powershell
   python manage.py runserver_plus 0.0.0.0:8000 --cert-file cert.crt --key-file cert.key
   ```

---

## Configuration & Feature Flags

Configured via environment variables or `secure_attendance/settings.py`:

| Setting | Default | Description |
| :--- | :--- | :--- |
| `SECURE_PRESENCE_V2_ENABLED` | `True` | Global feature flag enabling/disabling Secure V2 mode |
| `PRESENCE_HEARTBEAT_MAX_AGE_SECONDS` | `15` | Maximum age in seconds for valid HTTP heartbeats |
| `WEBAUTHN_RP_ID` | `"localhost"` | WebAuthn Relying Party ID |
| `WEBAUTHN_ORIGIN` | `"https://localhost:8000"` | WebAuthn allowed origin URL |
| `LIVENESS_VERIFIER_TYPE` | `"unconfigured"` | Liveness adapter (`"facenet"` or `"unconfigured"`) |

---

## Automated & Manual Testing

### Automated Test Suite
Run full test suite covering legacy regression and V2 protocol tests:
```powershell
python manage.py test core
```

### Deployment Check
```powershell
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
```

### Manual Smoke Test Steps
1. **Legacy Mode:** Professor creates legacy session -> student submits using legacy browser key -> check attendance record.
2. **Passkey Enrolment:** Student clicks "Enrol WebAuthn Passkey" -> completes browser OS passkey prompt.
3. **Secure V2 Mode:** Professor starts V2 session -> student starts attempt -> camera liveness frame evaluated -> passkey assertion signed -> attendance marked.
4. **Replay & Expiry Test:** Attempt to resubmit used assertion or expired challenge -> verify server rejection.
5. **Subnet Disconnect Test:** Disconnect from hotspot before final submit -> verify network restriction rejection.
6. **Audit Tampering Test:** Modify canonical report hash in database -> run professor integrity check -> verify failure detected.

---

## Threat Model & Residual Risks

> [!WARNING]
> - **Residual Real-Time Relay Risk:** While network subnet checks and HTTP heartbeats verify that the student's device is connected to the classroom LAN, they do **not** prove physical distance. A proxy student in the classroom could theoretically relay biometric frames or WebAuthn prompts to an off-site student over a custom tunnel.
> - **Fail-Closed Policy:** In Secure V2 mode, if the liveness verifier is unconfigured or unavailable, the system will fail closed to prevent unauthorized attendance.

---

## Architecture Document
For full sequence diagrams, detailed data models, state machines, and rollback procedures, refer to [SECURE_PRESENCE_V2.md](file:///d:/Project-%20Academic/Attendance/SECURE_PRESENCE_V2.md).
