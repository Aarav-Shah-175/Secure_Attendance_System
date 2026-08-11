# Secure Presence V2 -- Network Verification Architecture Redesign

## Objective

Redesign only the **network verification architecture** of the existing
Secure Presence V2 attendance system while preserving all existing
functionality.

### Existing functionality (must remain unchanged)

-   Django backend
-   Professor Dashboard
-   Student Dashboard
-   Attendance Sessions
-   Attendance Attempts
-   Face Registration
-   Face Verification
-   Liveness Detection
-   WebAuthn (Passkeys)
-   Existing authentication and authorization
-   Existing UI
-   Existing database schema unless absolutely necessary

------------------------------------------------------------------------

## Existing Architecture

Currently:

``` text
Professor Laptop
├── Django Server
├── Hotspot
└── Students
```

The Django server detects:

-   hotspot IP
-   gateway
-   subnet

Students are validated using subnet matching.

This tightly couples the web server and hotspot.

Problems:

1.  Django cannot easily be deployed to the cloud.
2.  Local HTTPS requires distributing and installing a custom Root CA
    certificate.
3.  Network logic is embedded inside Django.

------------------------------------------------------------------------

# New Architecture

Support BOTH:

## Development

``` text
Professor Laptop
├── Django
├── Attendance Agent
├── Hotspot
└── Students
```

## Production

``` text
                HTTPS
                 │
          Cloud Django Server
                 │
        -----------------------
                 │
         Professor Laptop
        ├── Attendance Agent
        └── Hotspot
                 │
             HTTP (LAN)
                 │
             Student Devices
```

The Django server must NEVER detect hotspot IPs or subnets.

All hotspot logic moves into a standalone Attendance Agent.

------------------------------------------------------------------------

# Attendance Agent

Implement a standalone Python Attendance Agent.

Requirements

-   Lightweight
-   Standalone process
-   No GUI
-   Modular
-   Platform independent
-   Configurable
-   Production ready

Responsibilities

-   Detect hotspot/network
-   Expose local REST API
-   Hold temporary cryptographic material
-   Destroy secrets automatically
-   Communicate with Django
-   Advertise local endpoint (optional mDNS)
-   Never store session secrets permanently

------------------------------------------------------------------------

# Remove Root CA Dependency

The Attendance Agent communicates with students using HTTP only.

Example:

http://attendance.local/

or

http://192.168.137.1:5000/

This endpoint never exposes sensitive data.

All communication with Django remains HTTPS.

No custom Root CA installation should be required.

------------------------------------------------------------------------

# Cryptographic Protocol

Do NOT expose a shared session secret.

Instead implement challenge-response authentication.

Recommended primitives:

-   HMAC-SHA256
-   Ed25519
-   SHA-256
-   Python secrets module

Avoid:

-   MD5
-   SHA1
-   AES-ECB
-   predictable RNG
-   static secrets

------------------------------------------------------------------------

# Attendance Agent Registration

On first launch:

Generate an Ed25519 keypair.

Store:

Private key

-   locally
-   securely
-   never transmitted

Register public key with Django.

Every professor machine has its own identity.

------------------------------------------------------------------------

# Session Creation

When professor clicks Start Attendance:

Django creates AttendanceSession.

Generate:

-   session_secret (256-bit random)
-   secrets.token_bytes(32)

Store ONLY:

SHA256(session_secret)

inside the database.

Never store plaintext session_secret.

Securely transmit session_secret to the Attendance Agent.

Attendance Agent stores it in RAM only.

------------------------------------------------------------------------

# Attendance Agent Endpoints

Implement:

GET /status

POST /start-session

POST /stop-session

GET /challenge

POST /heartbeat

------------------------------------------------------------------------

# Challenge Generation

Student browser requests

GET /challenge

Attendance Agent generates

-   random nonce
-   timestamp
-   session id

Then computes

HMAC(session_secret, challenge \|\| timestamp \|\| session_id)

OR

Ed25519 signature.

Return only:

-   challenge
-   timestamp
-   proof
-   agent signature

Never expose session_secret.

------------------------------------------------------------------------

# Student Workflow

Student visits

https://attendance.example.com

Clicks

Submit Attendance

Browser first requests

http://attendance.local/challenge

fallback

http://192.168.137.1:5000/challenge

Receives:

-   challenge
-   timestamp
-   proof
-   agent signature

Browser then submits attendance to Django over HTTPS.

Request payload:

-   session_id
-   challenge
-   timestamp
-   proof
-   passkey_assertion
-   face_embedding
-   liveness_result

------------------------------------------------------------------------

# Django Verification

Before WebAuthn.

Before Face Verification.

Before Liveness.

Verify:

-   challenge unused
-   timestamp valid
-   session active
-   proof valid
-   agent signature valid

Reject if:

-   replay
-   invalid signature
-   expired timestamp
-   expired session

Then continue existing workflow:

Network Verification

↓

Passkey

↓

Face Verification

↓

Liveness

↓

Attendance Recorded

------------------------------------------------------------------------

# Replay Protection

Every challenge:

-   cryptographically random
-   valid for 30 seconds
-   one-time use only

Reuse must be rejected.

------------------------------------------------------------------------

# Heartbeat

Attendance Agent sends heartbeat every 30 seconds.

Payload:

-   session id
-   agent id
-   alive status

If heartbeat stops,

Django automatically ends attendance.

------------------------------------------------------------------------

# Session Expiry

On expiry:

Attendance Agent

-   destroys session_secret
-   clears memory
-   invalidates all outstanding challenges
-   stops serving challenge endpoint

------------------------------------------------------------------------

# Development Compatibility

Development mode:

Professor Laptop

-   Django
-   Attendance Agent
-   Hotspot

Only configuration should differ from production.

------------------------------------------------------------------------

# Production Compatibility

Cloud-hosted Django.

Professor Laptop:

-   Attendance Agent
-   Hotspot

Students connect only to hotspot.

No application logic changes required.

------------------------------------------------------------------------

# Remove Completely

Delete all hotspot detection code from Django.

Examples:

-   detect_hotspot_ip()
-   get_gateway()
-   subnet_validation()
-   client_ip_validation()
-   interface_detection()

The Attendance Agent becomes solely responsible for network
verification.

------------------------------------------------------------------------

# Security Goals

Prevent:

-   Replay attacks
-   MITM attacks
-   Secret leakage
-   Reflection attacks
-   Session fixation
-   Brute force
-   Rogue hotspot impersonation

Use:

-   Ed25519 identities for Attendance Agents
-   HMAC-SHA256 proofs
-   One-time challenges
-   SHA-256 hashes
-   TLS 1.3 between browser and Django

------------------------------------------------------------------------

# Deliverables

Produce:

1.  Attendance Agent implementation.
2.  Django modifications.
3.  REST API specification.
4.  Configuration system.
5.  Sequence diagrams.
6.  Class diagrams.
7.  Cryptographic protocol documentation.
8.  Threat model.
9.  Replay attack analysis.
10. MITM analysis.
11. Secret leakage analysis.
12. Deployment guide.
13. Local development guide.
14. Unit tests.
15. Integration tests.
16. Migration guide.
17. Production deployment instructions.

The implementation should be modular, production-ready,
cryptographically sound, cloud-ready, and backward-compatible with local
development while preserving all existing Secure Presence V2
functionality except the old subnet/IP-based network verification.
