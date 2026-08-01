import os
import json
import base64
import csv
import logging
import ipaddress
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from openpyxl import Workbook

from core.models import (
    AttendanceSession,
    AttendanceRecord,
    PasskeyCredential,
    AttendanceAttempt,
    SecurityMode
)
from core.session_service import create_attendance_session
from core.attendance_service import verify_session_integrity
from core.student_service import (
    get_face_models,
    register_student_face_embedding,
    verify_student_face,
    revoke_student_face
)
from core.rate_limit import rate_limit_request
from core.presence_service import record_presence_heartbeat
from core.secure_presence_v2_service import (
    start_attendance_attempt,
    process_liveness_verification,
    issue_signing_challenge_v2,
    submit_attendance_v2
)
from core.webauthn_service import (
    generate_passkey_registration_options,
    verify_passkey_registration
)
from core.audit_service import verify_v2_session_integrity, close_session_audit_root
from core.liveness_challenge_service import issue_liveness_challenge, verify_liveness_nonce

logger = logging.getLogger(__name__)


import os
import json
import base64
import csv
import logging
import ipaddress
from datetime import timedelta
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from openpyxl import Workbook

from core.models import (
    User,
    AttendanceSession,
    AttendanceRecord,
    PasskeyCredential,
    AttendanceAttempt,
    SecurityMode,
    StudentProfile
)
from core.session_service import create_attendance_session
from core.attendance_service import verify_session_integrity
from core.student_service import (
    get_face_models,
    register_student_face_embedding,
    verify_student_face,
    revoke_student_face
)
from core.rate_limit import rate_limit_request
from core.presence_service import record_presence_heartbeat
from core.secure_presence_v2_service import (
    start_attendance_attempt,
    process_liveness_verification,
    issue_signing_challenge_v2,
    submit_attendance_v2
)
from core.webauthn_service import (
    generate_passkey_registration_options,
    verify_passkey_registration
)
from core.audit_service import verify_v2_session_integrity, close_session_audit_root
from core.liveness_challenge_service import issue_liveness_challenge, verify_liveness_nonce

logger = logging.getLogger(__name__)


# ---------- AUTH & DASHBOARD VIEWS ----------

@rate_limit_request(key_prefix="login", limit=10, window_seconds=60)
def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)
        if user:
            login(request, user)
            if user.role == "professor":
                return redirect("teacher_dashboard")
            else:
                return redirect("student_dashboard")
        else:
            return render(request, "login.html", {"error": "Invalid Email or Password."})

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def teacher_dashboard(request):
    if request.user.role != "professor":
        return redirect("login")

    now = timezone.now()
    # Home page shows only currently active (live) sessions for this professor
    active_sessions = AttendanceSession.objects.filter(
        professor=request.user,
        active=True,
        expiry__gt=now
    ).order_by("-timestamp")

    active_list = []
    for s in active_sessions:
        records = AttendanceRecord.objects.filter(session=s).select_related("student").order_by("-timestamp")
        active_list.append({
            "session": s,
            "records": records,
            "record_count": records.count(),
        })

    return render(request, "teacher_dashboard.html", {
        "active_sessions": active_list,
    })


@login_required
def session_history_view(request):
    if request.user.role != "professor":
        return redirect("login")

    thirty_days_ago = timezone.now() - timedelta(days=30)
    search_query = request.GET.get("q", "").strip()

    sessions = AttendanceSession.objects.filter(
        professor=request.user,
        timestamp__gte=thirty_days_ago
    )
    if search_query:
        sessions = sessions.filter(course_code__icontains=search_query)

    sessions = sessions.order_by("-timestamp")

    now = timezone.now()
    session_history = []
    for s in sessions:
        records = AttendanceRecord.objects.filter(session=s).select_related("student").order_by("-timestamp")
        session_history.append({
            "session": s,
            "records": records,
            "record_count": records.count(),
            "is_active": s.active and s.expiry > now,
        })

    return render(request, "session_history.html", {
        "session_history": session_history,
        "search_query": search_query,
    })


