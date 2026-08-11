# Detailed Setup & Execution Guide — Secure Attendance System (V3 Agent Architecture)

This document provides complete, step-by-step instructions for setting up, running, and troubleshooting the Secure Presence V3 Attendance System.

---

## 1. System Overview & Key Concepts

The system uses a **decoupled Network Verification Architecture**:

- **Django Server (HTTPS :8000)**: Serves the Web UI, handles login, face recognition, liveness verification, WebAuthn passkey assertion, and audit logging.
- **Attendance Agent (HTTP :5000)**: A lightweight background process (`attendance_agent`) running on the professor's laptop. It generates temporary, one-time cryptographic challenges over the local Wi-Fi hotspot (`http://192.168.137.1:5000/challenge`).
- **Why plain HTTP for the Agent?**: The Agent challenge is fetched locally over the hotspot LAN (`http://192.168.137.1:5000`). Because it is plain HTTP, **students do NOT need to install any Root CA certificates on their phones** for network presence verification!
- **Why `192-168-137-1.sslip.io` for Django?**: Browsers require WebAuthn (Passkeys) to run over trusted HTTPS using a domain name rather than a raw IP address. `192-168-137-1.sslip.io` is a public DNS domain that resolves to `192.168.137.1` (the laptop's hotspot IP).

---

## 2. One-Time Setup Instructions

Execute these steps once on the professor's laptop.

### Step A: Open PowerShell as Administrator / User
Open a terminal in the repository root (`D:\Project- Academic\Attendance`):

```powershell
cd "D:\Project- Academic\Attendance"
```

### Step B: Activate Virtual Environment
```powershell
.\venv\Scripts\Activate.ps1
```

### Step C: Install Package Dependencies
```powershell
# Install Django backend packages
pip install -r secure_attendance/requirements.txt

# Install Attendance Agent packages
pip install -r attendance_agent/requirements.txt
```

### Step D: Run Database Migrations
```powershell
cd secure_attendance
..\venv\Scripts\python.exe manage.py migrate
```

*This applies all database schemas including `0007_agent_network_verification.py`.*

---

## 3. Detailed Operational Steps (Every Class Session)

Follow these exact steps in order for every class session.

### Step 1: Turn ON Windows Mobile Hotspot
1. Press `Win + I` to open **Settings**.
2. Go to **Network & Internet** → **Mobile Hotspot**.
3. Toggle Mobile Hotspot to **ON**.
4. *(Default Windows Hotspot IP is `192.168.137.1`)*.

---

### Step 2: Start the Django Server (Terminal 1)
Open PowerShell Window #1:

```powershell
cd "D:\Project- Academic\Attendance\secure_attendance"
.\start_server.ps1
```

**Expected Output**:
```text
==================================================
  Secure Attendance System -- HTTPS Dev Server
==================================================
  Teacher and Students open:
  https://192-168-137-1.sslip.io:8000
```

---

### Step 3: Start the Attendance Agent (Terminal 2)
Open a **second** PowerShell Window #2:

```powershell
cd "D:\Project- Academic\Attendance"
..\venv\Scripts\python.exe -m attendance_agent --verbose
```

**Expected Output**:
```text
[INFO] Loaded config: Agent will listen on 0.0.0.0:5000
[INFO] Agent ID: <agent_id_prefix>
[INFO] Agent registered with Django successfully.
[INFO] Heartbeat thread started (interval=30s).
[INFO] Attendance Agent HTTP server starting on http://192.168.137.1:5000
```

> [!NOTE]
> The Agent automatically registers its Ed25519 identity key with Django. If Django was not ready when the Agent launched, the Agent will automatically retry registration every 30 seconds until connected.

---

### Step 4: Professor Starts Attendance Session
1. On the professor's laptop, open browser and navigate to:
   ```text
   https://192-168-137-1.sslip.io:8000
   ```
2. Log in with your **Professor** account.
3. Click **Start Attendance**.
4. Enter the **Course Code** (e.g., `CS201`) and click **Start Session**.
5. Django generates a 256-bit `session_secret` and pushes it to the Attendance Agent (`Session secret pushed to agent for session...`). The session is now active and ready for student attendance!

---

### Step 5: Students Mark Attendance on Phones

#### A. Connect to Hotspot Wi-Fi
Students open Wi-Fi settings on their mobile device and connect to the professor's Mobile Hotspot.

#### B. Open Dashboard
In Chrome (Android) or Safari (iOS), students open:
```text
https://192-168-137-1.sslip.io:8000
```

#### C. Submit Attendance
1. Student logs in with their account.
2. Tap **Submit Attendance**.
3. **Automated Step 1**: Browser fetches cryptographic network presence challenge from `http://192.168.137.1:5000/challenge?session_id=...` over local LAN.
4. **Interactive Step 2**: Complete face verification & liveness gesture prompt.
5. **Biometric Step 3**: Complete device Passkey prompt (fingerprint / Face ID / PIN).
6. **Success**: Attendance is verified cryptographically and logged to the tamper-evident audit ledger!

---

## 4. Architecture & Security Reference

```text
┌────────────────────────────────────────────────────────────────────────┐
│                         Professor's Laptop                             │
│                                                                        │
│   ┌─────────────────┐        HTTPS           ┌──────────────────────┐ │
│   │  Django Server  │◄──────────────────────►│  Attendance Agent    │ │
│   │  (HTTPS :8000)  │  /agent/heartbeat       │  (HTTP :5000)        │ │
│   │                 │  /agent/session         │                      │ │
│   │  - Passkey      │                         │  - Ed25519 identity  │ │
│   │  - Face/Liveness│                         │  - RAM-only secret   │ │
│   │  - Audit ledger │                         │  - HMAC challenges   │ │
│   └─────────────────┘                         └──────────┬───────────┘ │
│                                                          │              │
│                                                     HTTP :5000         │
│                                                          │              │
└──────────────────────────────────────────────────────────┼─────────────┘
                                                           │
                                              Wi-Fi Hotspot (LAN)
                                                           │
                                              ┌────────────┴────────────┐
                                              │     Student Phones      │
                                              │ 1. GET /challenge :5000 │
                                              │ 2. POST /submit   :8000 │
                                              └─────────────────────────┘
```

---

## 5. Troubleshooting Guide

| Issue / Error | Root Cause | Solution |
|---|---|---|
| `Network presence verification failed: agent_not_registered` | Session was started before Agent registered | 1. Ensure `python -m attendance_agent` is running in Terminal 2.<br>2. On Teacher Dashboard, click **Start Attendance** to create a fresh session.<br>3. Submit attendance again. |
| `generate_challenge: no active session for ... (404)` | Django did not push secret to Agent | Django pushes secrets when a session starts. Make sure to click **Start Attendance** in Teacher Dashboard after starting the Agent. |
| `Could not obtain Attendance Agent challenge` | Phone cannot reach `http://192.168.137.1:5000` | Verify student phone is connected to the professor's Wi-Fi hotspot. |
| `ATTENDANCE_AGENT_API_TOKEN mismatch` (401 Unauthorized) | Tokens differ between Agent and Django | Ensure token in `attendance_agent.toml` matches `ATTENDANCE_AGENT_API_TOKEN` in `settings.py` (both default to `secure_presence_v3_default_token`). |
| `ERR_NAME_NOT_RESOLVED` for `sslip.io` | Phone hotspot has no internet | Ensure laptop Mobile Hotspot has internet sharing enabled. |
| `Address already in use` | Old server instance running | Close extra PowerShell windows or run `taskkill /F /IM python.exe`. |

---

## 6. Project Documentation Links

Detailed technical specifications are available in the project files:

- [API Specification](file:///d:/Project-%20Academic/Attendance/attendance_agent/docs/api_spec.md)
- [Sequence Diagrams](file:///d:/Project-%20Academic/Attendance/attendance_agent/docs/sequence_diagrams.md)
- [Class Diagrams](file:///d:/Project-%20Academic/Attendance/attendance_agent/docs/class_diagrams.md)
- [Cryptographic Protocol](file:///d:/Project-%20Academic/Attendance/attendance_agent/docs/crypto_protocol.md)
- [Threat Model](file:///d:/Project-%20Academic/Attendance/attendance_agent/docs/threat_model.md)
- [Deployment Guide](file:///d:/Project-%20Academic/Attendance/attendance_agent/docs/deployment.md)
- [Migration Guide](file:///d:/Project-%20Academic/Attendance/attendance_agent/docs/migration.md)
