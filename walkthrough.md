# Walkthrough — Pre-Liveness Face Verification & Registration Gate

We have implemented **Face Matching (FaceNet Cosine Similarity > 0.7)** and **First-Time Face Registration** directly into the **Secure Presence V2** attendance flow, executing **before** the MediaPipe liveness challenge starts.

---

## 1. Summary of Accomplished Steps

### 1. Reset Old Embeddings
- Cleared all existing pre-existing `.npy` files from `secure_attendance/embeddings/` so all students undergo a clean first-time face registration on their next attendance attempt.

### 2. New Face Status API & Endpoint
- Created `check_face_status` view (`GET /student/face-status/`) in `views.py`.
- Added route `path('student/face-status/', views.check_face_status, name='check_face_status')` in `urls.py`.
- Returns `{"registered": true/false}` depending on whether `embeddings/{user_id}.npy` exists on disk.

### 3. Integrated Face Gate in `student_dashboard.html`
- Updated `submitAttendanceV2` to check `/student/face-status/`.
- Enhanced `runLivenessChallenge(challengeData, isRegistered)` camera flow:
  - **First-Time Student Login/Attendance (`isRegistered == false`):**
    1. Camera overlay opens: *"Step 1/2: Registering Face Profile..."*
    2. Captures face frame from video stream.
    3. Posts to `/student/register-face/` to compute FaceNet embedding and save `embeddings/{user_id}.npy`.
    4. Upon success, transitions seamlessly into *"Step 2/2: MediaPipe Liveness Challenge"*.
  - **Returning Student Attendance (`isRegistered == true`):**
    1. Camera overlay opens: *"Step 1/2: Verifying Face Identity..."*
    2. Captures face frame from video stream.
    3. Posts to `/student/face-verify/` to compare against `embeddings/{user_id}.npy` (threshold > 0.7).
    4. **If Face Match Fails (Wrong Person):** Aborts attempt immediately with error *"Face match failed. Identity not recognized."*
    5. **If Face Match Succeeds:** Transitions into *"Step 2/2: MediaPipe Liveness Challenge"*.

---

## 2. Updated Complete Attendance Workflow

```
Student clicks "Submit Secure V2 Attendance"
  │
  ├─ 1. Start Attempt & Presence Heartbeat
  │
  ├─ 2. GET /student/face-status/
  │      ├─▶ If NOT registered: Capture & POST /student/register-face/ ➔ Saves embeddings/{user_id}.npy
  │      └─▶ If ALREADY registered: Capture & POST /student/face-verify/ ➔ Check FaceNet similarity > 0.7
  │             └─▶ ❌ Mismatch ➔ Abort attempt
  │
  ├─ 3. GET /student/secure-v2/liveness-challenge/
  │
  ├─ 4. Run Interactive MediaPipe Liveness Challenge (Blink / Head Turn / Straight)
  │
  ├─ 5. POST /student/secure-v2/verify-liveness/ (Verify HMAC Nonce)
  │
  ├─ 6. Request WebAuthn Challenge & Passkey Assertion
  │
  └─ 7. Attendance Recorded ✅
```

---

## 3. Test & System Verification

All 13 unit tests passed:
```
Ran 13 tests in 19.769s
OK
System check identified no issues (0 silenced).
```
