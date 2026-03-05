import uuid
from django.db import models    #type: ignore
from django.contrib.auth.models import ( # type: ignore
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin
)
from core.crypto_utils import generate_ecdsa_keypair, aes_encrypt #type: ignore




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

class AttendanceSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professor = models.ForeignKey(User, on_delete=models.CASCADE)
    course_code = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    expiry = models.DateTimeField()
    network_nonce = models.TextField()
    session_signature = models.TextField()
    gateway_ip = models.GenericIPAddressField()
    subnet_range = models.CharField(max_length=50)
    active = models.BooleanField(default=True)

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

class AttendanceRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    client_ip = models.GenericIPAddressField()
    record_hash = models.CharField(max_length=256)
    chained_hash = models.CharField(max_length=256)



    def __str__(self):
        return self.email