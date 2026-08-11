# Secure Presence V2 — Network Verification Architecture Redesign

## Summary

Replace the current subnet/IP-based network verification in Django with a standalone **Attendance Agent** process that runs on the professor's laptop. The Agent holds short-lived session secrets in RAM, issues HMAC-SHA256 cryptographic challenges to students, and heartbeats to Django to confirm session liveness. Django verifies cryptographic proofs, never touching hotspot IPs again.

All other functionality (face registration, liveness, WebAuthn, dashboards, session history, admin panel, audit ledger) is preserved exactly.

---

## Key Design Decisions

> [!IMPORTANT]
> **Backward Compatibility**: The existing `AttendanceSession` model keeps `gateway_ip` and `subnet_range` fields so existing data is not broken. They are simply no longer used for verification.

> [!IMPORTANT]
> **No WebAuthn origin change**: The student still visits `https://192-168-137-1.sslip.io:8000`. The Agent runs on a separate HTTP port (5000) on the hotspot. The browser fetches challenge from Agent via `http://192.168.137.1:5000/challenge` before the HTTPS submission to Django.

> [!WARNING]
> **Root CA Dependency**: The Agent communicates over plain HTTP on the LAN — students no longer need the Root CA to talk to the Agent. Django communication (heartbeat) goes over HTTPS. The `rootCA.crt` remains required for the WebAuthn HTTPS origin but is no longer a student-side concern for challenge fetching.

---

## Open Questions

> [!IMPORTANT]
> 1. Should the Agent support mDNS advertisement (`http://attendance.local/`)? This would let students use a friendly name instead of an IP address.
> 2. Should the Agent be packaged as a Windows `.exe` (PyInstaller) for ease of deployment, or kept as a plain Python script?
> 3. How long should session_secret challenge tokens be valid? Prompt says 30 seconds — confirm before implementing.
> 4. The new `start_session` flow requires Django to securely push `session_secret` to the Agent. Should this use a pre-shared HTTPS bearer token stored in `.env`, or should it use the Agent's Ed25519 public key for encryption?

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                         Professor's Laptop                             │
│                                                                        │
│   ┌─────────────────┐        HTTPS           ┌──────────────────────┐ │
│   │  Django Server  │◄──────────────────────►│  Attendance Agent    │ │
│   │  (HTTPS :8000)  │  /agent/heartbeat       │  (HTTP :5000)        │ │
│   │                 │  /agent/session         │                      │ │
│   │  - All auth     │                         │  - Ed25519 identity  │ │
│   │  - Passkey      │                         │  - RAM-only secret   │ │
│   │  - Face/Liveness│                         │  - HMAC challenges   │ │
│   │  - Audit ledger │                         │  - Heartbeat sender  │ │
│   └─────────────────┘                         └──────────┬───────────┘ │
│                                                          │              │
│                                                     HTTP :5000         │
│                                                          │              │
└──────────────────────────────────────────────────────────┼─────────────┘
                                                           │
                                              Wi-Fi Hotspot (LAN)
                                                           │
                               ┌───────────────────────────┼──────────────────────────────┐
                               │                           │                              │
                    ┌──────────┴────────┐       ┌──────────┴────────┐        ┌────────────┴────────┐
                    │   Student Phone 1  │       │   Student Phone 2  │        │   Student Phone 3   │
                    │                   │       │                   │        │                     │
                    │ 1. GET /challenge  │       │ 1. GET /challenge  │        │ 1. GET /challenge   │
                    │    (HTTP :5000)   │       │    (HTTP :5000)   │        │    (HTTP :5000)     │
                    │ 2. POST /submit   │       │ 2. POST /submit   │        │ 2. POST /submit     │
                    │    (HTTPS :8000)  │       │    (HTTPS :8000)  │        │    (HTTPS :8000)    │
                    └───────────────────┘       └───────────────────┘        └─────────────────────┘
