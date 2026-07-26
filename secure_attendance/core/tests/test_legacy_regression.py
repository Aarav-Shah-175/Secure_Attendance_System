import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from core.models import User, AttendanceSession, AttendanceRecord, Device, SecurityMode
from core.session_service import create_attendance_session
from core.student_service import register_device
from core.crypto_utils import generate_ecdsa_keypair, sign_data, sha256_hash


class LegacyRegressionTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.professor = User.objects.create_user(
            email="prof@university.edu",
            password="ProfPassword123!",
            role="professor"
        )
        self.student = User.objects.create_user(
            email="student@university.edu",
            password="StudentPassword123!",
            role="student"
        )
        # Register a legacy device for student
        self.private_key_pem, self.public_key_pem = generate_ecdsa_keypair()
        self.device = register_device(
            user=self.student,
            public_key_pem=self.public_key_pem,
            device_info_string="Mozilla/5.0 TestBrowser"
        )

    def test_legacy_session_creation(self):
        self.client.login(email="prof@university.edu", password="ProfPassword123!")
        session = create_attendance_session(
            professor=self.professor,
            course_code="CS101",
            gateway_ip="127.0.0.1",
            subnet_range="127.0.0.0/24",
            security_mode=SecurityMode.LEGACY
        )
        self.assertEqual(session.security_mode, SecurityMode.LEGACY)
        self.assertTrue(session.active)

    def test_legacy_attendance_submission(self):
        self.client.login(email="prof@university.edu", password="ProfPassword123!")
        session = create_attendance_session(
            professor=self.professor,
            course_code="CS101",
            gateway_ip="127.0.0.1",
            subnet_range="127.0.0.0/24",
            security_mode=SecurityMode.LEGACY
        )

        self.client.login(email="student@university.edu", password="StudentPassword123!")
        
        # Sign session nonce
        signature_b64 = sign_data(self.private_key_pem, session.network_nonce.encode("utf-8"))

        response = self.client.post(
            reverse("submit_attendance"),
            data={
                "session_id": str(session.id),
                "signed_nonce": signature_b64
            },
            content_type="application/json",
            REMOTE_ADDR="127.0.0.1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "success")
        self.assertTrue(AttendanceRecord.objects.filter(student=self.student, session=session).exists())

    def test_legacy_session_integrity_check(self):
        self.client.login(email="prof@university.edu", password="ProfPassword123!")
        session = create_attendance_session(
            professor=self.professor,
            course_code="CS101",
            gateway_ip="127.0.0.1",
            subnet_range="127.0.0.0/24",
            security_mode=SecurityMode.LEGACY
        )

        record_hash = sha256_hash(str(self.student.id) + str(session.id))
        chained_hash = sha256_hash(record_hash)
        AttendanceRecord.objects.create(
            student=self.student,
            session=session,
            client_ip="127.0.0.1",
            record_hash=record_hash,
            chained_hash=chained_hash
        )

        response = self.client.get(reverse("verify_integrity", args=[session.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Integrity Check")

    def test_legacy_exports(self):
        self.client.login(email="prof@university.edu", password="ProfPassword123!")
        session = create_attendance_session(
            professor=self.professor,
            course_code="CS101",
            gateway_ip="127.0.0.1",
            subnet_range="127.0.0.0/24",
            security_mode=SecurityMode.LEGACY
        )
        csv_res = self.client.get(reverse("export_csv", args=[session.id]))
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res["Content-Type"], "text/csv")

        xlsx_res = self.client.get(reverse("export_xlsx", args=[session.id]))
        self.assertEqual(xlsx_res.status_code, 200)
        self.assertEqual(xlsx_res["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
