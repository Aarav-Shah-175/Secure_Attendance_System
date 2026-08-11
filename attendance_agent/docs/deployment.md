# Deployment Guide — Attendance Agent & Production Cloud Setup

## 1. Local Development Setup (Professor Laptop)

### Prerequisites
- Python 3.10+
- `pip install -r attendance_agent/requirements.txt`

### Step-by-Step Setup

1. **Configure Agent**:
   Create or edit `attendance_agent.toml`:
   ```toml
   [agent]
   port = 5000
   host = "0.0.0.0"
   hotspot_ip = "192.168.137.1"
   key_dir = "~/.secure_attendance"
   challenge_ttl_seconds = 30
   heartbeat_interval_seconds = 30

   [django]
   url = "http://127.0.0.1:8000"
   api_token = "my_secret_token_123"
   verify_ssl = false
   ```

2. **Configure Django `.env` or Environment**:
   ```env
   ATTENDANCE_AGENT_URL=http://127.0.0.1:5000
   ATTENDANCE_AGENT_API_TOKEN=my_secret_token_123
   ```

3. **Start Django Server**:
   ```powershell
   python manage.py runserver 0.0.0.0:8000
   ```

4. **Start Attendance Agent**:
   ```powershell
   python -m attendance_agent --verbose
   ```

---

## 2. Cloud Production Deployment

### Architecture
- **Django Server**: Hosted on AWS EC2, DigitalOcean, Heroku, or GCP with HTTPS enabled (`https://attendance.example.com`).
- **Professor Laptop**: Connected to Mobile Hotspot. Runs Attendance Agent locally.

### Production Environment Variables

#### On Django Cloud Server (`.env`):
```env
SECURE_PRESENCE_V2_ENABLED=True
ATTENDANCE_AGENT_API_TOKEN=prod_random_bearer_token_987654321
ATTENDANCE_AGENT_CHALLENGE_TTL_SECONDS=30
ATTENDANCE_AGENT_HEARTBEAT_MAX_AGE_SECONDS=90
WEBAUTHN_RP_ID=attendance.example.com
WEBAUTHN_RP_NAME=Secure Presence V2
```

#### On Professor Laptop (`attendance_agent.toml`):
```toml
[agent]
port = 5000
host = "0.0.0.0"
hotspot_ip = "192.168.137.1"
key_dir = "~/.secure_attendance"

[django]
url = "https://attendance.example.com"
api_token = "prod_random_bearer_token_987654321"
verify_ssl = true
```

---

## 3. Verifying Production Readiness

1. Launch Agent on laptop: `python -m attendance_agent`.
2. Observe log: `Agent registered with Django successfully.`
3. Start session in Professor Dashboard.
4. Student connects phone to hotspot, opens `https://attendance.example.com`.
5. Student clicks **Mark Attendance**. Student browser fetches challenge from `http://192.168.137.1:5000/challenge` without Root CA requirement.
6. Attendance submitted to Django over HTTPS and verified cleanly.
