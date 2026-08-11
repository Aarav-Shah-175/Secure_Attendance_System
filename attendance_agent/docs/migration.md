# Migration Guide — Upgrading to V3 Agent-Based Network Verification

## 1. DB Migration Summary

Migration `0007_agent_network_verification.py` applies the following changes:
- `AttendanceAgent` table created (stores Ed25519 identity keys and heartbeats).
- `AttendanceSession.session_secret_hash` added (stores `SHA256(session_secret)`).
- `AttendanceSession.agent_id` added.
- `AttendanceSession.gateway_ip` altered to `null=True, blank=True`.
- `AttendanceSession.subnet_range` altered to `default='agent'`.
- `AttendanceAttempt.agent_challenge_nonce`, `agent_challenge_ts`, `agent_proof_verified` added.

Existing historical attendance records and session records are **100% preserved**.

---

## 2. Code Changes & Removals

| Component | Status | Action Taken |
|---|---|---|
| `verify_network_subnet()` | **REMOVED** | Removed from `presence_service.py`. Subnet matching is no longer performed. |
| `HotspotRestrictionMiddleware` | **REMOVED** | Removed from `middleware.py` and `MIDDLEWARE` list in `settings.py`. |
| `get_local_hotspot_ip()` | **REMOVED** | Removed IP detection from `session_service.py` and `views.py`. |
| `start_session` view | **UPDATED** | Removed runtime IP socket lookup. Session creation now triggers `_push_secret_to_agent()`. |
| `start_attempt_v2` view | **UPDATED** | Accepts `agent_nonce`, `agent_timestamp`, `agent_proof`, `agent_sig` from student browser. |
| Root CA Certificate Requirement | **REMOVED for Agent** | Agent communicates via HTTP (`http://192.168.137.1:5000`). Root CA is no longer needed on student phones to fetch challenges. |

---

## 3. Step-by-Step Rollout Checklist

1. **Run Migration**:
   ```powershell
   python manage.py migrate core
   ```
2. **Update Environment**:
   Set `ATTENDANCE_AGENT_API_TOKEN` in `.env`.
3. **Deploy Attendance Agent**:
   Ensure `attendance_agent` package is installed on professor machines.
4. **Test Session Lifecycle**:
   Start attendance session in Professor Dashboard → verify Agent receives session_secret.
5. **Test Student Attendance**:
   Submit attendance from student phone → confirm challenge fetched from Agent over LAN HTTP and verified by Django over HTTPS.