@login_required
def admin_dashboard(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect("teacher_dashboard")

    students = User.objects.filter(role="student").order_by("email")
    student_credentials = []
    passkey_count = 0
    face_count = 0

    for st in students:
        passkey = PasskeyCredential.objects.filter(student=st, revoked=False).first()
        has_face = os.path.exists(f"embeddings/{st.id}.npy") or StudentProfile.objects.filter(user=st).exists()
        
        if passkey:
            passkey_count += 1
        if has_face:
            face_count += 1

        student_credentials.append({
            "student": st,
            "passkey": passkey,
            "has_face": has_face,
        })

    return render(request, "admin_dashboard.html", {
        "student_credentials": student_credentials,
        "total_students": len(student_credentials),
        "passkey_count": passkey_count,
        "face_count": face_count,
    })


@login_required
def start_session(request):
    if request.user.role != "professor":
        return redirect("login")

    if request.method == "POST":
        course_code = request.POST.get("course_code")
        security_mode = SecurityMode.SECURE_PRESENCE_V2

        import socket
        gateway_ip = None
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None):
                addr = info[4][0]
                try:
                    parsed = ipaddress.ip_address(addr)
                    if not parsed.is_loopback and parsed.version == 4:
                        if str(parsed).startswith("192.168.137."):
                            gateway_ip = str(parsed)
                            break
                        elif gateway_ip is None:
                            gateway_ip = str(parsed)
                except ValueError:
                    continue
        except Exception:
            pass

        if not gateway_ip:
            gateway_ip = request.META.get("SERVER_ADDR") or request.META.get("REMOTE_ADDR", "127.0.0.1")

        network = ipaddress.ip_network(gateway_ip + "/24", strict=False)
        subnet_range = str(network)

        create_attendance_session(
            professor=request.user,
            course_code=course_code,
            gateway_ip=gateway_ip,
            subnet_range=subnet_range,
            security_mode=security_mode
        )
        return redirect("teacher_dashboard")

    return render(request, "start_session.html")


@login_required
def student_dashboard(request):
    if request.user.role != "student":
        return redirect("login")

    active_sessions = AttendanceSession.objects.filter(
        active=True,
        expiry__gt=timezone.now()
    )

    has_passkey = PasskeyCredential.objects.filter(student=request.user, revoked=False).exists()
    has_face = os.path.exists(f"embeddings/{request.user.id}.npy") or StudentProfile.objects.filter(user=request.user).exists()
    is_fully_registered = has_passkey and has_face

    return render(request, "student_dashboard.html", {
        "sessions": active_sessions,
        "has_passkey": has_passkey,
        "has_face": has_face,
        "is_fully_registered": is_fully_registered,
    })


# ---------- LEGACY FLOW VIEWS ----------

@login_required
def register_device_view(request):
    if request.method == "GET":
        return render(request, "student_register_device.html")

    if request.method == "POST":
        data = json.loads(request.body)
        public_key = data.get("public_key")

        register_device(
            user=request.user,
            public_key_pem=public_key,
            device_info_string=request.META.get('HTTP_USER_AGENT', '')
        )

        return JsonResponse({"status": "success"})


@login_required
@rate_limit_request(key_prefix="submit_legacy", limit=5, window_seconds=60)
def submit_attendance_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    session_id = data.get("session_id")
    signed_nonce = data.get("signed_nonce")
    client_ip = request.META.get("REMOTE_ADDR")

    success, message = submit_attendance(
        user=request.user,
        session_id=session_id,
        signed_nonce=signed_nonce,
        client_ip=client_ip
    )

    return JsonResponse({
        "status": "success" if success else "error",
        "message": message
    })