```

---

## Cryptographic Protocol

### Agent Identity (one-time setup)
1. On first launch, Agent generates an **Ed25519 keypair**.
2. Private key stored in `~/.secure_attendance/agent_key.pem` (file permission 600).
3. Agent registers its **public key** with Django via `POST /agent/register/`.
4. Django stores the public key in a new `AttendanceAgent` model.

### Session Secret (per session)
1. Django generates `session_secret = secrets.token_bytes(32)` when professor starts a session.
2. Django stores `SHA256(session_secret)` in DB (never the plaintext).
3. Django transmits `session_secret` (encrypted with Agent's Ed25519 public key → X25519 ECDH) to Agent via `POST /agent/session/`.
4. Agent stores `session_secret` in RAM only. Destroyed on session end/expiry.

### Challenge-Response (per attendance attempt)
```
Student           Agent (HTTP :5000)         Django (HTTPS :8000)
  |                       |                           |
  |--- GET /challenge ---->|                           |
  |                       | nonce = secrets.token_hex(16)
  |                       | ts = unix_timestamp()
  |                       | proof = HMAC-SHA256(session_secret,
  |                       |           nonce || ts || session_id)
  |<-- {nonce, ts, proof, agent_sig} ---|              |
  |                       |                           |
  |--- POST /submit ---------------------------------->|
  |   {session_id, challenge={nonce,ts,proof},         |
  |    passkey_assertion, liveness_nonce}              |
  |                       |                           |
  |                       |  Verify: HMAC-SHA256(SHA256(secret),
  |                       |            nonce||ts||session_id) == proof
  |                       |  Check: ts within 30s
  |                       |  Check: nonce not replayed (cache)
  |<----------------------------------------------- 200 OK
```

---

## Proposed Changes

---

### A. New Standalone Package: `attendance_agent/`

**Location**: `d:\Project- Academic\Attendance\attendance_agent\`

#### [NEW] `attendance_agent/__main__.py`
- Entry point. Reads config, starts Flask HTTP server on port 5000.

#### [NEW] `attendance_agent/agent.py`
- `AttendanceAgent` class:
  - `load_or_generate_identity()` — Ed25519 keypair management
  - `register_with_django(django_url, api_token)` — POST public key to Django
  - `start_session(session_id, encrypted_secret)` — decrypt and store in RAM
  - `stop_session(session_id)` — zeroize and remove secret
  - `generate_challenge(session_id)` — HMAC-SHA256 nonce
  - `validate_heartbeat_needed()` — heartbeat scheduler

#### [NEW] `attendance_agent/api.py`
- Flask routes:
  - `GET /status` — agent health and active sessions
  - `POST /start-session` — called by Django to push session secret
  - `POST /stop-session` — session expiry cleanup
  - `GET /challenge?session_id=<id>` — student challenge endpoint
  - `POST /heartbeat` — Agent → Django heartbeat sender (internal scheduler)

#### [NEW] `attendance_agent/crypto.py`
- `generate_ed25519_keypair()` — create and persist key
- `load_ed25519_private_key()` — load from disk
- `hmac_sha256(secret: bytes, message: str) -> str` — challenge proof
- `sign_challenge(private_key, payload: dict) -> str` — Ed25519 agent signature
- `decrypt_session_secret(private_key, ciphertext: bytes) -> bytes` — X25519 ECDH unwrap

#### [NEW] `attendance_agent/config.py`
- Reads from `attendance_agent.toml` or environment:
  - `DJANGO_URL`, `AGENT_API_TOKEN`, `AGENT_PORT`, `HOTSPOT_IP`

#### [NEW] `attendance_agent/challenge_store.py`
- In-memory store of issued challenges (nonce → expiry).
- `mark_used(nonce)` / `is_replay(nonce)` — one-time use enforcement.
- Auto-purges expired entries.

#### [NEW] `attendance_agent/heartbeat.py`
- Background thread that `POST`s to Django every 30 seconds.
- Payload: `{session_id, agent_id, alive: true}`.

#### [NEW] `attendance_agent/attendance_agent.toml` (config template)
```toml
[agent]
port = 5000
hotspot_ip = "192.168.137.1"

