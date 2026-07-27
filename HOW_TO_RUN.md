# How to Run the Secure Attendance System

## Why This Setup Is Needed (Quick Explanation)

WebAuthn (passkeys/biometrics) has **two hard browser requirements**:

| Requirement | Problem we had | Fix applied |
|---|---|---|
| Site must be on trusted HTTPS | Old cert was a dummy self-signed cert | Generated new cert with `mkcert`, installed CA on phone |
| `rpId` must be a real domain name (no IPs) | `192.168.137.1` is an IP, not a domain | Using `192-168-137-1.sslip.io` — a real domain that resolves to the IP |

**What is `192-168-137-1.sslip.io`?**  
`sslip.io` is a free public DNS service. Any domain like `A-B-C-D.sslip.io` automatically resolves to the IP `A.B.C.D`. So `192-168-137-1.sslip.io` always points to `192.168.137.1` — your laptop's hotspot IP. The phone resolves this via DNS through the hotspot's shared internet.

---

## One-Time Setup per Phone (Install the CA Certificate)

Students only need to do this once. After this, every cert from mkcert is trusted automatically.

### Get the file onto the phone

The file is: `D:\Project- Academic\Attendance\secure_attendance\rootCA.crt`

**Easiest method — Python file server:**
1. Turn on your laptop's Mobile Hotspot first.
2. Connect the student's phone to the hotspot.
3. Open a **second terminal** in the project folder and run:
   ```powershell
   ..\venv\Scripts\python.exe -m http.server 9999
   ```
4. On the phone browser, open: `http://192.168.137.1:9999`
5. Tap `rootCA.crt` to download it.
6. Stop the file server (Ctrl+C) when done.

---

### Install on Android

1. Open **Settings** → search for **"Install certificate"** in the search bar → tap it.
2. Choose **CA certificate** (not Wi-Fi or VPN certificate).
3. Tap the downloaded `rootCA.crt` file.
4. Give it any name. Tap **OK**.
5. ✅ Done. Always use **Chrome** browser (not Samsung Internet).

### Install on iPhone

1. Tap the downloaded `rootCA.crt` file in Files / Mail — it will say **"Profile Downloaded"**.
2. Go to **Settings → General → VPN & Device Management**.
3. Tap the profile → tap **Install** → enter passcode → tap **Install** again.
4. Go to **Settings → General → About → Certificate Trust Settings**.
5. Toggle ON the mkcert certificate → tap **Continue**.
6. ✅ Done. Use **Safari** browser.

---

## Every-Day Steps — Teacher

### 1. Turn on Mobile Hotspot

**Windows key + I** → **Network & Internet → Mobile Hotspot** → toggle **ON**.

### 2. Open a terminal in the project folder

```powershell
cd "D:\Project- Academic\Attendance\secure_attendance"
```

### 3. Start the server

```powershell
.\start_server.ps1
```

You will see:
```
Development server is running at https://0.0.0.0:8000/
```

### 4. Open your dashboard (on the laptop)

```
https://192-168-137-1.sslip.io:8000
```

> [!NOTE]
> The laptop can also use `https://192.168.137.1:8000` or `https://localhost:8000` — the IP works on the laptop itself. Only the phones must use the sslip.io domain.

---

## Every-Day Steps — Students

### 1. Connect to the teacher's hotspot

Open Wi-Fi settings → connect to teacher's hotspot.

### 2. Open the website in Chrome (Android) or Safari (iPhone)

```
https://192-168-137-1.sslip.io:8000
```

> [!IMPORTANT]
> You MUST type exactly `https://192-168-137-1.sslip.io:8000` — with dashes, not dots. This is the domain that WebAuthn accepts. The IP address will give an "invalid domain" error.

### 3. First time only — Enrol your passkey

1. Log in with your student account.
2. Go to the **Enrol** page.
3. Tap **Enrol Passkey**.
4. Complete the biometric (fingerprint / Face ID) prompt.
5. ✅ Done — you're enrolled permanently.

### 4. Every class — Mark attendance

1. Teacher starts a session.
2. Go to **Mark Attendance**.
3. Tap **Submit** → complete biometric.
4. ✅ Attendance recorded.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `ERR_NAME_NOT_RESOLVED` for sslip.io | Phone has no internet through hotspot | Check laptop has internet; hotspot internet sharing is on |
| "Certificate error" in browser | CA cert not installed on phone | Redo the one-time CA install steps |
| "Invalid domain" on passkey enrol | Using IP address instead of sslip.io domain | Type `https://192-168-137-1.sslip.io:8000` exactly |
| "TLS certificate errors" | Old CA cert left on phone, cert mismatch | Delete old certs in phone settings, reinstall `rootCA.crt` |
| `(venv)` not appearing | Execution policy blocked | Run: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| "Address already in use" | Old server still running | Close the old terminal window |
| Django errors / 500 page | Database not migrated | Run: `python manage.py migrate` |

---

## File Reference

| File | Purpose |
|---|---|
| `192-168-137-1.sslip.io+3.pem` | TLS certificate for the server |
| `192-168-137-1.sslip.io+3-key.pem` | TLS private key |
| `rootCA.crt` | Install this on every student phone once |
| `start_server.ps1` | Run this to start the server |
| `.env` | Database credentials (do not share) |
