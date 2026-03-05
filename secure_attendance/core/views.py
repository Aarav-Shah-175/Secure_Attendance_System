from django.shortcuts import render, redirect # type: ignore
from django.contrib.auth import authenticate, login, logout# type: ignore
from django.contrib.auth.decorators import login_required# type: ignore
from core.models import AttendanceSession, AttendanceRecord
from core.session_service import create_attendance_session
from core.attendance_service import submit_attendance
from django.utils import timezone # type: ignore
import json
from django.http import JsonResponse# type: ignore
from core.student_service import register_device
import ipaddress
import csv
from django.http import HttpResponse#type: ignore
from openpyxl import Workbook#type: ignore

@login_required
def export_xlsx(request, session_id):

    session = AttendanceSession.objects.get(id=session_id, professor=request.user)
    records = AttendanceRecord.objects.filter(session=session).select_related("student")

    wb = Workbook()
    ws = wb.active
    ws.append(["Student", "Timestamp", "IP"])

    for r in records:
        ws.append([r.student.email, str(r.timestamp), r.client_ip])

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
        writer.writerow([r.student.email, r.timestamp, r.client_ip])

    return response

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
            device_info_string=request.META.get('HTTP_USER_AGENT')
        )

        return JsonResponse({"status": "success"})

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

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("login")

@login_required
def teacher_dashboard(request):
    sessions = AttendanceSession.objects.filter(professor=request.user, active=True)

    attendance_records = AttendanceRecord.objects.filter(
        session__in=sessions
    ).select_related("student")

    return render(request, "teacher_dashboard.html", {
        "sessions": sessions,
        "attendance_records": attendance_records
    })


@login_required
def start_session(request):
    if request.user.role != "professor":
        return redirect("login")

    if request.method == "POST":
        course_code = request.POST.get("course_code")

        # Get the IP used to access server
        host_ip = request.get_host().split(":")[0]

        # Build subnet from that
        network = ipaddress.ip_network(host_ip + "/24", strict=False)
        subnet_range = str(network)

        session = create_attendance_session(
            professor=request.user,
            course_code=course_code,
            gateway_ip=host_ip,
            subnet_range=subnet_range
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

    return render(request, "student_dashboard.html", {
        "sessions": active_sessions
    })


@login_required
def submit_attendance_view(request):

    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception as e:
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

from core.attendance_service import verify_session_integrity


@login_required
def verify_integrity_view(request, session_id):
    if request.user.role != "professor":
        return redirect("login")

    result = verify_session_integrity(session_id)

    return render(request, "integrity_result.html", {
        "result": result
    })