@login_required
def verify_integrity_view(request, session_id):
    if request.user.role != "professor":
        return redirect("login")

    session = AttendanceSession.objects.filter(id=session_id, professor=request.user).first()
    if not session:
        return redirect("teacher_dashboard")

    if session.security_mode == SecurityMode.SECURE_PRESENCE_V2:
        result = verify_v2_session_integrity(session_id)
    else:
        result = {"valid": verify_session_integrity(session_id)}

    return render(request, "integrity_result.html", {
        "result": result,
        "session": session
    })


@login_required
def export_xlsx(request, session_id):
    session = AttendanceSession.objects.get(id=session_id, professor=request.user)
    records = AttendanceRecord.objects.filter(session=session).select_related("student")

    wb = Workbook()
    ws = wb.active
    ws.append(["Student", "Timestamp", "IP"])

    for r in records:
        ist_time = timezone.localtime(r.timestamp)
        ws.append([r.student.email, ist_time.strftime("%Y-%m-%d %H:%M:%S"), r.client_ip])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f'attachment; filename="attendance_{session.course_code}.xlsx"'

    wb.save(response)
    return response


@login_required
def export_csv(request, session_id):
    session = AttendanceSession.objects.get(id=session_id, professor=request.user)
    records = AttendanceRecord.objects.filter(session=session).select_related("student")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="attendance_{session.course_code}.csv"'

    writer = csv.writer(response)
    writer.writerow(["Student", "Timestamp", "IP"])

    for r in records:
        ist_time = timezone.localtime(r.timestamp)
        writer.writerow([r.student.email, ist_time.strftime("%Y-%m-%d %H:%M:%S"), r.client_ip])

    return response


# ---------- OPTIMIZED DECOUPLED BIOMETRIC VIEWS ----------

@login_required
def check_face_status(request):
    if request.user.role != "student":
        return JsonResponse({"registered": False, "error": "Unauthorized"}, status=403)

    embedding_path = f"embeddings/{request.user.id}.npy"
    is_registered = os.path.exists(embedding_path) or StudentProfile.objects.filter(user=request.user).exists()
    return JsonResponse({"registered": is_registered, "user_id": str(request.user.id)})


@login_required
@rate_limit_request(key_prefix="register_face", limit=5, window_seconds=60)
def register_face(request):
    if request.user.role != "student":
        return JsonResponse({"status": "fail", "message": "Unauthorized"}, status=403)

    if request.method != "POST":
        return JsonResponse({"status": "fail", "message": "Invalid method"}, status=400)

    try:
        data = json.loads(request.body)
        image_data = data["image"].split(",")[1]
        image_bytes = base64.b64decode(image_data)

        import cv2
        import numpy as np
        from PIL import Image

        mtcnn, resnet = get_face_models()

        np_img = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

        if frame is None:
            return JsonResponse({"status": "fail", "message": "Invalid image payload"})

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)

        face = mtcnn(img)
        if face is None:
            return JsonResponse({"status": "fail", "message": "No face detected in frame. Align face clearly."})

        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        face_tensor = face.unsqueeze(0).to(device)

        with torch.no_grad():
            embedding = resnet(face_tensor)

        embedding_np = embedding.cpu().numpy()
        success, msg = register_student_face_embedding(request.user, embedding_np)

        return JsonResponse({"status": "success" if success else "fail", "message": msg})

    except Exception as e:
        logger.error("Error during face registration: %s", str(e))
        return JsonResponse({"status": "fail", "message": "Face registration error"}, status=500)