[django]
url = "https://192-168-137-1.sslip.io:8000"
api_token = "changeme"
verify_ssl = false  # set true in production with real cert
```

---

### B. Django — New Model

#### [MODIFY] [models.py](file:///d:/Project-%20Academic/Attendance/secure_attendance/core/models.py)
Add:
```python
class AttendanceAgent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    professor = models.OneToOneField(User, on_delete=models.CASCADE)
    public_key_pem = models.TextField()  # Ed25519 public key, PEM
    session_secret_hash = models.CharField(max_length=64, blank=True)  # SHA256(session_secret)
    last_heartbeat = models.DateTimeField(null=True)
    registered_at = models.DateTimeField(auto_now_add=True)
```

Add to `AttendanceAttempt`:
```python
agent_challenge_nonce = models.CharField(max_length=64, null=True, blank=True)
agent_challenge_ts = models.BigIntegerField(null=True, blank=True)
agent_proof_verified = models.BooleanField(default=False)
```

#### [NEW] Migration

---

### C. Django — New Views / Endpoints

#### [MODIFY] [views.py](file:///d:/Project-%20Academic/Attendance/secure_attendance/core/views.py)
Add Agent API endpoints (behind `api_token` bearer auth, not login_required):
- `POST /agent/register/` — receive and store Agent Ed25519 public key
- `POST /agent/session/` — receive encrypted `session_secret`, store `SHA256(session_secret)` in `AttendanceAgent.session_secret_hash`
- `POST /agent/heartbeat/` — update `AttendanceAgent.last_heartbeat`; auto-close session if heartbeat stops

Modify `start_session`:
- After creating `AttendanceSession`, generate `session_secret`, store its hash, push to Agent via internal HTTP call.
- Remove the hotspot IP detection block (`socket.getaddrinfo`, `192.168.137.1` hardcode).
- Pass `gateway_ip="agent"` and `subnet_range="agent"` as neutral placeholder values (DB schema unchanged).

#### [NEW] `core/agent_verification.py`
- `verify_agent_proof(session, nonce, timestamp, proof) -> bool`:
  - Recompute `HMAC-SHA256(SHA256(session_secret), nonce||ts||session_id)`.
  - Check timestamp within 30 seconds.
  - Check nonce not in Django-side replay cache.
  - Check agent signature (Ed25519 verify).
- `mark_nonce_used(nonce)` — store in cache for 60s.

---

### D. Django — Remove Network Verification

#### [MODIFY] [presence_service.py](file:///d:/Project-%20Academic/Attendance/secure_attendance/core/presence_service.py)
- **Remove** `verify_network_subnet()` and all its callers.
- `record_presence_heartbeat()` — mark heartbeats `valid=True` unconditionally (Agent presence is proven by the challenge, not by IP).
- `has_recent_valid_heartbeat()` — unchanged.

#### [MODIFY] [secure_presence_v2_service.py](file:///d:/Project-%20Academic/Attendance/secure_attendance/core/secure_presence_v2_service.py)
- `start_attendance_attempt()`: Remove `verify_network_subnet(client_ip, session)` call. Add `verify_agent_proof(session, nonce, ts, proof)`.
- `submit_attendance_v2()`: Remove `verify_network_subnet(...)` and `has_recent_valid_heartbeat(...)` subnet-based block.

#### [MODIFY] [middleware.py](file:///d:/Project-%20Academic/Attendance/secure_attendance/core/middleware.py)
- **Remove** `HotspotRestrictionMiddleware` entirely (or convert to a no-op passthrough).

#### [MODIFY] [session_service.py](file:///d:/Project-%20Academic/Attendance/secure_attendance/core/session_service.py)
- **Remove** `get_local_hotspot_ip()`.
- `create_attendance_session()`: Remove `ipaddress.ip_network()` subnet computation. Accept `gateway_ip="agent"` placeholder.

---

### E. Django — urls.py

#### [MODIFY] [urls.py](file:///d:/Project-%20Academic/Attendance/secure_attendance/secure_attendance/urls.py)
Add:
```python
path('agent/register/', views.agent_register_view, name='agent_register'),
path('agent/session/', views.agent_session_view, name='agent_session'),
path('agent/heartbeat/', views.agent_heartbeat_view, name='agent_heartbeat'),
```

---

### F. Student Browser — Challenge Fetch

#### [MODIFY] [student_dashboard.html](file:///d:/Project-%20Academic/Attendance/secure_attendance/core/templates/student_dashboard.html)
In `submitAttendanceV2()`, before the start-attempt call:
```js
// 1. Fetch challenge from Agent over HTTP (LAN)
const agentBase = "http://192.168.137.1:5000";
const challengeRes = await fetch(`${agentBase}/challenge?session_id=${sessionId}`);
const challengeData = await challengeRes.json();
// challengeData: { nonce, timestamp, proof, agent_sig }

