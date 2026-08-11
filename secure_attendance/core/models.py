import uuid
from django.db import models  # type: ignore
from django.contrib.auth.models import (  # type: ignore
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin
)
from core.crypto_utils import generate_ecdsa_keypair, aes_encrypt  # type: ignore

# ---------------------------------------------------------------------------
# NOTE ON ARCHITECTURE (v3 — Agent-based network verification)
# ---------------------------------------------------------------------------
# gateway_ip and subnet_range on AttendanceSession are kept for backward
# compatibility with existing records. They are no longer used for verification.
# Network verification is now handled by the standalone Attendance Agent
# via HMAC-SHA256 challenge-response.  See core/agent_verification.py.
# ---------------------------------------------------------------------------


class SecurityMode(models.TextChoices):
    LEGACY = "legacy", "Legacy"
    SECURE_PRESENCE_V2 = "secure_presence_v2", "Secure Presence V2"


class AttemptStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    LIVENESS_PENDING = "LIVENESS_PENDING", "Liveness Pending"
    BIOMETRIC_VERIFIED = "BIOMETRIC_VERIFIED", "Biometric Verified"
    CHALLENGE_ISSUED = "CHALLENGE_ISSUED", "Challenge Issued"
    SIGNED = "SIGNED", "Signed"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    EXPIRED = "EXPIRED", "Expired"


class LivenessStatus(models.TextChoices):
    PASSED = "PASSED", "Passed"
    FAILED = "FAILED", "Failed"
    ERROR = "ERROR", "Error"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, role='student'):
        if not email:
            raise ValueError("Users must have an email address")

        email = self.normalize_email(email)
        user = self.model(email=email, role=role)
        user.set_password(password)

        if role == 'professor':
            private_key, public_key = generate_ecdsa_keypair()
            encrypted_private = aes_encrypt(private_key.encode())
            user.public_key = public_key
            user.private_key_encrypted = encrypted_private

        user.save(using=self._db)
        return user

    def create_superuser(self, email, password):
        user = self.create_user(
            email=email,
            password=password,
            role='professor'
        )
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('professor', 'Professor'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    totp_secret = models.CharField(max_length=255, null=True, blank=True)
    public_key = models.TextField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    private_key_encrypted = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class AttendanceSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professor = models.ForeignKey(User, on_delete=models.CASCADE)
    course_code = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    expiry = models.DateTimeField()
    network_nonce = models.TextField()
    session_signature = models.TextField()
    # Kept for backward compatibility; no longer used for verification.
    # Set to '0.0.0.0' / 'agent' when session was started via Attendance Agent.
    gateway_ip = models.GenericIPAddressField(null=True, blank=True)
    subnet_range = models.CharField(max_length=50, blank=True, default='agent')
    # Attendance Agent fields
    session_secret_hash = models.CharField(max_length=64, blank=True, default='')  # SHA256(session_secret)
    agent_id = models.CharField(max_length=64, blank=True, default='')
    active = models.BooleanField(default=True)
    security_mode = models.CharField(
        max_length=30,
        choices=SecurityMode.choices,
        default=SecurityMode.LEGACY
    )

    class Meta:
        indexes = [
            models.Index(fields=['active', 'expiry', 'security_mode']),
            models.Index(fields=['professor', 'active']),
        ]

    def __str__(self):
        return f"{self.course_code} ({self.security_mode})"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    encrypted_face_embedding = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Device(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    public_key = models.TextField()
    fingerprint_hash = models.CharField(max_length=256)
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['student', 'revoked']),
        ]


class PasskeyCredential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='passkeys')
    credential_id = models.CharField(max_length=512, unique=True, db_index=True)
    public_key = models.TextField()
    sign_counter = models.BigIntegerField(default=0)
    credential_metadata = models.JSONField(default=dict, blank=True)
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['student', 'revoked']),
        ]

    def __str__(self):
        return f"Passkey({self.credential_id[:16]}...) - {self.student.email}"


class AttendanceAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_attempts')
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='attempts')
    passkey_credential = models.ForeignKey(
        PasskeyCredential,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attempts'
    )
    client_ip = models.GenericIPAddressField()
    status = models.CharField(
        max_length=30,
        choices=AttemptStatus.choices,
        default=AttemptStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    signing_challenge = models.TextField(null=True, blank=True)
    challenge_issued_at = models.DateTimeField(null=True, blank=True)
    challenge_expires_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)
    # Agent challenge proof fields (set during start_attempt)
    agent_challenge_nonce = models.CharField(max_length=64, blank=True, null=True)
    agent_challenge_ts = models.BigIntegerField(null=True, blank=True)
    agent_proof_verified = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['session', 'student', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]

    def __str__(self):
        return f"Attempt({self.id}) - {self.student.email} [{self.status}]"


class LivenessVerification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.OneToOneField(
        AttendanceAttempt,
        on_delete=models.CASCADE,
        related_name='liveness_verification'
    )
    status = models.CharField(max_length=20, choices=LivenessStatus.choices)
    score = models.FloatField(null=True, blank=True)
    verifier_name = models.CharField(max_length=100)
    verifier_version = models.CharField(max_length=50)
    reason_code = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"Liveness({self.status}) for Attempt {self.attempt_id}"


class PresenceHeartbeat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(AttendanceAttempt, on_delete=models.CASCADE, related_name='heartbeats')
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    client_ip = models.GenericIPAddressField()
    timestamp = models.DateTimeField(auto_now_add=True)
    valid = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['attempt', 'student', 'timestamp']),
        ]


class AttendanceRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    client_ip = models.GenericIPAddressField()
    record_hash = models.CharField(max_length=256)
    chained_hash = models.CharField(max_length=256)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'session'],
                name='unique_student_session_attendance'
            )
        ]

    def __str__(self):
        return f"{self.student.email} - {self.session.course_code}"


class AttendanceAuditEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='audit_entries')
    record = models.OneToOneField(AttendanceRecord, on_delete=models.CASCADE, related_name='audit_entry')
    canonical_report_hash = models.CharField(max_length=64)
    previous_entry_hash = models.CharField(max_length=64, null=True, blank=True)
    entry_signature = models.TextField()
    signed_at = models.DateTimeField(auto_now_add=True)
    verification_references = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['session', 'signed_at']),
        ]


class AttendanceSessionAuditRoot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(AttendanceSession, on_delete=models.CASCADE, related_name='audit_root')
    root_hash = models.CharField(max_length=64)
    signature = models.TextField()
    signed_at = models.DateTimeField(auto_now_add=True)
    closed = models.BooleanField(default=False)

    def __str__(self):
        return f"AuditRoot({self.session.course_code}) - Closed: {self.closed}"


class AttendanceAgent(models.Model):
    """
    Represents a registered professor Attendance Agent instance.
    Each professor laptop has one agent identity (Ed25519 public key).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professor = models.OneToOneField(
        'User',
        on_delete=models.CASCADE,
        related_name='attendance_agent',
        null=True,
        blank=True,
    )
    agent_id = models.CharField(max_length=64, unique=True, db_index=True)
    public_key_pem = models.TextField()  # Ed25519 public key in PEM format
    x25519_public_key_pem = models.TextField(blank=True, default='')  # X25519 key for secret delivery
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['agent_id']),
            models.Index(fields=['last_heartbeat']),
        ]

    def __str__(self):
        return f"Agent({self.agent_id[:8]}...) - {self.professor.email if self.professor else 'unassigned'}"