# Codebase Overview & System Architecture

## 1. Tech Stack & Infrastructure

| Layer | Technology / Library | Purpose & Details |
|---|---|---|
| **Framework & Language** | Python 3.x, Django 5.2, Django REST Framework 3.16 | Primary backend web application framework and REST API support. |
| **Database & ORM** | PostgreSQL (`psycopg2-binary`), Django ORM | Relational database storage; Django ORM for model definitions & migrations. |
| **Caching & Rate Limiting** | Django `LocMemCache` | Ephemeral state management, rate limiting, and challenge tracking. |
| **Biometrics & Liveness** | MediaPipe (`mediapipe`), PyTorch (`facenet-pytorch`), OpenCV (`opencv-python`), SciPy, NumPy, Pillow | Face mesh detection, liveness challenge verification, and face embedding processing. |
| **Authentication & Passkeys** | PyWebAuthn (`webauthn`), PyOTP, PyCryptodome, cryptography | FIDO2/WebAuthn credential registration & authentication, TOTP secrets, AES encryption, and ECDSA keypairs. |
| **Export & Tools** | `openpyxl`, `django-extensions` | Attendance record export to Excel (.xlsx) / CSV; development utility tools. |
| **Infrastructure / DNS** | Local Hotspot + TLS Certificates (`mkcert`), `sslip.io` | Domain binding for WebAuthn (`192-168-137-1.sslip.io`) over local Wi-Fi hotspot with HTTPS SSL termination. |

---

## 2. Architecture & Directory Blueprint

### Directory Layout

```
Attendance/
├── .env                                  # Environment variables (database, crypto keys, WebAuthn settings)
├── HOW_TO_RUN.md                         # Operational & hotspot SSL setup instructions
├── SECURE_PRESENCE_V2.md                 # Architecture documentation for V2 flow
├── requirements.txt                      # Python dependencies
├── secure_attendance/                    # Primary project working directory
│   ├── manage.py                         # Django management CLI
│   ├── start_server.ps1                  # PowerShell HTTPS startup script with SSL certs
│   ├── core/                             # Primary application app
│   │   ├── models.py                     # Database schemas & state choices
│   │   ├── views.py                      # Request handlers & API endpoints
│   │   ├── middleware.py                 # Hotspot IP restriction middleware
│   │   ├── rate_limit.py                 # Request rate limiter logic
│   │   ├── crypto_utils.py               # AES encryption & ECDSA key generation
│   │   ├── liveness.py                   # MediaPipe facial liveness verification algorithm
│   │   ├── liveness_challenge_service.py # Dynamic liveness challenge orchestration
│   │   ├── webauthn_service.py           # WebAuthn options & verification service
│   │   ├── secure_presence_v2_service.py # Secure Presence V2 orchestration pipeline
│   │   ├── audit_service.py              # Cryptographic audit ledger & hash-chaining service
│   │   ├── attendance_service.py         # Attendance session & record business logic
│   │   ├── presence_service.py           # Heartbeat & presence validation
│   │   ├── session_service.py            # Session management logic
│   │   ├── student_service.py            # Student profile & embedding management
│   │   ├── templates/                    # HTML views for Teacher & Student interfaces
│   │   └── tests/                        # Automated unit & integration tests
│   └── secure_attendance/                # Django project settings root
│       ├── settings.py                   # Global configuration & security parameters
│       ├── urls.py                       # Global URL routing blueprint
│       ├── asgi.py / wsgi.py             # Server gateway interfaces
```

### Business Logic & Routing Flow

1. **HTTP Request Arrival**: Request passes through `HotspotRestrictionMiddleware` to validate gateway IP boundaries.
2. **URL Dispatch**: `secure_attendance/urls.py` routes endpoint to specific controller views in `core/views.py`.
3. **Service Layer Execution**: Views delegate complex logic to modular services:
   - `secure_presence_v2_service.py` coordinates attempt state transitions.
   - `webauthn_service.py` handles FIDO2 registration & authentication.
   - `liveness.py` / `liveness_challenge_service.py` evaluates face landmarks via MediaPipe.
   - `audit_service.py` computes SHA-256 hash chains for tamper-evident audit logs.
