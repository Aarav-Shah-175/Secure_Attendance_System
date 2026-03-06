from django.contrib import admin# type: ignore
from django.urls import path# type: ignore
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/start-session/', views.start_session, name='start_session'),

    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/register-device/', views.register_device_view, name='register_device'),
    path('student/submit/', views.submit_attendance_view, name='submit_attendance'),
    path('teacher/verify/<uuid:session_id>/', views.verify_integrity_view, name='verify_integrity'),
    path('teacher/export-csv/<uuid:session_id>/', views.export_csv, name='export_csv'),
    path('teacher/export-xlsx/<uuid:session_id>/', views.export_xlsx, name='export_xlsx'),
    path("student/face-verify/", views.face_verify),

]