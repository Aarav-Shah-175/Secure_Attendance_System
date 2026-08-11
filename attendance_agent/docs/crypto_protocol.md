# Cryptographic Protocol Documentation

## 1. Overview & Security Goals

The redesigned network verification architecture enforces physical presence on a Wi-Fi hotspot without inspecting IP addresses or subnets.

### Primary Goals
1. **Physical Presence Verification**: Prove student is connected to the professor's hotspot LAN when fetching a challenge.
2. **Replay Protection**: Challenge nonces are single-use with a 30-second TTL.
3. **Identity & Non-Repudiation**: Attendance Agent signs challenges with Ed25519; Django verifies signature.
4. **Secret Confidentiality**: Session secret plaintext is stored ONLY in RAM on the Agent and never written to disk or stored in Django DB.

---

## 2. Cryptographic Primitives

| Primitive | Usage | Algorithm |
|---|---|---|
| Agent Identity | Keypair for agent signature | **Ed25519** (RFC 8032) |
| Session Secret | High-entropy session key | **256-bit CSPRNG** (`secrets.token_bytes(32)`) |
| Challenge Proof | Proof of session secret knowledge | **HMAC-SHA256** |
| Session Secret Hash | Database representation | **SHA-256** |
| Agent Signature | Proof of Agent challenge issuance | **Ed25519 Signature** |

---

## 3. Protocol Execution Steps

### Step 1: Agent Registration
- Agent generates Ed25519 keypair on first run (`agent_key.pem`, `agent_pub.pem`).
- `agent_id = SHA256(public_key_pem)[:16]`.
- Agent POSTs `public_key_pem` to Django `/agent/register/`.
- Django stores `AttendanceAgent(agent_id, public_key_pem)`.

### Step 2: Session Creation & Secret Distribution
1. Django generates `session_secret = secrets.token_bytes(32)`.
2. Django computes `session_secret_hash = SHA256(session_secret.hex())`.
3. Django stores `session_secret_hash` in `AttendanceSession` (DB).
4. Django sends `session_secret` to Agent via `POST /start-session` over local HTTP/HTTPS carrying Bearer token.
5. Agent stores `session_secret` in RAM (`SessionState`).

### Step 3: Challenge Issuance (Agent → Student over LAN HTTP)
1. Student browser GETs `http://192.168.137.1:5000/challenge?session_id=...`.
2. Agent generates `nonce = secrets.token_hex(16)` (128 bits random).
3. Agent gets current Unix timestamp `ts`.
4. Agent computes `proof = HMAC-SHA256(session_secret, nonce || ":" || ts || ":" || session_id)`.
5. Agent signs `payload = nonce || ":" || ts || ":" || session_id || ":" || proof` with Ed25519 private key → `agent_sig`.
6. Agent stores `nonce` in `ChallengeStore` with 30s TTL.
7. Agent returns `{ nonce, timestamp, proof, agent_sig, session_id, ttl }`.

### Step 4: Submission Verification (Django)
1. Student submits payload to Django `POST /student/secure-v2/start-attempt/`:
   `{ session_id, agent_nonce, agent_timestamp, agent_proof, agent_sig }`.
2. Django verifies:
   - `now - agent_timestamp <= 30s` (Freshness)
   - `agent_nonce` not in Django cache (Replay Protection)
   - `Ed25519_Verify(agent_pub_key, payload, agent_sig) == True` (Agent Authenticity & Message Integrity)
3. Django marks `agent_nonce` in cache for 60s.
4. Attempt initialization proceeds to biometric & WebAuthn steps.
