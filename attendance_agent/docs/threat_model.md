# Threat Model & Attack Analysis — Secure Presence V2 Agent Architecture

## 1. Threat Matrix & Mitigations

| Threat Vector | Attack Scenario | Mitigation Strategy | Risk Level |
|---|---|---|---|
| **Replay Attack** | Attacker intercepts a student's challenge and reuses it from remote location. | 1. Agent enforces one-time use of `nonce` via `ChallengeStore`.<br>2. Django enforces one-time cache check (`NONCE_CACHE_PREFIX`).<br>3. Nonce TTL enforced at 30 seconds. | **Mitigated** (Low) |
| **Rogue Agent Impersonation** | Malicious actor sets up a fake local server on port 5000 to issue fake challenges. | Django verifies `agent_sig` using the professor's registered Ed25519 public key. A fake agent cannot produce a valid signature. | **Mitigated** (Low) |
| **Remote Proxy / VPN Bypass** | Student at home proxies HTTP request through classmate's phone to fetch challenge. | The WebAuthn passkey assertion + face verification + liveness check must also pass on the same device. Proxied network challenge without student's physical passkey/face fails at Step 4/7. | **Mitigated** (Low) |
| **Secret Leakage (DB Compromise)** | Adversary dumps Django database or database backup. | Database stores ONLY `SHA256(session_secret)`. Plaintext `session_secret` is held strictly in RAM on Agent and destroyed on session stop. | **Mitigated** (Low) |
| **MITM on LAN (Student ↔ Agent)** | Attacker modifies challenge parameters in flight on HTTP LAN. | Agent signs `nonce:ts:session_id:proof` with Ed25519. Any tampering invalidates `agent_sig` on Django side. | **Mitigated** (Low) |
| **Heartbeat Spoofing** | Attacker sends fake heartbeats to keep dead session open. | Heartbeat endpoint requires pre-shared `ATTENDANCE_AGENT_API_TOKEN` bearer header. | **Mitigated** (Low) |

---

## 2. Replay Attack Analysis

- **Condition**: Nonce reused within TTL (30s) or after TTL.
- **Agent Action**: `ChallengeStore.verify_and_consume()` marks `used = True` on first call. Subsequent calls return `replay_attack`.
- **Django Action**: `cache.get(f"agent_nonce_used:{nonce}")` returns `True` if already used, rejecting request immediately.

---

## 3. MITM Analysis

- Communication between Student and Agent is plain HTTP over local Wi-Fi hotspot.
- Since HTTPS is not used for the Agent (eliminating Root CA install requirement), an attacker could eavesdrop on HTTP LAN traffic.
- **Impact Analysis**: An eavesdropper can read `(nonce, ts, proof, agent_sig)`. However, the nonce is consumed upon first use by the legitimate student. By the time the attacker re-transmits the intercepted payload to Django, Django rejects it as a replay.

---

## 4. Secret Leakage Analysis

- Plaintext `session_secret` is created via `secrets.token_bytes(32)`.
- It exists ONLY in:
  1. Django memory briefly during session creation.
  2. Agent RAM (`SessionState`) during session lifetime.
- On session expiration/stop:
  - Agent zeroizes secret memory (`ctypes.memmove`).
  - Secret is purged from RAM.
- Even if Django DB is leaked, the attacker obtains `session_secret_hash` (SHA-256), which is pre-image resistant.
