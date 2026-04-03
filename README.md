# Secure Attendance System

A security-focused classroom attendance platform built with Django. It is designed for hotspot/LAN classroom environments and combines authentication, device binding, facial verification, network checks, and tamper-evident attendance records.

## Table of Contents
- [Overview](#overview)
- [Key Capabilities](#key-capabilities)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation and Setup](#installation-and-setup)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [End-to-End User Flow](#end-to-end-user-flow)
- [Security and Cryptography Model](#security-and-cryptography-model)
- [Data Model](#data-model)
- [HTTP Routes](#http-routes)
- [Export and Reporting](#export-and-reporting)
- [Operational Notes](#operational-notes)
- [Troubleshooting](#troubleshooting)
- [Future Improvements](#future-improvements)

## Overview
Traditional attendance systems are vulnerable to proxy attendance and tampering. This project addresses that by requiring multiple proofs before attendance is accepted:
- authenticated account
- approved network location (hotspot/subnet)
- registered student device key
- biometric face match
- cryptographic nonce signature
- integrity-preserving record hashing

The project currently supports two operational user roles:
- `professor`: creates live attendance sessions and reviews/export records
- `student`: registers device/face and submits attendance

## Key Capabilities
- Custom user model with role-based behavior (`student` / `professor`)
- Live attendance sessions with expiry windows
- Hotspot/subnet-restricted attendance
- Device registration with browser-generated ECDSA key pair
- Nonce signing and signature verification for attendance submission
- Face registration and verification using FaceNet embeddings
- Hash-chain based attendance integrity verification
- CSV and XLSX export for attendance reports

## System Architecture
High-level components:
1. **Django Web Layer** (`core/views.py`, templates)
2. **Service Layer** (`core/session_service.py`, `core/attendance_service.py`, `core/student_service.py`)
3. **Cryptography Utilities** (`core/crypto_utils.py`)
4. **Network Enforcement Middleware** (`core/middleware.py`)
5. **Persistence Layer** (PostgreSQL via Django ORM models in `core/models.py`)
6. **Client Browser Layer** (Web Crypto + Camera capture in templates)

## Technology Stack
### Backend
- Python 3.x
- Django 5.2.x
- Django Extensions
- Django REST Framework (installed, not currently central to flow)

### Database
- PostgreSQL (`psycopg2-binary`)

### Security and Crypto
- `cryptography` library
- ECDSA P-256 (`SECP256R1`) for signatures
- AES-256-GCM for encrypted private-key storage
- SHA-256 for hashes/chaining/fingerprints

### Face Verification
- PyTorch
- `facenet-pytorch` (`MTCNN`, `InceptionResnetV1`)
- OpenCV
- NumPy
- Pillow

### Export
- CSV (Python stdlib)
- XLSX (`openpyxl`)

## Project Structure

```text
Attendance/
|-- requirements.txt
|-- steps.txt
|-- secure_attendance/
|   |-- manage.py
|   |-- secure_attendance/
|   |   |-- settings.py
|   |   |-- urls.py
|   |   |-- asgi.py
|   |   `-- wsgi.py
|   |-- core/
|   |   |-- models.py
|   |   |-- views.py
|   |   |-- middleware.py
|   |   |-- crypto_utils.py
|   |   |-- session_service.py
|   |   |-- attendance_service.py
|   |   |-- student_service.py
|   |   |-- templates/
|   |   `-- migrations/
|   `-- embeddings/
`-- venv/
```

## Prerequisites
- Python 3.10+ recommended
- PostgreSQL instance
- Camera access on student devices
- Hotspot/LAN setup for local classroom operation
- OpenSSL-compatible certificate PEM for HTTPS local serving (recommended for camera/Web Crypto reliability)

## Installation and Setup

### 1. Clone repository
```bash
git clone <your-repo-url>
cd Attendance
```

### 2. Create and activate virtual environment
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
Create a `.env` file in `secure_attendance/` (same level as `manage.py`) with values similar to:

```env
SECRET_KEY=your-django-secret-key
DEBUG=True

DB_NAME=attendance_db
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432

# Base64-encoded 32-byte AES key
AES_MASTER_KEY=your-base64-encoded-32-byte-key
```

### 5. Run migrations
```bash
cd secure_attendance
python manage.py migrate
```

### 6. Create superuser (professor/admin)
```bash
python manage.py createsuperuser
```

## Configuration
Important settings are in `secure_attendance/secure_attendance/settings.py`:
- `AUTH_USER_MODEL = 'core.User'`
- PostgreSQL database config loaded from `.env`
- middleware includes `core.middleware.HotspotRestrictionMiddleware`
- timezone: `Asia/Kolkata`

## Running the Application
From `secure_attendance/` directory:

### Standard local run
```bash
python manage.py runserver
```

### Classroom hotspot/HTTPS run (as documented in project)
```bash
python manage.py runserver_plus 0.0.0.0:8000 --cert-file 192.168.137.1+2.pem
```

Then open:
- `https://192.168.137.1:8000` (example hotspot IP)

## End-to-End User Flow

### Professor flow
1. Login
2. Open Teacher Dashboard
3. Start new session (`course_code`)
4. Session is created with nonce, expiry, subnet, and signature
5. Monitor attendance records
6. Run integrity verification
7. Export attendance CSV/XLSX

### Student flow
1. Login
2. (First time) Register device (browser key pair generated)
3. (First time) Register face embedding
4. View active sessions
5. Capture face for verification
6. If face passes, sign session nonce with private key
7. Submit attendance
8. Receive success/error response

## Security and Cryptography Model

### 1. Authentication and authorization
- Django session auth (`authenticate`, `login`, `logout`)
- role-based controls for teacher/student actions

### 2. Network enforcement
- Active session stores:
  - `gateway_ip`
  - `subnet_range`
- Middleware and submit service validate student IP against session subnet

### 3. Device binding
- Student browser creates ECDSA P-256 key pair
- Public key stored in DB (`Device.public_key`)
- Private key remains client-side (currently browser localStorage)

### 4. Nonce signature verification
- Session includes random `network_nonce`
- Student signs nonce with device private key
- Server verifies signature using registered public key

### 5. At-rest protection
- Professor private key encrypted with AES-GCM (`private_key_encrypted`)
- AES key loaded from `AES_MASTER_KEY`

### 6. Integrity chain
- `record_hash = SHA256(student_id + session_id)`
- `chained_hash` links each attendance record to previous one
- `verify_session_integrity` recomputes and validates chain

### 7. Face verification
- Face detection: MTCNN
- Embedding generation: InceptionResnetV1
- Matching: cosine similarity against stored embedding (`> 0.7` threshold)

## Data Model
Main entities in `core/models.py`:

- `User`
  - custom auth model
  - fields include `email`, `role`, `public_key`, `private_key_encrypted`

- `AttendanceSession`
  - session metadata: `course_code`, `expiry`, `network_nonce`, `gateway_ip`, `subnet_range`, `session_signature`, `active`

- `Device`
  - student registered device key and fingerprint

- `StudentProfile`
  - encrypted face embedding field (present in model)

- `AttendanceRecord`
  - attendance entries with `record_hash` and `chained_hash`

## HTTP Routes
Configured in `secure_attendance/secure_attendance/urls.py`.

### Authentication
- `GET/POST /` -> login
- `GET /logout/` -> logout

### Professor
- `GET /teacher/dashboard/`
- `GET/POST /teacher/start-session/`
- `GET /teacher/verify/<uuid:session_id>/`
- `GET /teacher/export-csv/<uuid:session_id>/`
- `GET /teacher/export-xlsx/<uuid:session_id>/`

### Student
- `GET /student/dashboard/`
- `GET/POST /student/register-device/`
- `POST /student/register-face/`
- `POST /student/face-verify/`
- `POST /student/submit/`

## Export and Reporting
Professor can export per-session attendance reports:
- CSV: student email, localized timestamp, client IP
- XLSX: same fields using `openpyxl`

## Operational Notes
- Project is intended for controlled classroom networks (hotspot/LAN).
- Ensure camera permissions are granted in browser.
- Keep `AES_MASTER_KEY` secure and never commit `.env`.
- `embeddings/` directory stores face embedding `.npy` files by user UUID.

## Troubleshooting

### Login fails
- Verify user exists and password is correct.
- Confirm database connection settings in `.env`.

### Attendance submission returns network/hotspot error
- Confirm student device is connected to correct hotspot.
- Confirm server is accessed through hotspot IP.

### Face verification fails
- Ensure face was registered first.
- Improve lighting and camera framing.
- Confirm `embeddings/<student_id>.npy` exists.

### Signature verification fails
- Ensure device was registered before attendance submission.
- Do not clear browser storage between registration and submit.

### Export not working
- Check professor ownership of session.
- Ensure attendance records exist for selected session.

## Future Improvements
- Enforce MFA (TOTP utilities exist but are not integrated into login)
- Add stronger production hardening:
  - strict `ALLOWED_HOSTS`
  - secure cookie flags
  - HSTS/HTTPS redirects
- Add rate limiting and lockout policies
- Move student private-key storage from localStorage to more secure keystore approach
- Unify biometric storage strategy (DB-encrypted vs filesystem embeddings)
- Add automated tests for security-critical flows

---

If you are onboarding as a developer, start by reading these files in order:
1. `secure_attendance/secure_attendance/urls.py`
2. `secure_attendance/core/views.py`
3. `secure_attendance/core/attendance_service.py`
4. `secure_attendance/core/session_service.py`
5. `secure_attendance/core/crypto_utils.py`
6. `secure_attendance/core/models.py`
