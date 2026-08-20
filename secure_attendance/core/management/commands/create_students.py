"""
Management command to bulk create user accounts (student/professor).
"""
from django.core.management.base import BaseCommand
from core.models import User


class Command(BaseCommand):
    help = "Bulk create user profiles with flexible ranges, roles, domains, and passwords"

    def add_arguments(self, parser):
        parser.add_argument(
            '--start',
            type=int,
            default=1,
            help='Start index for numbering (default: 1)'
        )
        parser.add_argument(
            '--end',
            type=int,
            default=10,
            help='End index for numbering (default: 10)'
        )
        parser.add_argument(
            '--count',
            type=int,
            default=None,
            help='Number of accounts to create (overrides --end if specified)'
        )
        parser.add_argument(
            '--prefix',
            type=str,
            default='student',
            help='Email prefix, e.g. student3@test.com (default: student)'
        )
        parser.add_argument(
            '--domain',
            type=str,
            default='test.com',
            help='Email domain (default: test.com)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='1234',
            help='Password for created accounts (default: 1234)'
        )
        parser.add_argument(
            '--role',
            type=str,
            choices=['student', 'professor'],
            default='student',
            help='Role for created users: student or professor (default: student)'
        )
        parser.add_argument(
            '--email',
            type=str,
            default=None,
            help='Create a single specific user with this exact email'
        )

    def handle(self, *args, **options):
        start = options['start']
        end = options['end']
        count = options['count']
        prefix = options['prefix']
        domain = options['domain']
        password = options['password']
        role = options['role']
        single_email = options['email']

        if single_email:
            if User.objects.filter(email=single_email).exists():
                self.stdout.write(self.style.WARNING(f"[SKIPPED] User {single_email} already exists."))
            else:
                User.objects.create_user(email=single_email, password=password, role=role)
                self.stdout.write(self.style.SUCCESS(f"[CREATED] {single_email} (role: {role}, password: {password})"))
            return

        self.stdout.write(
            f"Creating {role} accounts: {prefix}{start}@{domain} to {prefix}{end}@{domain}...\n"
        )

        created_count = 0
        skipped_count = 0

        for i in range(start, end + 1):
            email = f"{prefix}{i}@{domain}"
            if User.objects.filter(email=email).exists():
                self.stdout.write(self.style.WARNING(f"  [SKIPPED] {email} already exists"))
                skipped_count += 1
            else:
                User.objects.create_user(email=email, password=password, role=role)
                self.stdout.write(self.style.SUCCESS(f"  [CREATED] {email} (role: {role})"))
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nSummary: {created_count} {role}(s) created, {skipped_count} skipped."
        ))
        self.stdout.write(f"Password set for created accounts: {password}\n")