@login_required
@rate_limit_request(key_prefix="face_verify", limit=5, window_seconds=60)
def face_verify(request):
    if request.user.role != "student":
        return JsonResponse({"status": "fail", "message": "Unauthorized"}, status=403)

    if request.method != "POST":
        return JsonResponse({"status": "fail", "message": "Invalid method"}, status=400)

    try:
        data = json.loads(request.body)
        image_data = data["image"].split(",")[1]
        image_bytes = base64.b64decode(image_data)

        import cv2
        import numpy as np
        from PIL import Image

        mtcnn, resnet = get_face_models()

        np_img = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

        if frame is None:
            return JsonResponse({"status": "fail", "message": "Invalid image payload"})

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)

        face = mtcnn(img)
        if face is None:
            return JsonResponse({"status": "fail", "message": "No face detected"})

        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        face_tensor = face.unsqueeze(0).to(device)

        with torch.no_grad():
            embedding = resnet(face_tensor)

        embedding_np = embedding.cpu().numpy()
        match_ok, score, msg = verify_student_face(str(request.user.id), embedding_np, threshold=0.7)

        if match_ok:
            return JsonResponse({"status": "success", "score": score})
        else:
            return JsonResponse({"status": "fail", "message": msg, "score": score})

    except Exception as e:
        logger.error("Error during face verification: %s", str(e))
        return JsonResponse({"status": "fail", "message": "Verification error"}, status=500)


@login_required
def revoke_student_face_view(request, student_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({"error": "Forbidden: Admin privileges required"}, status=403)

    target_student = User.objects.filter(id=student_id, role="student").first()
    if target_student:
        revoke_student_face(target_student)

    return redirect("teacher_dashboard")


# ---------- SECURE PRESENCE V2 ENDPOINTS ----------

@login_required
@rate_limit_request(key_prefix="passkey_reg_opt", limit=5, window_seconds=60)
def passkey_register_options_view(request):
    if request.user.role != "student":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    try:
        options_dict, challenge_b64url = generate_passkey_registration_options(request.user)
        request.session["passkey_reg_challenge"] = challenge_b64url
        return JsonResponse(options_dict)
    except Exception as e:
        logger.error("Passkey registration options error: %s", str(e))
        return JsonResponse({"error": "Failed to generate passkey options"}, status=500)


@login_required
@rate_limit_request(key_prefix="passkey_reg_verify", limit=5, window_seconds=60)
def passkey_register_verify_view(request):
    if request.user.role != "student":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    expected_challenge = request.session.get("passkey_reg_challenge")
    if not expected_challenge:
        return JsonResponse({"error": "No registration challenge found in session"}, status=400)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        success, passkey, message = verify_passkey_registration(
            user=request.user,
            credential_payload=payload,
            expected_challenge=expected_challenge
        )
        if success:
            request.session.pop("passkey_reg_challenge", None)
            return JsonResponse({"status": "success", "message": message})
        else:
            return JsonResponse({"status": "error", "message": message}, status=400)
    except Exception as e:
        logger.error("Passkey registration verification error: %s", str(e))
        return JsonResponse({"error": "Passkey registration verification failed"}, status=400)


@login_required
@rate_limit_request(key_prefix="v2_start_attempt", limit=5, window_seconds=60)
def start_attempt_v2_view(request):
    if request.user.role != "student":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))
        session_id = data.get("session_id")
        client_ip = request.META.get("REMOTE_ADDR")

        success, attempt, message = start_attendance_attempt(
            user=request.user,
            session_id=session_id,
            client_ip=client_ip
        )
        if success:
            return JsonResponse({
                "status": "success",
                "attempt_id": str(attempt.id),
                "message": message
            })
        else:
            return JsonResponse({"status": "error", "message": message}, status=400)
    except Exception as e:
        logger.error("Error starting V2 attempt: %s", str(e))
        return JsonResponse({"error": "Failed to start attendance attempt"}, status=400)


@login_required
def presence_heartbeat_v2_view(request):
    if request.user.role != "student":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))
        attempt_id = data.get("attempt_id")

        attempt = AttendanceAttempt.objects.filter(id=attempt_id, student=request.user).first()
        if not attempt:
            return JsonResponse({"error": "Attempt not found"}, status=404)

        client_ip = request.META.get("REMOTE_ADDR")
        heartbeat = record_presence_heartbeat(attempt, request.user, client_ip)

        return JsonResponse({
            "status": "success" if heartbeat.valid else "error",
            "valid": heartbeat.valid
        })
    except Exception as e:
        return JsonResponse({"error": "Heartbeat processing error"}, status=400)


