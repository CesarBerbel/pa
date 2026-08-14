from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, WebAuthnCredential


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Admin configuration for the custom user model

    model = User

    list_display = [
        "email",
        "full_name",
        "phone",
        "is_internal_staff",
        "can_access_clinical_data",
        "is_active",
    ]

    list_filter = [
        "is_internal_staff",
        "can_access_clinical_data",
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
        (
            "Acesso ao sistema",
            {
                "fields": (
                    "is_internal_staff",
                    "can_access_clinical_data",
                ),
                "description": (
                    "Quem trabalha na receção precisa apenas do acesso à área "
                    "interna. O acesso a dados clínicos é reservado a quem "
                    "presta os cuidados."
                ),
            },
        ),
        (
            "Permissions",
            {
                "classes": ("collapse",),
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "full_name",
                    "phone",
                    "password1",
                    "password2",
                    "is_internal_staff",
                    "can_access_clinical_data",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(WebAuthnCredential)
class WebAuthnCredentialAdmin(admin.ModelAdmin):
    # Só de leitura: uma credencial nasce da cerimónia com o aparelho e não
    # pode ser escrita à mão. O que faz sentido daqui é ver quem tem o quê e
    # revogar um aparelho perdido.

    list_display = [
        "name",
        "user",
        "created_at",
        "last_used_at",
        "sign_count",
    ]

    list_filter = [
        "created_at",
        "last_used_at",
    ]

    search_fields = [
        "name",
        "user__email",
        "user__full_name",
    ]

    ordering = [
        "-created_at",
    ]

    readonly_fields = [
        "user",
        "credential_id",
        "public_key",
        "sign_count",
        "name",
        "created_at",
        "last_used_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
