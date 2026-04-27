from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Admin configuration for the custom user model

    model = User

    list_display = [
        "email",
        "full_name",
        "phone",
        "is_staff",
        "is_active",
    ]

    list_filter = [
        "is_staff",
        "is_active",
        "is_superuser",
    ]

    search_fields = [
        "email",
        "full_name",
        "phone",
    ]

    ordering = [
        "email",
    ]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal information", {"fields": ("full_name", "phone")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "phone", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )