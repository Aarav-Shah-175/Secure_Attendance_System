# REST API Specification — Attendance Agent & Django Endpoints

## Overview

The Attendance Agent architecture decouples network verification from Django.
It introduces two categories of APIs:
1. **Attendance Agent Endpoints** (hosted on local HTTP server, default port 5000)
2. **Django Agent Management Endpoints** (hosted on HTTPS Django server)

---

## 1. Attendance Agent Endpoints (Local LAN - HTTP :5000)

### 1.1 `GET /status`
- **Description**: Returns agent status, agent ID, active sessions, and server timestamp.
- **Access**: Public / Unauthenticated
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "agent_id": "a1b2c3d4e5f67890",
    "active_sessions": ["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    "timestamp": 1770000000
  }
  ```

### 1.2 `GET /health`
- **Description**: Lightweight health probe for monitoring.
- **Access**: Public / Unauthenticated
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "agent_id": "a1b2c3d4e5f67890"
  }
  ```

### 1.3 `GET /challenge?session_id=<UUID>`
- **Description**: Called by student browser over local HTTP to fetch a cryptographic proof of LAN presence.
- **Access**: Public / CORS enabled
- **Query Parameters**:
  - `session_id` (string, required): Active attendance session UUID.
- **Response `200 OK`**:
  ```json
  {
    "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "nonce": "7f8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d",
    "timestamp": 1770000015,
    "proof": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "agent_sig": "3045022100...",
    "ttl": 30
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: `{"error": "session_id is required"}`
  - `404 Not Found`: `{"error": "No active session found. Session may have expired or not started."}`

### 1.4 `POST /start-session`
- **Description**: Called by Django to push a session_secret to the Agent when a professor starts attendance.
- **Access**: Auth-Gated (Bearer `ATTENDANCE_AGENT_API_TOKEN`)
- **Request Body**:
  ```json
  {
    "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "session_secret_hex": "4a7f9b...",
    "expires_at": 1770001800.0
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

### 1.5 `POST /stop-session`
- **Description**: Called by Django when a session is closed or expired to destroy RAM secrets.
- **Access**: Auth-Gated (Bearer `ATTENDANCE_AGENT_API_TOKEN`)
- **Request Body**:
  ```json
  {
    "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

---

## 2. Django Agent Management Endpoints (HTTPS Server)

### 2.1 `POST /agent/register/`
- **Description**: Agent registers its Ed25519 identity (public key) with Django upon launch.
- **Access**: Bearer `ATTENDANCE_AGENT_API_TOKEN`
- **Request Body**:
  ```json
  {
    "agent_id": "a1b2c3d4e5f67890",
    "public_key_pem": "-----BEGIN PUBLIC KEY-----\n..."
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "action": "registered",
    "agent_id": "a1b2c3d4e5f67890"
  }
  ```

### 2.2 `POST /agent/heartbeat/`
- **Description**: Agent sends periodic heartbeat to Django every 30s for each active session.
- **Access**: Bearer `ATTENDANCE_AGENT_API_TOKEN`
- **Request Body**:
  ```json
  {
    "agent_id": "a1b2c3d4e5f67890",
    "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "alive": true
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

### 2.3 `POST /agent/stop-session/`
- **Description**: Django endpoint to mark session as inactive.
- **Access**: Bearer `ATTENDANCE_AGENT_API_TOKEN`
- **Request Body**:
  ```json
  {
    "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "closed": true
  }
  ```
