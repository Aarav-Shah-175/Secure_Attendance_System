# Secure Attendance System — AWS Cloud Operations & User Guide

> **Cloud Domain**: [https://13-127-69-218.sslip.io](https://13-127-69-218.sslip.io)  
> **Elastic IP**: `13.127.69.218`  
> **Architecture**: Docker Compose (Django + PostgreSQL `pgvector` + Caddy HTTPS Reverse Proxy)

---

## Table of Contents
1. [Prerequisites & System Architecture](#1-prerequisites--system-architecture)
2. [Starting the AWS Server (Turning On)](#2-starting-the-aws-server-turning-on)
3. [User Management & Registration](#3-user-management--registration)
   - [Registering an Admin / Superuser](#a-registering-an-admin--superuser)
   - [Registering a New Teacher / Professor](#b-registering-a-new-teacher--professor)
   - [Registering a New Student & Biometrics](#c-registering-a-new-student--biometrics)
4. [Conducting Attendance (Step-by-Step Flow)](#4-conducting-attendance-step-by-step-flow)
   - [Step A: Teacher Starts Session](#step-a-teacher-starts-session)
   - [Step B: Attendance Agent Proximity Check (Optional)](#step-b-attendance-agent-proximity-check-optional)
   - [Step C: Student Submits Attendance (Mobile Phone)](#step-c-student-submits-attendance-mobile-phone)
5. [Viewing & Exporting Attendance Reports](#5-viewing--exporting-attendance-reports)
6. [Shutting Down the AWS Server (Cost Control)](#6-shutting-down-the-aws-server-cost-control)
7. [Troubleshooting & Handy Terminal Commands](#7-troubleshooting--handy-terminal-commands)

---

## 1. Prerequisites & System Architecture

### Supported Browsers
* **iOS (iPhone/iPad)**: Safari (Required for WebAuthn Passkeys & Camera access).
* **Android / Laptop**: Google Chrome, Microsoft Edge, or Mozilla Firefox.

### EC2 SSH Terminal Access
To manage the server via command line, open PowerShell/Terminal on your computer:
```bash
ssh -i "C:\Users\shaha\OneDrive\Desktop\AWS\attendance-ec2-key.pem" ubuntu@13.127.69.218
```

---

## 2. Starting the AWS Server (Turning On)

Whenever you want to test, demo, or present the project:

### Step 1: Start EC2 Instance in AWS Console
1. Open the [AWS EC2 Management Console](https://console.aws.amazon.com/ec2/).
2. Go to **Instances** in the left menu.
3. Select **`Secure-Attendance-Server`**.
4. Click **Instance state** (top right) $\rightarrow$ Click **Start instance**.
5. Wait **30 seconds** until Instance state shows **`Running`**.

### Step 2: Verify Docker Containers are Running
Because containers have `restart: always` configured, Docker automatically boots up PostgreSQL, Django, and Caddy SSL reverse proxy as soon as Ubuntu starts.

To verify in SSH:
```bash
cd ~/Secure_Attendance_System
docker compose ps
```

You should see 3 healthy/started containers:
* `secure_attendance_db` (PostgreSQL 16 `pgvector`)
* `secure_attendance_web` (Django Gunicorn WSGI)
* `secure_attendance_caddy` (Caddy Automatic Let's Encrypt HTTPS)

### Step 3: Open Browser
Visit **`https://13-127-69-218.sslip.io`**. You will see the live Login page with a green padlock HTTPS connection.

---

## 3. User Management & Registration

### A. Registering an Admin / Superuser

In your SSH terminal, run:
```bash
docker compose exec web python manage.py shell -c "
from core.models import User
User.objects.filter(email='admin@test.com').exists() or User.objects.create_superuser('admin@test.com', 'AdminPass123!')
print('Admin created successfully!')
"
```

You can now log into the Django Admin Panel at **`https://13-127-69-218.sslip.io/admin/`**.

---

### B. Registering a New Teacher / Professor

Professors require cryptographic **ECDSA P-256 keys** to sign attendance metadata.

#### Option 1: Via Shell Command (Fastest)
```bash
docker compose exec web python manage.py shell -c "
from core.models import User
User.objects.filter(email='prof.smith@university.edu').exists() or User.objects.create_superuser('prof.smith@university.edu', 'ProfPass123!')
print('Professor account created!')
"
```
*(Note: When the professor first starts a session, the system automatically generates and encrypts their ECDSA keypair).*

#### Option 2: Via Django Admin Panel
1. Log in at `https://13-127-69-218.sslip.io/admin/` with your Admin account.
2. Go to **Users** $\rightarrow$ **Add User**.
3. Set `Email`, `Password`, `Role = Professor`, `Is Staff = True`.

---

### C. Registering a New Student & Biometrics

Student registration involves 3 steps:

#### Step 1: Create Student Account
Run in SSH shell:
```bash
docker compose exec web python manage.py shell -c "
from core.models import User
User.objects.filter(email='student1@test.com').exists() or User.objects.create_user(email='student1@test.com', password='StudentPass123!', role='student')
print('Student account created!')
"
```

#### Step 2: Student Biometric Passkey Registration (FIDO2 / Touch ID / Face ID)
1. Have the student log in at **`https://13-127-69-218.sslip.io`** on their phone.
2. The Student Dashboard will prompt: **"Passkey Registration Required"**.
3. Click **Register Passkey / Face ID**.
4. The phone OS prompt will appear $\rightarrow$ Confirm with **Face ID**, **Touch ID**, or **Screen Lock PIN**.

#### Step 3: Student Face Profile Enrollment
1. On the Student Dashboard, click **Enroll Face Profile**.
2. Align face clearly in the camera frame.
3. Click **Capture & Save Face Profile**.
4. The server runs MTCNN face detection, generates a 512-dimensional L2-normalized float embedding (`.npy`), and saves it to PostgreSQL.

---

## 4. Conducting Attendance (Step-by-Step Flow)

### Step A: Teacher Starts Session
1. Professor logs in at `https://13-127-69-218.sslip.io`.
2. Click **Start New Session**.
3. Enter the **Course Code** (e.g. `CS101 - Operating Systems`).
4. Click **Start Session**.
5. Django generates a 256-bit `session_secret` and binds it to the active course session.

---

### Step B: Running Network Verification (Choose Mode 1 or Mode 2)

To ensure students in Room 101 cannot mark attendance for Professor B in Room 102, choose one of the network verification options:

#### Mode 1: Standalone Attendance Agent Mode (Recommended for Wi-Fi / Hotspots)
The **Attendance Agent** runs on the professor's laptop or classroom router to issue signed HMAC-SHA256 network nonces.

1. On the Professor's laptop (connected to classroom Wi-Fi / hotspot), navigate to the project directory:
   ```bash
   cd attendance_agent
   ```
2. Set the Agent API token in environment / `.env`:
   ```bash
   # Windows (PowerShell)
   $env:ATTENDANCE_AGENT_API_TOKEN="secure_presence_v3_default_token"
   $env:DJANGO_BACKEND_URL="https://13-127-69-218.sslip.io"

   # Linux / Mac
   export ATTENDANCE_AGENT_API_TOKEN="secure_presence_v3_default_token"
   export DJANGO_BACKEND_URL="https://13-127-69-218.sslip.io"
   ```
3. Start the Attendance Agent:
   ```bash
   python agent.py
   ```
   *The Agent runs on `http://127.0.0.1:5000` (or local IP) and receives the active `session_secret` pushed by Django.*

---

#### Mode 2: IP Subnet Range Matching Mode (Traditional Subnet Filter)
If the classroom has a dedicated static IP subnet (e.g. `192.168.1.0/24`):
1. In `core/attendance_service.py`, `verify_network(student_ip, session)` checks if the student's incoming IP address falls strictly within `session.subnet_range` and matches `session.gateway_ip`.
2. Students outside the classroom IP range are rejected with **"Network Verification Failed — You are not connected to the classroom Wi-Fi."**

---

### Multi-Teacher Session Isolation Principle

When **Professor A (Room 101 - CS101)** and **Professor B (Room 102 - CS102)** run simultaneous sessions:

* **Session Secret Isolation**: Session `CS101` is cryptographically bound to Room 101's Agent / Subnet. Session `CS102` is bound to Room 102's Agent / Subnet.
* **Attempt Rejection**: If Student 1 (in Room 101) attempts to submit attendance for `CS102`, Student 1's phone requests an HMAC proof from Room 101's Agent. When submitted to AWS, Django compares Room 101's proof against `CS102`'s session secret hash. **The check fails and REJECTS Student 1 immediately.**

---

### Step C: Student Submits Attendance (Mobile Phone)

1. Student opens `https://13-127-69-218.sslip.io` on Safari (iOS) or Chrome (Android).
2. Click **Mark Attendance** under their active course session (`CS101`).
3. **Stage 1 — MediaPipe Liveness Check**:
   - Camera opens. Student aligns face in the center circle.
   - MediaPipe FaceMesh tracks 468 30-FPS facial landmarks to verify genuine human liveness.
4. **Stage 2 — PyTorch Face Matching**:
   - Snapshot frame sent to EC2 Gunicorn.
   - FaceNet compares the snapshot embedding against the student's enrolled 512-dim `.npy` profile embedding (~15-25ms).
5. **Stage 3 — Biometric Passkey Verification**:
   - Phone prompts **Face ID / Touch ID / Fingerprint**.
6. **Stage 4 — Network Proof Verification**:
   - Browser submits the Attendance Agent HMAC nonce proof / IP check to Django.
7. **Attendance Accepted!**:
   - Server appends a tamper-evident SHA-256 chained hash to PostgreSQL (`chained_hash = SHA256(record_hash + previous_hash)`).
   - Student sees **"Attendance Recorded Successfully"** green checkmark.

---

## 5. Viewing & Exporting Attendance Reports

### View Active Session Logs
On the **Teacher Dashboard**, click **View Active Session** to see student emails, timestamps, verification statuses, and client IP addresses in real time.

### Export Attendance Records
1. Go to **Session History** on the Teacher Dashboard.
2. Select a course session.
3. Click **Export Excel (`.xlsx`)** or **Export CSV**.
4. The file downloads containing student names, emails, timestamps, verification methods, and hash audit trails.

---

## 6. Shutting Down the AWS Server (Cost Control)

To ensure **$0.00 compute charges** when you are done working:

### Step 1: Stop EC2 Instance in AWS Console UI
1. Open the [AWS EC2 Management Console](https://console.aws.amazon.com/ec2/).
2. Go to **Instances** $\rightarrow$ select **`Secure-Attendance-Server`**.
3. Click **Instance state** $\rightarrow$ Click **Stop instance**.
4. Confirm **Stop**.

> [!TIP]
> **Data Safety Guarantee**: Stopping the server preserves 100% of your PostgreSQL database, enrolled student profiles, face embeddings, and attendance records on disk. When you turn the server back on, everything is instantly restored.

---

## 7. Troubleshooting & Handy Terminal Commands

### View Live Application Logs
```bash
cd ~/Secure_Attendance_System
docker compose logs -f web
```

### View Caddy SSL Reverse Proxy Logs
```bash
docker compose logs -f caddy
```

### Restart All Containers
```bash
docker compose restart
```

### Re-pull Latest Code & Apply Updates
```bash
cd ~/Secure_Attendance_System
git pull
docker compose up -d
```

### Reset / Change User Password
```bash
docker compose exec web python manage.py shell -c "
from core.models import User
u = User.objects.get(email='teacher@test.com')
u.set_password('NewPassword123!')
u.save()
print('Password updated!')
"
```
