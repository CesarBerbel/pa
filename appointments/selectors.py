from __future__ import annotations

from dataclasses import dataclass

from django.db import models

from appointments.availability import AvailabilityService
from appointments.models import Appointment, ScheduleBlock


@dataclass(frozen=True)
class AppointmentFilters:
    q: str = ""
    status: str = ""
    service: str = ""
    date_from: str = ""
    date_to: str = ""
    reminder: str = ""
    ordering: str = "date_asc"

    @classmethod
    def from_querydict(cls, querydict):
        return cls(
            q=querydict.get("q", "").strip(),
            status=querydict.get("status", "").strip(),
            service=querydict.get("service", "").strip(),
            date_from=querydict.get("date_from", "").strip(),
            date_to=querydict.get("date_to", "").strip(),
            reminder=querydict.get("reminder", "").strip(),
            ordering=querydict.get("ordering", "date_asc").strip() or "date_asc",
        )

    def as_template_context(self):
        return {
            "q": self.q,
            "status": self.status,
            "service": self.service,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "reminder": self.reminder,
            "ordering": self.ordering,
        }


class AppointmentSelectors:
    allowed_orderings = {
        "date_asc": ("date", "start_time"),
        "date_desc": ("-date", "-start_time"),
        "customer_asc": ("customer__full_name", "date", "start_time"),
        "customer_desc": ("-customer__full_name", "date", "start_time"),
        "service_asc": ("service__name", "date", "start_time"),
        "service_desc": ("-service__name", "date", "start_time"),
        "status_asc": ("status", "date", "start_time"),
        "status_desc": ("-status", "date", "start_time"),
        "created_desc": ("-created_at",),
        "created_asc": ("created_at",),
    }

    @classmethod
    def list_appointments(cls, filters: AppointmentFilters):
        queryset = Appointment.objects.select_related(
            "customer",
            "service",
            "created_by",
        )

        if filters.q:
            queryset = queryset.filter(
                models.Q(reference_code__icontains=filters.q)
                | models.Q(customer__full_name__icontains=filters.q)
                | models.Q(customer__email__icontains=filters.q)
                | models.Q(customer__phone__icontains=filters.q)
                | models.Q(service__name__icontains=filters.q)
            )

        if filters.status:
            queryset = queryset.filter(status=filters.status)

        if filters.service:
            queryset = queryset.filter(service_id=filters.service)

        if filters.date_from:
            queryset = queryset.filter(date__gte=filters.date_from)

        if filters.date_to:
            queryset = queryset.filter(date__lte=filters.date_to)

        if filters.reminder == "24h_sent":
            queryset = queryset.filter(reminder_24h_sent_at__isnull=False)
        elif filters.reminder == "24h_pending":
            queryset = queryset.filter(
                reminder_24h_sent_at__isnull=True,
            ).exclude(status__in=[Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED])
        elif filters.reminder == "2h_sent":
            queryset = queryset.filter(reminder_2h_sent_at__isnull=False)
        elif filters.reminder == "2h_pending":
            queryset = queryset.filter(
                reminder_2h_sent_at__isnull=True,
            ).exclude(status__in=[Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED])

        return queryset.order_by(*cls.allowed_orderings.get(filters.ordering, cls.allowed_orderings["date_asc"]))

    @staticmethod
    def customer_appointments(customer):
        if not customer:
            return []

        return Appointment.objects.filter(
            customer=customer,
        ).select_related(
            "service",
        ).order_by("-date", "-start_time")

    @staticmethod
    def customer_appointment_by_reference(customer, reference_code):
        if not customer:
            return None

        return Appointment.objects.filter(
            customer=customer,
            reference_code=reference_code.strip().upper(),
        ).select_related(
            "service",
            "customer",
        ).first()

    @staticmethod
    def appointments_for_date(selected_date, include_cancelled=True):
        queryset = Appointment.objects.filter(
            date=selected_date,
        ).select_related(
            "customer",
            "service",
        ).order_by("start_time")

        if not include_cancelled:
            queryset = queryset.exclude(status=Appointment.STATUS_CANCELLED)

        return queryset

    @staticmethod
    def blocks_for_date(selected_date):
        return AvailabilityService.get_active_blocks_for_date(selected_date)
