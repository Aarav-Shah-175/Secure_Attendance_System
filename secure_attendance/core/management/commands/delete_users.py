"""
Management command to bulk delete user profiles.
"""
from django.core.management.base import BaseCommand
from core.models import User, StudentProfile, PasskeyCredential, Device, AttendanceAttempt, AttendanceRecord


class Command(BaseCommand):
    help = "Bulk delete user profiles and associated credentials"

    def add_arguments(self, parser):
        parser.add_argument(
            '--domain',
            type=str,
            default=None,
            help='Delete all users matching this email domain (e.g. university.edu or test.com)'
        )
        parser.add_argument(
            '--prefix',
            type=str,
            default=None,
            help='Delete users with email prefix (e.g. student)'
        )
        parser.add_argument(
            '--start',
            type=int,
            default=None,
            help='Start index for range deletion'
        )
        parser.add_argument(
            '--end',
            type=int,
            default=None,
            help='End index for range deletion'
        )
        parser.add_argument(
            '--email',
            type=str,
            nargs='*',
            help='Specific email(s) to delete'
        )
        parser.add_argument(
            '--all-students',
            action='store_true',
            help='Delete ALL non-staff student accounts'
        )

    def handle(self, *args, **options):
        domain = options['domain']
        prefix = options['prefix']
        start = options['start']
        end = options['end']
        emails = options['email']
        all_students = options['all_students']

        users_to_delete = User.objects.none()

        if all_students:
            users_to_delete = User.objects.filter(role='student', is_staff=False, is_superuser=False)
        elif emails:
            users_to_delete = User.objects.filter(email__in=emails)
        elif domain:
            qs = User.objects.filter(email__icontains=f"@{domain}")
            if prefix and start is not None and end is not None:
                target_emails = [f"{prefix}{i}@{domain}" for i in range(start, end + 1)]
                qs = qs.filter(email__in=target_emails)
            elif prefix:
                qs = qs.filter(email__startswith=prefix)
            users_to_delete = qs
        elif prefix and start is not None and end is not None:
            # Match any domain with prefix and index range
            qs = User.objects.none()
            for u in User.objects.all():
                for i in range(start, end + 1):
                    if u.email.startswith(f"{prefix}{i}@"):
                        qs = qs | User.objects.filter(id=u.id)
            users_to_delete = qs

        count = users_to_delete.count()
        if count == 0:
            self.stdout.write(self.style.WARNING("No matching users found to delete."))
            return

        self.stdout.write(f"Found {count} user(s) to delete:")
        for u in users_to_delete:
            self.stdout.write(self.style.NOTICE(f"  - {u.email} (role: {u.role})"))

        deleted_emails = list(users_to_delete.values_list('email', flat=True))
        users_to_delete.delete()

        self.stdout.write(self.style.SUCCESS(
            f"\nSuccessfully deleted {len(deleted_emails)} user(s): {', '.join(deleted_emails)}"
        ))
