from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Teacher & Admin endpoints
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/start-session/', views.start_session, name='start_session'),
    path('teacher/verify/<uuid:session_id>/', views.verify_integrity_view, name='verify_integrity'),
    path('teacher/export-csv/<uuid:session_id>/', views.export_csv, name='export_csv'),
    path('teacher/export-xlsx/<uuid:session_id>/', views.export_xlsx, name='export_xlsx'),
    path('teacher/revoke-passkey/<uuid:passkey_id>/', views.revoke_passkey_v2_view, name='revoke_passkey'),
    path('teacher/revoke-face/<uuid:student_id>/', views.revoke_student_face_view, name='revoke_face'),

    # Student biometric & core endpoints
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/face-verify/', views.face_verify, name='face_verify'),
    path('student/register-face/', views.register_face, name='register_face'),
    path('student/face-status/', views.check_face_status, name='check_face_status'),

    # Secure Presence V2 endpoints
    path('student/passkey/register/options/', views.passkey_register_options_view, name='passkey_register_options'),
    path('student/passkey/register/verify/', views.passkey_register_verify_view, name='passkey_register_verify'),
    path('student/secure-v2/start-attempt/', views.start_attempt_v2_view, name='start_attempt_v2'),
    path('student/presence/heartbeat/', views.presence_heartbeat_v2_view, name='presence_heartbeat_v2'),
    path('student/secure-v2/liveness-challenge/', views.liveness_challenge_view, name='liveness_challenge'),
    path('student/secure-v2/verify-liveness/', views.verify_liveness_v2_view, name='verify_liveness_v2'),
    path('student/secure-v2/request-challenge/', views.passkey_authenticate_options_view, name='passkey_authenticate_options'),
    path('student/secure-v2/submit/', views.submit_attendance_v2_view, name='submit_attendance_v2'),
]