@login_required
@rate_limit_request(key_prefix="v2_liveness_challenge", limit=10, window_seconds=60)
def liveness_challenge_view(request):
    """GET — Issue a random liveness challenge + signed nonce for the given attempt."""
    if request.user.role != "student":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    attempt_id = request.GET.get("attempt_id")
    if not attempt_id:
        return JsonResponse({"error": "attempt_id required"}, status=400)

    # Verify this attempt belongs to the requesting student
    attempt = AttendanceAttempt.objects.filter(id=attempt_id, student=request.user).first()
    if not attempt:
        return JsonResponse({"error": "Attempt not found"}, status=404)

    challenge_data = issue_liveness_challenge(attempt_id)
    return JsonResponse({"status": "success", **challenge_data})


@login_required
@rate_limit_request(key_prefix="v2_verify_liveness", limit=5, window_seconds=60)
def verify_liveness_v2_view(request):
    """POST — Verify the HMAC nonce echoed back by the client after completing the challenge."""
    if request.user.role != "student":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))
        attempt_id = data.get("attempt_id")
        nonce = data.get("nonce", "")

        # Validate the nonce (proves the client received a genuine server challenge)
        nonce_ok, nonce_reason = verify_liveness_nonce(attempt_id, nonce)
        if not nonce_ok:
            logger.warning(
                "Liveness nonce validation failed attempt=%s reason=%s user=%s",
                attempt_id, nonce_reason, request.user.id
            )
            return JsonResponse(
                {"status": "error", "message": f"Liveness check failed: {nonce_reason}"},
                status=400
            )

        # Pass a sentinel image payload — nonce-based verifier does not need image bytes
        success, verification, message = process_liveness_verification(
            attempt_id=attempt_id,
            user=request.user,
            image_payload="nonce_verified"
        )

        return JsonResponse({
            "status": "success" if success else "error",
            "message": message
        }, status=200 if success else 400)
    except Exception as e:
        logger.error("Liveness verification endpoint error: %s", str(e))
        return JsonResponse({"error": "Liveness verification processing error"}, status=500)


@login_required
@rate_limit_request(key_prefix="v2_request_challenge", limit=5, window_seconds=60)
def passkey_authenticate_options_view(request):
    if request.user.role != "student":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))
        attempt_id = data.get("attempt_id")

        success, options_dict, message = issue_signing_challenge_v2(
            attempt_id=attempt_id,
            user=request.user
        )

        if success:
            return JsonResponse({
                "status": "success",
                "options": options_dict
            })
        else:
            return JsonResponse({"status": "error", "message": message}, status=400)
    except Exception as e:
        logger.error("Passkey auth options error: %s", str(e))
        return JsonResponse({"error": "Challenge generation error"}, status=400)


@login_required
@rate_limit_request(key_prefix="v2_submit", limit=3, window_seconds=60)
def submit_attendance_v2_view(request):
    if request.user.role != "student":
        return JsonResponse({"error": "Unauthorized"}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))
        attempt_id = data.get("attempt_id")
        credential_payload = data.get("credential")
        client_ip = request.META.get("REMOTE_ADDR")

        success, message = submit_attendance_v2(
            user=request.user,
            attempt_id=attempt_id,
            credential_payload=credential_payload,
            client_ip=client_ip
        )

        return JsonResponse({
            "status": "success" if success else "error",
            "message": message
        }, status=200 if success else 400)
    except Exception as e:
        logger.error("Secure V2 submit error: %s", str(e))
        return JsonResponse({"error": "Submission processing error"}, status=500)


@login_required
def revoke_passkey_v2_view(request, passkey_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({"error": "Forbidden: Admin privileges required"}, status=403)

    passkey = PasskeyCredential.objects.filter(id=passkey_id).first()
    if passkey:
        passkey.revoked = True
        passkey.save(update_fields=['revoked'])

    return redirect("teacher_dashboard")
