# Sequence Diagrams — Secure Presence V2 Network Architecture Redesign

## 1. Agent Launch & Identity Registration

```mermaid
sequenceDiagram
    autonumber
    actor Prof as Professor Laptop
    participant Agent as Attendance Agent (Python)
    participant Django as Cloud Django Server

    Prof->>Agent: Run python -m attendance_agent
    Agent->>Agent: Load/Generate Ed25519 Keypair (~/.secure_attendance/agent_key.pem)
    Agent->>Django: POST /agent/register/ (Bearer token + Ed25519 Public Key)
    Django->>Django: Upsert AttendanceAgent record in DB
    Django-->>Agent: 200 OK { status: "ok", agent_id }
    Agent->>Agent: Start Heartbeat Thread (daemon) & Flask HTTP Server (:5000)
```

---

## 2. Session Initialization Flow

```mermaid
sequenceDiagram
    autonumber
    actor Prof as Professor
    participant Django as Django Server
    participant Agent as Attendance Agent (RAM)

    Prof->>Django: POST /teacher/start-session/ (Course Code)
    Django->>Django: Generate session_id & session_secret (32 random bytes)
    Django->>Django: Compute SHA256(session_secret)
    Django->>Django: Create AttendanceSession record (store secret hash ONLY)
    Django->>Agent: POST http://127.0.0.1:5000/start-session (Bearer token + session_secret_hex)
    Agent->>Agent: Store session_secret in RAM & initialize ChallengeStore
    Agent-->>Django: 200 OK { status: "ok" }
    Django-->>Prof: Redirect /teacher/dashboard/
```

---

## 3. Student Attendance Marking Flow

```mermaid
sequenceDiagram
    autonumber
    actor Student as Student Browser
    participant Agent as Attendance Agent (HTTP :5000 LAN)
    participant Django as Django Server (HTTPS :8000)

    Student->>Agent: GET http://192.168.137.1:5000/challenge?session_id=UUID
    Agent->>Agent: Generate random nonce, timestamp, HMAC-SHA256 proof
    Agent->>Agent: Sign payload with Ed25519 key
    Agent-->>Student: 200 OK { nonce, timestamp, proof, agent_sig }

    Student->>Django: POST /student/secure-v2/start-attempt/ { session_id, agent_nonce, agent_timestamp, agent_proof, agent_sig }
    Django->>Django: verify_agent_challenge(): check TTL, cache replay, verify Ed25519 signature
    Django-->>Student: 200 OK { attempt_id }

    rect rgb(240, 248, 255)
        note over Student, Django: Existing V2 Pipeline (Unchanged)
        Student->>Django: GET /student/secure-v2/liveness-challenge/
        Django-->>Student: 200 OK { liveness_challenge }
        Student->>Student: Interactive Camera Gesture / Liveness Check
        Student->>Django: POST /student/secure-v2/verify-liveness/
        Django-->>Student: 200 OK { liveness_passed }
        Student->>Django: POST /student/secure-v2/request-challenge/ (Passkey)
        Django-->>Student: 200 OK WebAuthn options
        Student->>Student: navigator.credentials.get() Passkey Prompt
        Student->>Django: POST /student/secure-v2/submit/
        Django->>Django: Verify WebAuthn signature + append to immutable audit ledger
        Django-->>Student: 200 OK { attendance_recorded }
    end
```

---

## 4. Heartbeat & Session Teardown

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Attendance Agent
    participant Django as Django Server

    loop Every 30 seconds
        Agent->>Django: POST /agent/heartbeat/ { agent_id, session_id, alive: true }
        Django->>Django: Update AttendanceAgent.last_heartbeat
        Django-->>Agent: 200 OK
    end

    alt Heartbeat Stops (Agent Closed / Laptop Disconnected)
        Django->>Django: Check last_heartbeat age > 90s
        Django->>Django: Automatically deactivate session (active = False)
    end
```
