# Local Development Guide — Attendance Agent

## Quick Start

### 1. Install Dependencies
Make sure virtual environment is active:
```powershell
pip install -r attendance_agent/requirements.txt
```

### 2. Run Agent Standalone
To run the Attendance Agent with debug logging:
```powershell
python -m attendance_agent --verbose
```

### 3. Run Agent in Development Bypass Mode (without Django)
If testing student UI without Django:
```powershell
python -m attendance_agent --no-register --verbose
```

---

## Testing Endpoints Locally

### Check Health
```powershell
curl http://127.0.0.1:5000/health
```

### Check Agent Status
```powershell
curl http://127.0.0.1:5000/status
```

### Simulate Start Session Push (Django → Agent)
```powershell
curl -X POST http://127.0.0.1:5000/start-session `
  -H "Authorization: Bearer my_secret_token_123" `
  -H "Content-Type: application/json" `
  -d '{"session_id": "test-session-123", "session_secret_hex": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}'
```

### Fetch Challenge (Student Simulation)
```powershell
curl "http://127.0.0.1:5000/challenge?session_id=test-session-123"
```

---

## Unit Testing

Run Django backend tests:
```powershell
cd secure_attendance
python manage.py test core
```