4. **Persistence Layer**: Data models in `core/models.py` write to PostgreSQL database.

---

## 3. Data Models & State

### Primary Schemas & Entity Relationships

- **`User`** (`AbstractBaseUser`): Custom user model with roles (`student` vs `professor`), TOTP secrets, and encrypted ECDSA keypairs for professors.
- **`StudentProfile`**: 1-to-1 extension of `User` storing AES-encrypted face embeddings.
- **`AttendanceSession`**: Created by a Professor for a course code; stores network nonce, session ECDSA signature, gateway IP, subnet range, and security mode (`LEGACY` vs `SECURE_PRESENCE_V2`).
- **`PasskeyCredential`**: WebAuthn credential metadata (`credential_id`, `public_key`, signature counter) linked to a Student.
- **`AttendanceAttempt`**: Multi-step state machine tracking attendance attempts:
  - *States*: `PENDING` $\rightarrow$ `LIVENESS_PENDING` $\rightarrow$ `BIOMETRIC_VERIFIED` $\rightarrow$ `CHALLENGE_ISSUED` $\rightarrow$ `SIGNED` $\rightarrow$ `ACCEPTED` (or `REJECTED`/`EXPIRED`).
- **`LivenessVerification`**: 1-to-1 relation with `AttendanceAttempt` storing liveness result status (`PASSED`/`FAILED`), score, verifier name, and reason codes.
- **`PresenceHeartbeat`**: Periodic ping records linking a student attempt to their client IP to prevent remote proxying.
- **`AttendanceRecord`**: Immutable record created upon successful attempt verification, constrained by `(student, session)` uniqueness, containing single and chained hashes.
- **`AttendanceAuditEntry` & `AttendanceSessionAuditRoot`**: Cryptographic ledger storing canonical SHA-256 hashes and signed roots for verifiable audit trails.

### State Strategy

- **Database State**: Persistent user credentials, passkey metadata, finalized attendance records, and audit chains in PostgreSQL.
- **Ephemeral State**: In-memory cache (`LocMemCache`) for rate limiting counters, WebAuthn challenge tokens, and active heartbeat timers.

---

## 4. Environment & Execution

### Key Environment Variables (`.env`)

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django application secret key |
| `DEBUG` | Boolean flag for Django debug mode |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection parameters |
| `AES_MASTER_KEY` | Base64 master key for symmetric payload encryption |
| `SECURE_PRESENCE_V2_ENABLED` | Feature flag enabling V2 WebAuthn & liveness pipeline |
| `PRESENCE_HEARTBEAT_MAX_AGE_SECONDS` | Maximum allowed threshold for active presence heartbeats |
| `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGIN` | WebAuthn Relying Party ID (e.g. `192-168-137-1.sslip.io`) and HTTPS origin URL |
| `LIVENESS_VERIFIER_TYPE` | Engine type for face liveness detection (default: `mediapipe`) |

### Local Run Setup

1. **Activate Virtual Environment**:
   ```powershell
   ..\venv\Scripts\Activate.ps1
   ```
2. **Apply Database Migrations**:
   ```powershell
   python manage.py migrate
   ```
3. **Launch HTTPS Server**:
   ```powershell
   cd secure_attendance
   .\start_server.ps1
   ```

---

## 5. Code Patterns & Standards

- **Service-Oriented Core Architecture**: Views act strictly as HTTP controllers, delegating logic to dedicated service modules (`audit_service`, `webauthn_service`, `secure_presence_v2_service`).
- **Cryptographic Tamper-Evidence**: High security enforced via ECDSA session signing and SHA-256 hash-chaining (`AttendanceAuditEntry`) to prevent retroactive record modification.
- **Subnet & Hotspot Binding**: Hardware/network boundary enforcement via custom `HotspotRestrictionMiddleware` ensuring clients operate within designated Wi-Fi hotspot subnet ranges.
- **Biometric Passkey Authentication**: FIDO2/WebAuthn standard integration eliminating plain text credentials in favor of device-bound hardware authenticators.
- **Multi-Factor Liveness Verification**: Computer vision pipeline using MediaPipe face landmarks to verify physical presence prior to passkey challenge issuance.
