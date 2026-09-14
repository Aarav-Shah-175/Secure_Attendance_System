# Secure Attendance System (V3 Production Architecture)
### *A Zero-Trust, 5-Layer Cryptographic & Deep Learning Biometric Attendance Platform*

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)](https://djangoproject.com)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.2+-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org)
[![FIDO2 / WebAuthn](https://img.shields.io/badge/WebAuthn-FIDO2%20Passkeys-green)](https://fidoalliance.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![AWS](https://img.shields.io/badge/AWS-EC2%20Cloud-FF9900?logo=amazonaws&logoColor=white)](https://aws.amazon.com)

---

## 📑 Table of Contents (Presentation & Reference Sitemap)

1. [Executive Summary & Problem Statement](#1-executive-summary--problem-statement)
2. [Comparative Analysis (Why Existing Systems Fail)](#2-comparative-analysis-why-existing-systems-fail)
3. [The 5-Layer Zero-Trust Security Blueprint](#3-the-5-layer-zero-trust-security-blueprint)
4. [High-Level System Architecture](#4-high-level-system-architecture)
5. [Deep Learning Anti-Spoofing & Biometric Pipeline](#5-deep-learning-anti-spoofing--biometric-pipeline)
6. [Cryptographic Identity & WebAuthn Hardware Passkeys](#6-cryptographic-identity--webauthn-hardware-passkeys)
7. [End-to-End Operational Lifecycle & Sequence Flows](#7-end-to-end-operational-lifecycle--sequence-flows)
8. [Database Schema & Tamper-Evident Audit Ledger](#8-database-schema--tamper-evident-audit-ledger)
9. [Deployment Topologies (Cloud vs Local Development)](#9-deployment-topologies-cloud-vs-local-development)
10. [Technology Stack & Core Dependencies](#10-technology-stack--core-dependencies)
11. [Installation & Rapid Deployment Guide](#11-installation--rapid-deployment-guide)
12. [Threat Model & Attack Mitigation Matrix](#12-threat-model--attack-mitigation-matrix)
13. [Automated Verification & Test Suite](#13-automated-verification--test-suite)

---

## 1. Executive Summary & Problem Statement

### 🚨 The Problem in Modern Academic Attendance
Traditional classroom attendance tracking methods suffer from severe security flaws, operational overhead, and proxy fraud:
* **Paper Sign-in Sheets**: Rampant manual proxy signatures, easy forgery, and lack of physical verification.
* **Static QR Codes**: Screenshots shared instantly via messaging apps (WhatsApp, Telegram) allow students anywhere in the world to mark attendance.
* **Basic Mobile GPS Geofencing**: Trivial to bypass using fake GPS apps, VPNs, or location spoofers.
* **Single-Frame Facial Recognition**: Highly vulnerable to presentation attacks (printed photographs, high-resolution tablet screens, video replay, deepfake generative models).
* **Browser-Exported Credentials**: Vulnerable to credential dumping, key sharing, and automated bot replays.

### 💡 The Solution
The **Secure Attendance Platform (V3)** is a zero-trust attendance platform that guarantees **physical proximity, biometric liveness, hardware-bound device identity, and cryptographic ledger immutability** without requiring students to install custom apps or Root CA certificates.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                5-LAYER ZERO-TRUST VERIFICATION                         │
│                                                                                        │
│   [ Layer 1 ]  Physical Proximity (Local Hotspot + Ephemeral HMAC-SHA256 Challenge)   │
│   [ Layer 2 ]  Multi-Frame Anti-Spoofing (Dual MiniFASNet Ensemble + Tilt + Distance) │
│   [ Layer 3 ]  Facial Identity Matching (FaceNet InceptionResNetV1 512-d Embedding)    │
│   [ Layer 4 ]  FIDO2 Hardware Passkey (Apple Secure Enclave / Android StrongBox)       │
│   [ Layer 5 ]  Tamper-Evident Audit Ledger (Cryptographic SHA-256 Hash Chain)         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Comparative Analysis (Why Existing Systems Fail)

| Security Feature | Paper Sheets | Static QR Codes | Mobile GPS Apps | Basic Face Recognition | **Our Secure Attendance System** |
|---|:---:|:---:|:---:|:---:|:---:|
| **Proxy Resistance** | ❌ None | ❌ Replay via WhatsApp | ❌ Fake GPS spoofing | ⚠️ Photo / Screen Bypass | 🟢 **100% Mathematically Bound** |
| **Physical Room Proof** | ❌ None | ❌ None | ⚠️ Approximate ($10\text{m}$) | ❌ None | 🟢 **Classroom Wi-Fi HMAC Nonce** |
| **Liveness Anti-Spoofing**| ❌ None | ❌ None | ❌ None | ❌ Single 2D frame | 🟢 **7-Frame Dual MiniFASNet Ensemble** |
| **Device Hardware Enclave**| ❌ None | ❌ None | ❌ None | ❌ None | 🟢 **FIDO2 / WebAuthn Biometric Enclave** |
| **Tamper Detection** | ❌ None | ❌ None | ❌ None | ❌ None | 🟢 **SHA-256 Linked Ledger Hash Chains**|
| **Student UX Friction** | ⚠️ Slow | 🟢 Quick | ⚠️ Slow | 🟢 Quick | 🟢 **Seamless (<5s automated scan)** |
| **App / Root CA Setup** | 🟢 None | 🟢 None | ❌ Native App Required | ❌ Native App Required | 🟢 **Zero App / Zero Root CA (Browser)** |

---

## 3. The 5-Layer Zero-Trust Security Blueprint

```mermaid
flowchart TD
    Start["👤 Student Initiates Attendance"] --> L1

    subgraph L1 ["🛡️ Layer 1: Physical Proximity (LAN Hotspot)"]
        direction TB
        L1_Desc["• Connects to Professor Wi-Fi Hotspot (192.168.137.1)<br/>• Fetches ephemeral HMAC-SHA256 challenge (30s TTL)<br/>• Plain HTTP on LAN (Zero Root CA required)"]
    end
    L1 -->|Valid LAN Nonce| L2
    L1 -.->|Out of Range / Remote Proxy| R1["❌ Reject: Proximity Failure"]

    subgraph L2 ["👁️ Layer 2: Multi-Frame Liveness & Anti-Spoofing"]
        direction TB
        L2_Desc["• Captures 7 temporal burst frames (~1.2s window)<br/>• Dual MiniFASNet Ensemble (Scale 2.7x + 4.0x SE)<br/>• Roll Angle Tilt Guard (&le; 30°) & Distance Ratio Check"]
    end
    L2 -->|Live Genuine Face| L3
    L2 -.->|Print / Screen / Deepfake| R2["❌ Reject: Presentation Attack"]

    subgraph L3 ["🧬 Layer 3: Deep Metric Biometric Matching"]
        direction TB
        L3_Desc["• InceptionResNetV1 (FaceNet) 512-d unit vector<br/>• Cosine Similarity vs Enrolled Profile<br/>• Match Threshold: Similarity &ge; 0.65"]
    end
    L3 -->|Biometric Match Confirmed| L4
    L3 -.->|Wrong Face / Impersonator| R3["❌ Reject: Identity Mismatch"]

    subgraph L4 ["🔑 Layer 4: FIDO2 / WebAuthn Hardware Passkey"]
        direction TB
        L4_Desc["• Server issues cryptographic WebAuthn challenge<br/>• Hardware Secure Enclave (Touch ID / Face ID / PIN)<br/>• Signs challenge with non-exportable private key"]
    end
    L4 -->|Hardware Assertion Verified| L5
    L4 -.->|Invalid Signature / Proxy Device| R4["❌ Reject: Auth Failure"]

    subgraph L5 ["⛓️ Layer 5: Tamper-Evident Audit Ledger"]
        direction TB
        L5_Desc["• Appends to SHA-256 Hash Chain: H_n = SHA256(H_n-1 || Record_n)<br/>• Cryptographically signed with Professor Ed25519 Key<br/>• Real-time Merkle root integrity verification"]
    end
    L5 --> Success["✅ Attendance Recorded & Sealed in Ledger"]

    style Start fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#ffffff
    style Success fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#ffffff
    style R1 fill:#7f1d1d,stroke:#ef4444,stroke-width:1.5px,color:#ffffff
    style R2 fill:#7f1d1d,stroke:#ef4444,stroke-width:1.5px,color:#ffffff
    style R3 fill:#7f1d1d,stroke:#ef4444,stroke-width:1.5px,color:#ffffff
    style R4 fill:#7f1d1d,stroke:#ef4444,stroke-width:1.5px,color:#ffffff
```

---

## 4. High-Level System Architecture

```mermaid
flowchart TB
    subgraph CLOUD ["☁️ AWS EC2 Cloud Infrastructure (Ubuntu 24.04 LTS)"]
        direction TB
        
        subgraph CADDY ["🌐 Caddy Web Server (Reverse Proxy :80 / :443)"]
            CAD_SSL["• Automated Let's Encrypt TLS<br/>• SSL Termination & Header Rewriting"]
        end

        subgraph DJANGO ["⚙️ Django 5.2 Application Server (Gunicorn WSGI :8000)"]
            DJ_CORE["• REST Attendance & Session API<br/>• Role-Based Access Control (RBAC)"]
            DJ_AI["• FaceNet 512-d Face Recognition<br/>• Dual MiniFASNet Anti-Spoofing Engine"]
            DJ_WA["• WebAuthn / FIDO2 Relying Party<br/>• Monotonic Counter Verification"]
            DJ_LEDGER["• SHA-256 Hash Chain Audit Engine<br/>• Cryptographic Ledger Validator"]
        end

        subgraph DATABASE ["🗄️ PostgreSQL 16 Database + pgvector (:5432)"]
            DB_DATA["• Student Profiles & 512-d Embeddings<br/>• WebAuthn Public Keys & Counters<br/>• Cryptographic Audit Entries & Roots"]
        end

        CAD_SSL -->|Proxy localhost:8000| DJ_CORE
        DJANGO <-->|TCP :5432 Relational & Vectors| DATABASE
    end

    subgraph HOST ["💻 Professor Laptop (Classroom Host Node)"]
        direction TB
        
        subgraph AGENT ["⚡ Attendance Agent Daemon (Python :5000)"]
            AG_KEY["• Ed25519 Asymmetric Identity Pair<br/>• Private Key in ~/.secure_attendance/"]
            AG_CHAL["• RAM-Only Session Secret Store<br/>• Ephemeral HMAC-SHA256 Challenge Nonces"]
            AG_HB["• Background Heartbeat Emitter<br/>• Session Registration Client"]
        end
    end

    subgraph CLIENTS ["📱 Student Smartphones (Mobile Edge)"]
        direction TB
        
        subgraph PHONE ["Browser & Hardware Enclave"]
            CL_BROWSER["• Mobile Safari / Chrome UI<br/>• WebAuthn JS API Client"]
            CL_CAM["• Front Camera Video Burst<br/>• 7 Temporal Frame Collector"]
            CL_ENCLAVE["• Apple Secure Enclave / Android StrongBox<br/>• Non-Exportable FIDO2 Private Key"]
        end
    end

    %% Network Connections
    HOST <==>|"1. HTTPS Heartbeat & Registration (WAN)"| CLOUD
    PHONE <==>|"2. HTTPS WebAuthn & Face Verification (WAN via Domain)"| CLOUD
    PHONE <==>|"3. HTTP Ephemeral Challenge Fetch (Classroom Wi-Fi Hotspot LAN :5000)"| HOST
```

---

## 5. Deep Learning Anti-Spoofing & Biometric Pipeline

### A. Dual MiniFASNet Anti-Spoofing Ensemble
The anti-spoofing subsystem uses an ensemble of **two multi-scale MiniFASNet convolutional neural networks** operating on custom spatial scale croppers:

1. **Scale 2.7x Model (`2.7_80x80_MiniFASNetV2.pth`)**:
   - Focuses on fine facial texture, skin grain, eye reflex, and specular screen reflection.
2. **Scale 4.0x with Squeeze-and-Excitation (`4_0_0_80x80_MiniFASNetV1SE.pth`)**:
   - Broad receptive field analyzing outer face boundaries, paper borders, phone edges, and background perspective distortion.
3. **Ensemble Softmax Fusion**:
   $$\text{Score}_{\text{ensemble}} = \frac{P_{\text{live}}(2.7x) + P_{\text{live}}(4.0x)}{2} \ge 0.50$$

```mermaid
graph TD
    A[Camera 7-Frame Burst] --> B[MTCNN / 5-Point Facial Landmark Detection]
    B --> C[Facial Pose & Tilt Evaluation - Reject if > 30 deg]
    B --> D[Distance & Size Evaluation - Reject if Face > 38% frame]
    B --> E[Multi-Scale Spatial Croppers]
    E -->|Scale 2.7x Crop 80x80| F[MiniFASNet V2 CNN]
    E -->|Scale 4.0x Crop 80x80| G[MiniFASNet V1SE CNN with SE-Blocks]
    F --> H[Softmax Ensemble Probabilities]
    G --> H
    H -->|Ensemble Score >= 0.50| I[Live Face Confirmed]
    H -->|Ensemble Score < 0.50| J[Spoof Rejected: Print/Screen Attack]
```

### B. Facial Recognition (InceptionResNetV1 / FaceNet)
* Converts the verified live face crop into a **512-dimensional unit-normalized embedding vector** $\vec{e}_{\text{live}} \in \mathbb{R}^{512}$.
* Computes Cosine Similarity against the student's registered profile embedding $\vec{e}_{\text{enrolled}}$:
  $$\text{Similarity}(\vec{u}, \vec{v}) = \frac{\vec{u} \cdot \vec{v}}{\|\vec{u}\|_2 \|\vec{v}\|_2} \ge 0.65$$
* Rejects any face with similarity $< 0.65$, preventing attendance marking for wrong individuals.

---

## 6. Cryptographic Identity & WebAuthn Hardware Passkeys

```mermaid
graph LR
    subgraph Student Device Enclave
        SE[Secure Enclave / StrongBox]
        BIO[Touch ID / Face ID / PIN]
        KEY[(Private Key - Non-Exportable)]
    end

    subgraph Browser Context
        NAV[navigator.credentials.get]
    end

    subgraph Cloud Server
        WA[WebAuthn Verifier]
        PUB[(Public Key in PostgreSQL)]
    end

    BIO -->|User Verified| SE
    SE -->|Sign Challenge| KEY
    KEY --> NAV
    NAV -->|Signed Assertion| WA
    WA -->|Verify Signature & Counter| PUB
```

### Why Hardware Passkeys Prevent Fraud
1. **Non-Exportable Private Keys**: Generated inside the device's cryptographic coprocessor (Apple Secure Enclave, Android StrongBox/Titan M, Windows Hello TPM). Private keys **cannot be extracted, shared, or copied**.
2. **RP_ID Domain Binding**: Passkeys are cryptographically locked to the server origin domain (`WEBAUTHN_RP_ID`). Phishing or proxy servers cannot reuse assertions.
3. **Monotonic Signature Counters**: The enclave increments an internal signature counter upon each signing. Any attempt to replay previous assertions triggers an immediate counter-mismatch alert.

---

## 7. End-to-End Operational Lifecycle & Sequence Flows

```mermaid
sequenceDiagram
    autonumber
    actor Prof as Professor
    actor Agent as Attendance Agent (Laptop)
    actor Cloud as Cloud Server (EC2)
    actor Student as Student Smartphone

    Note over Prof,Cloud: 1. Pre-Lecture Setup (5 mins before class)
    Prof->>Prof: Turn ON Laptop Hotspot (192.168.137.1)
    Prof->>Agent: Run python -m attendance_agent
    Agent->>Cloud: POST /agent/register/ (Ed25519 Public Key)
    Cloud-->>Agent: 200 OK (Registration Confirmed)

    Prof->>Cloud: Login -> Start Attendance Session (e.g. BCSE309L)
    Cloud->>Agent: POST /agent/session-start/ (Session Secret pushed to RAM)
    Agent-->>Cloud: 200 OK (Session Active)

    Note over Student,Cloud: 2. Student In-Class Attendance Flow
    Student->>Student: Connect Phone to Professor's Hotspot
    Student->>Cloud: Open https://13-127-69-218.sslip.io (Portal)
    Student->>Cloud: POST /student/secure-v2/start-attempt/
    Cloud-->>Student: Attempt Created (ID + Challenge Token)

    rect rgb(235, 245, 255)
        Note over Student,Agent: Phase 1: Physical Proximity Verification
        Student->>Agent: GET http://192.168.137.1:5000/challenge?session_id=...
        Agent-->>Student: 200 OK (HMAC-SHA256 Nonce + Timestamp)
    end

    rect rgb(240, 255, 240)
        Note over Student,Cloud: Phase 2: Biometric Liveness & Facial Matching
        Student->>Student: Front Camera 7-Frame Burst (~1.2s)
        Student->>Cloud: POST /student/secure-v2/verify-liveness/ (7 Frames + Agent Challenge)
        Cloud->>Cloud: Verify Agent HMAC-SHA256 Nonce
        Cloud->>Cloud: MiniFASNet Dual Anti-Spoofing (Scale 2.7x + 4.0x)
        Cloud->>Cloud: FaceNet 512-d Cosine Similarity Matching (>= 0.65)
        Cloud-->>Student: 200 OK (Liveness & Identity Confirmed)
    end

    rect rgb(255, 250, 235)
        Note over Student,Cloud: Phase 3: Hardware Passkey Assertion
        Student->>Cloud: POST /student/secure-v2/request-challenge/
        Cloud-->>Student: WebAuthn Challenge Options
        Student->>Student: Native Biometric Prompt (Touch ID / Face ID / PIN)
        Student->>Cloud: POST /student/secure-v2/submit/ (Signed Assertion)
        Cloud->>Cloud: Verify FIDO2 Signature & Increment Counter
        Cloud->>Cloud: Append SHA-256 Audit Hash Chain (H_n = SHA256(H_n-1 || Record))
        Cloud-->>Student: 200 OK (Attendance Recorded Successfully!)
    end

    Note over Prof,Cloud: 3. Post-Lecture Close
    Prof->>Cloud: Click "End Attendance Session"
    Cloud->>Agent: Invalidate Active Session Secrets
    Prof->>Prof: Stop Agent (Ctrl+C) & Turn OFF Hotspot
```

---

## 8. Database Schema & Tamper-Evident Audit Ledger

### Entity Relationship Diagram

```mermaid
erDiagram
    USER ||--o{ PASSKEY_CREDENTIAL : owns
    USER ||--o{ STUDENT_PROFILE : has
    USER ||--o{ ATTENDANCE_SESSION : instructs
    ATTENDANCE_SESSION ||--o{ ATTENDANCE_RECORD : contains
    ATTENDANCE_SESSION ||--o{ ATTENDANCE_ATTEMPT : tracks
    ATTENDANCE_SESSION ||--o{ ATTENDANCE_AUDIT_ENTRY : logs
    ATTENDANCE_SESSION ||--o| ATTENDANCE_SESSION_AUDIT_ROOT : seals

    USER {
        uuid id PK
        string email UK
        string role "professor | student"
        text public_key "ECDSA Public Key"
        text private_key_encrypted "AES-256-GCM"
    }

    STUDENT_PROFILE {
        uuid id PK
        uuid user_id FK
        string roll_number
        string embedding_path "Encrypted 512-d .npy"
        boolean face_registered
    }

    PASSKEY_CREDENTIAL {
        uuid id PK
        uuid user_id FK
        text credential_id UK
        text public_key_cose
        integer sign_count
        string aaguid
    }

    ATTENDANCE_SESSION {
        uuid id PK
        uuid professor_id FK
        string course_code
        datetime timestamp
        datetime expiry
        string session_secret_hash
        string agent_id
        boolean active
    }

    ATTENDANCE_AUDIT_ENTRY {
        uuid id PK
        uuid session_id FK
        uuid record_id FK
        string canonical_report_hash "SHA-256"
        string previous_entry_hash "SHA-256 Linked"
        text entry_signature "Signed by Professor"
        datetime signed_at
    }
```

### Cryptographic Audit Ledger Mathematics
Each attendance entry is bound to an append-only, tamper-evident hash chain:
$$H_0 = \text{SHA256}(\text{"GENESIS"} \parallel \text{SessionID})$$
$$H_n = \text{SHA256}(H_{n-1} \parallel \text{CanonicalJSON}(\text{Record}_n))$$
$$\text{Signature}_n = \text{Sign}_{\text{ProfPrivateKey}}(H_n \parallel H_{n-1})$$

If an attacker modifies any historical database row, the entire downstream hash chain breaks, allowing instant detection via the **Verify Ledger Integrity** button on the Professor Dashboard.

---

## 9. Deployment Topologies (Cloud vs Local Development)

### Topology A: Production Hybrid Cloud Deployment (Recommended)
* **Cloud Node (AWS EC2 / Ubuntu 24.04 LTS)**:
  * Hosts Django Web Application, PyTorch AI Pipeline, Caddy Reverse Proxy, and PostgreSQL Database.
  * Elastic Public IP with `sslip.io` / Domain and automatic Let's Encrypt TLS.
* **Classroom Host (Professor Laptop)**:
  * Hosts Windows Mobile Hotspot (`192.168.137.1`).
  * Runs lightweight `attendance_agent` daemon issuing local HMAC challenge nonces.

### Topology B: Standalone Local Development Mode
* Full stack runs directly on the Professor's laptop.
* `runserver_plus` runs over local HTTPS (`https://192-168-137-1.sslip.io:8000`) with self-signed development certificates.

---

## 10. Technology Stack & Core Dependencies

| Layer / Subsystem | Technology | Version | Purpose |
|---|---|---|---|
| **Web Framework** | Django | `5.2.x` | Core backend, ORM, Session Management & RBAC |
| **API Layer** | Django REST Framework | `3.16.x` | REST endpoints for biometric & passkey submissions |
| **Hardware Passkeys** | `webauthn` | `2.5.x` | FIDO2 / WebAuthn Relying Party challenge & assertion |
| **Anti-Spoofing AI** | MiniFASNet V1SE / V2 | PyTorch `2.2+` | Multi-scale CNN anti-spoofing ensemble |
| **Face Recognition** | InceptionResNetV1 (FaceNet) | `facenet-pytorch 2.6.x`| 512-dimensional facial feature embedding vector |
| **Vision & Math** | OpenCV & SciPy | `4.8+` / `1.11+` | Image preprocessing, alignment, cosine similarity |
| **Agent Cryptography** | `cryptography` | `46.0.x` | Ed25519 identity keys, AES-256-GCM, HMAC-SHA256 |
| **Database** | PostgreSQL + pgvector | `16.x` | Relational audit tables & high-dimensional vector data |
| **Cloud Proxy & TLS** | Caddy Server | `2.8.x` | Reverse proxy with automated Let's Encrypt SSL |
| **Container Engine** | Docker & Compose | `24.x+` | Containerized reproducible deployments |

---

## 11. Installation & Rapid Deployment Guide

### Prerequisites
* Python 3.10 or 3.11
* Docker & Docker Compose
* Git

### Quickstart (Local Development)

```powershell
# 1. Clone the repository
git clone https://github.com/Aarav-Shah-175/Secure_Attendance_System.git
cd Secure_Attendance_System

# 2. Setup Virtual Environment
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r attendance_agent/requirements.txt

# 3. Launch Docker Containers (Postgres & Django)
docker compose up -d

# 4. Apply Database Migrations & Create Superuser
docker compose exec web python manage.py migrate
docker compose exec -it web python manage.py createsuperuser

# 5. Start the Attendance Agent (in a separate terminal)
python -m attendance_agent --verbose
```

> [!TIP]
> For complete cloud provisioning, turning ON/OFF cloud instances, mobile setup, and troubleshooting, consult the **[HOW_TO_RUN2.md](file:///d:/Project-%20Academic/Attendance/HOW_TO_RUN2.md)** operational manual.

---

## 12. Threat Model & Attack Mitigation Matrix

| Attack Vector | Attacker Method | System Mitigation Defense | Result |
|---|---|---|:---:|
| **Remote Proxy Attendance** | Student at home tries to mark attendance via shared link | Challenge requires local Wi-Fi hotspot access (`http://192.168.137.1:5000`); HMAC nonce has 30s TTL | 🛑 **BLOCKED** |
| **Photo / Paper Attack** | Printed photo of student held in front of phone camera | MiniFASNet Scale 2.7x texture analysis & Scale 4.0x boundary checks reject flat static textures | 🛑 **BLOCKED** |
| **Screen Replay Attack** | High-res smartphone/tablet screen displaying video of student | Specular reflex analysis, landmark rotation variance, and moiré pattern detection flag fake face | 🛑 **BLOCKED** |
| **Deepfake Video Injection** | Virtual camera software injecting simulated face | Facial tilt geometric angle filter ($>30^\circ$) + multi-frame landmark movement coherence checks | 🛑 **BLOCKED** |
| **Credential / Token Sharing**| Student gives login email & password to a friend | FIDO2 Passkey requires physical biometric scan on the registered hardware Secure Enclave | 🛑 **BLOCKED** |
| **Database Tampering** | Rogue admin directly alters attendance records in SQL | Modifying records invalidates the cryptographic SHA-256 hash chain and signature ledger | 🛑 **DETECTED** |
| **Replay Attack** | Resending previous valid network packet or token | Ephemeral nonces expire in 30 seconds; WebAuthn signature counter monotonicity enforced | 🛑 **BLOCKED** |

---

## 13. Automated Verification & Test Suite

The project includes an automated test suite validating all layers:

```powershell
# Run the automated test suite
.\venv\Scripts\python.exe secure_attendance/manage.py test core
```

### Test Coverage Highlights:
* **`test_face_system.py`**: Validates MiniFASNet multi-scale forward passes, anti-spoofing ensemble thresholds, FaceNet embedding generation, cosine similarity matching, and print attack rejection.
* **`test_passkey.py`**: Validates WebAuthn registration, user verification options, assertion signing, and cryptographic signature counter tracking.
* **`test_audit_ledger.py`**: Validates tamper-evident linked SHA-256 hash chains, Merkle root creation, and historical tampering detection.
* **`test_agent_crypto.py`**: Validates Ed25519 asymmetric identity, HMAC challenge issuance, session key decryption, and nonce verification.

```text
Ran 23 tests in 4.812s
OK (All 23 Tests Passed)
```

---

## 📄 License & Academic Attribution
Developed as an advanced academic research and engineering platform for secure, tamper-proof attendance management. Released under the **MIT License**.