// 2. Include challenge in start-attempt payload
const startRes = await fetch("/student/secure-v2/start-attempt/", {
    body: JSON.stringify({
        session_id: sessionId,
        agent_nonce: challengeData.nonce,
        agent_timestamp: challengeData.timestamp,
        agent_proof: challengeData.proof,
        agent_sig: challengeData.agent_sig,
    })
});
```

---

### G. Settings

#### [MODIFY] [settings.py](file:///d:/Project-%20Academic/Attendance/secure_attendance/secure_attendance/settings.py)
Add:
```python
ATTENDANCE_AGENT_API_TOKEN = os.getenv("ATTENDANCE_AGENT_API_TOKEN", "")
ATTENDANCE_AGENT_CHALLENGE_TTL_SECONDS = 30
ATTENDANCE_AGENT_HEARTBEAT_MAX_AGE_SECONDS = 90  # 3 missed heartbeats before session dies
```

Remove from `settings.py`:
- `PRESENCE_HEARTBEAT_MAX_AGE_SECONDS` (absorbed into Agent heartbeat logic)

---

## Documentation Deliverables (saved as files)

After implementation:

| # | Artifact | Path |
|---|---|---|
| 1 | REST API Spec | `attendance_agent/docs/api_spec.md` |
| 2 | Sequence Diagrams | `attendance_agent/docs/sequence_diagrams.md` |
| 3 | Class Diagrams | `attendance_agent/docs/class_diagrams.md` |
| 4 | Cryptographic Protocol | `attendance_agent/docs/crypto_protocol.md` |
| 5 | Threat Model | `attendance_agent/docs/threat_model.md` |
| 6 | Deployment Guide | `attendance_agent/docs/deployment.md` |
| 7 | Dev Guide | `attendance_agent/docs/dev_guide.md` |
| 8 | Migration Guide | `attendance_agent/docs/migration.md` |

---

## Verification Plan

### Automated Tests
```powershell
# Django system check
..\venv\Scripts\python.exe manage.py check

# Django migration check
..\venv\Scripts\python.exe manage.py migrate --check

# Unit tests
..\venv\Scripts\python.exe manage.py test core.tests
```

### Manual Verification
1. Start Django server + Attendance Agent.
2. Professor starts a session — confirm Agent receives `session_secret` push.
3. On student phone, open `https://192-168-137-1.sslip.io:8000/student/dashboard/` and tap **Mark Attendance**.
4. Browser fetches `http://192.168.137.1:5000/challenge` — confirm challenge JSON received.
5. Submission completes — attendance recorded in DB.
6. Kill the Agent — confirm Django auto-closes the session after 90s (missed heartbeats).
7. Replay the same nonce — confirm 403 rejection.
