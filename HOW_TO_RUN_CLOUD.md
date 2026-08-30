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
5. The **Active Session Dashboard** displays the live QR code, session countdown, and real-time student count.

---

### Step B: Attendance Agent Proximity Check (Optional)
If running the Attendance Agent on the classroom Wi-Fi network:
```bash
python attendance_agent/agent.py
```
The agent holds an in-memory HMAC-SHA256 secret to verify that students are physically inside the classroom network.

---

### Step C: Student Submits Attendance (Mobile Phone)

1. Student opens `https://13-127-69-218.sslip.io` on Safari (iOS) or Chrome (Android).
2. Click **Mark Attendance** under the active course session (`CS101`).
3. **Stage 1 — MediaPipe Liveness**:
   - The browser opens camera feed.
   - Student aligns face in the center guide circle.
   - MediaPipe FaceMesh tracks 468 30-FPS facial landmarks to verify genuine human liveness (gesture & blink check).
4. **Stage 2 — PyTorch Face Matching**:
   - A face snapshot is sent to Gunicorn on EC2.
   - FaceNet compares the snapshot embedding against the student's enrolled profile embedding.
5. **Stage 3 — Passkey Verification**:
   - Phone prompts **Face ID / Touch ID**.
6. **Attendance Accepted!**:
   - The server appends a tamper-evident SHA-256 chained hash to PostgreSQL (`chained_hash = SHA256(record_hash + previous_hash)`).
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
