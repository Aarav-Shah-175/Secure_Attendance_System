from django.contrib import admin#type: ignore
from django.contrib.auth.admin import UserAdmin#type: ignore
from core.models import User, AttendanceSession, AttendanceRecord, Device


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ("email", "role", "is_staff", "is_active")
    ordering = ("email",)
    search_fields = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permissions", {"fields": ("is_staff", "is_active", "is_superuser", "groups", "user_permissions")}),
        ("Role", {"fields": ("role",)}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "role", "is_staff", "is_active")}
        ),
    )


admin.site.register(AttendanceSession)
admin.site.register(AttendanceRecord)
admin.site.register(Device)
