from django import forms

from django.contrib import admin

from .models import (
    Appointment,
    AppointmentLog,
    Customer,
    Service,
    ScheduleBlock,
    BusinessHour,
)

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "duration_minutes", "price", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


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
        "reminder_sent_at",
    )

    list_filter = (
        "status",
        "date",
        "service",
        "cancelled_at",
    )

    search_fields = (
        "reference_code",
        "customer__full_name",
        "customer__email",
        "cancellation_reason",
    )

    readonly_fields = (
        "reference_code",
        "cancelled_at",
        "created_at",
        "updated_at",
        "reminder_sent_at",
        "reminder_24h_sent_at",
        "reminder_2h_sent_at",
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
                    "reminder_24h_sent_at",
                    "reminder_2h_sent_at",
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
        "is_active",
    )

    list_filter = ("is_active", "is_full_day", "block_type")

    search_fields = ("title",)


@admin.register(BusinessHour)
class BusinessHourAdmin(admin.ModelAdmin):
    list_display = ("weekday", "start_time", "end_time", "is_active")
    list_editable = ("start_time", "end_time", "is_active")            

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