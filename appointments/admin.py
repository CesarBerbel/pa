from django.contrib import admin

from .models import (
    Appointment,
    AppointmentLog,
    AppointmentReminderLog,
    BusinessHour,
    Customer,
    ScheduleBlock,
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
    )
    list_display_links = ("name",)
    list_editable = (
        "display_order",
        "is_active",
        "is_coming_soon",
    )
    list_filter = ("is_active", "is_coming_soon")
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
        (None, {"fields": ("display_order", "is_active", "is_coming_soon")}),
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
        "reminder_24h_sent_at",
        "reminder_2h_sent_at",
        "cancelled_at",
    )

    list_filter = (
        "status",
        "date",
        "service__category",
        "service",
        "reminder_24h_sent_at",
        "reminder_2h_sent_at",
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
            "Lembretes",
            {
                "fields": (
                    "reminder_24h_sent_at",
                    "reminder_2h_sent_at",
                )
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
        "title",
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

    search_fields = ("title",)


@admin.register(BusinessHour)
class BusinessHourAdmin(admin.ModelAdmin):
    list_display = (
        "weekday",
        "start_time",
        "end_time",
        "is_active",
    )
    list_editable = (
        "start_time",
        "end_time",
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
