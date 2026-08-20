from django.contrib import admin

from .models import (
    Appointment,
    AppointmentLog,
    AppointmentReminderLog,
    BusinessHour,
    Customer,
    ScheduleBlock,
    ClinicalNote,
    PatientRecord,
    PatientRecordLog,
    Service,
    ServiceCategory,
)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "display_order",
        "name",
        "slug",
        "is_active",
        "is_coming_soon",
        "show_prices",
    )
    list_display_links = ("name",)
    list_editable = (
        "display_order",
        "is_active",
        "is_coming_soon",
        "show_prices",
    )
    list_filter = ("is_active", "is_coming_soon", "show_prices")
    search_fields = (
        "name",
        "slug",
        "description",
        "name_en",
    )
    prepopulated_fields = {
        "slug": ("name",),
    }
    fieldsets = (
        (None, {"fields": ("name", "slug", "description")}),
        (
            "Tradução para inglês (páginas em /en/)",
            {
                "fields": ("name_en", "description_en"),
                "description": (
                    "Campos opcionais. Quando ficam vazios, a versão em inglês "
                    "do site mostra o texto em português."
                ),
            },
        ),
        (
            None,
            {"fields": ("display_order", "is_active", "is_coming_soon", "show_prices")},
        ),
    )


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "duration_minutes",
        "price",
        "is_active",
    )
    list_filter = (
        "category",
        "is_active",
    )
    search_fields = (
        "name",
        "description",
        "category__name",
        "name_en",
    )
    autocomplete_fields = ("category",)
    fieldsets = (
        (None, {"fields": ("category", "name", "description")}),
        (
            "Tradução para inglês (páginas em /en/)",
            {
                "fields": ("name_en", "description_en"),
                "description": (
                    "Campos opcionais. Quando ficam vazios, a versão em inglês "
                    "do site mostra o texto em português."
                ),
            },
        ),
        (None, {"fields": ("duration_minutes", "price", "is_active")}),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "user")
    search_fields = ("full_name", "email", "phone")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "reference_code",
        "customer",
        "service",
        "date",
        "start_time",
        "status",
        "cancelled_at",
    )

    list_filter = (
        "status",
        "date",
        "service__category",
        "service",
        "cancelled_at",
    )

    search_fields = (
        "reference_code",
        "customer__full_name",
        "customer__email",
        "service__name",
        "service__category__name",
        "cancellation_reason",
    )

    readonly_fields = (
        "reference_code",
        "reminder_24h_sent_at",
        "reminder_2h_sent_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Dados da marcação",
            {
                "fields": (
                    "reference_code",
                    "customer",
                    "service",
                    "created_by",
                    "date",
                    "start_time",
                    "status",
                    "notes",
                )
            },
        ),
        (
            "Lembretes (histórico)",
            {
                "fields": (
                    "reminder_24h_sent_at",
                    "reminder_2h_sent_at",
                ),
                "description": (
                    "O envio de lembretes por email foi descontinuado. "
                    "Estas datas são o registo dos que chegaram a sair."
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Cancelamento",
            {
                "fields": (
                    "cancellation_reason",
                    "cancelled_at",
                )
            },
        ),
        (
            "Controle",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(ScheduleBlock)
class ScheduleBlockAdmin(admin.ModelAdmin):
    list_display = (
        "block_type",
        "date",
        "start_time",
        "end_time",
        "is_full_day",
        "is_recurring",
        "is_active",
    )

    list_filter = (
        "is_active",
        "is_full_day",
        "is_recurring",
        "block_type",
    )

    search_fields = ("notes",)


@admin.register(BusinessHour)
class BusinessHourAdmin(admin.ModelAdmin):
    list_display = (
        "weekday",
        "start_time",
        "end_time",
        "second_start_time",
        "second_end_time",
        "is_active",
    )
    list_editable = (
        "start_time",
        "end_time",
        "second_start_time",
        "second_end_time",
        "is_active",
    )
    list_filter = ("is_active",)


@admin.register(AppointmentLog)
class AppointmentLogAdmin(admin.ModelAdmin):
    list_display = (
        "appointment",
        "action",
        "performed_by",
        "created_at",
    )

    list_filter = (
        "action",
        "created_at",
    )

    search_fields = (
        "appointment__reference_code",
        "performed_by__email",
        "description",
    )

    readonly_fields = (
        "appointment",
        "action",
        "performed_by",
        "description",
        "created_at",
    )


@admin.register(AppointmentReminderLog)
class AppointmentReminderLogAdmin(admin.ModelAdmin):
    list_display = (
        "appointment",
        "reminder_type",
        "status",
        "sent_at",
    )

    list_filter = (
        "reminder_type",
        "status",
        "sent_at",
    )

    search_fields = (
        "appointment__reference_code",
        "appointment__customer__full_name",
        "error_message",
    )

    readonly_fields = (
        "appointment",
        "reminder_type",
        "status",
        "error_message",
        "sent_at",
    )


@admin.register(PatientRecord)
class PatientRecordAdmin(admin.ModelAdmin):
    # Dados de saúde: o admin fica atrás da mesma autenticação da área interna,
    # mas a edição habitual faz-se na ficha em /clientes/<id>/anamnese/.

    list_display = (
        "customer",
        "has_diabetes",
        "has_circulatory_issues",
        "has_allergies",
        "updated_at",
    )
    list_filter = (
        "has_diabetes",
        "has_circulatory_issues",
        "has_cardiovascular_issues",
        "has_allergies",
    )
    search_fields = ("customer__full_name", "customer__email", "customer__phone")
    autocomplete_fields = ("customer",)
    readonly_fields = ("created_at", "updated_at", "updated_by")


@admin.register(ClinicalNote)
class ClinicalNoteAdmin(admin.ModelAdmin):
    # Registo clínico por consulta. A edição habitual faz-se em
    # /marcacoes/<id>/nota-clinica/.

    list_display = ("appointment", "created_by", "updated_at")
    search_fields = (
        "appointment__reference_code",
        "appointment__customer__full_name",
        "procedures",
    )
    autocomplete_fields = ("appointment",)
    readonly_fields = ("created_at", "updated_at", "created_by")


@admin.register(PatientRecordLog)
class PatientRecordLogAdmin(admin.ModelAdmin):
    # Histórico de alterações. Só leitura: alterar o histórico esvaziaria a
    # garantia de integridade que ele existe para dar.

    list_display = ("record", "performed_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("record__customer__full_name", "description")
    readonly_fields = ("record", "performed_by", "description", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
