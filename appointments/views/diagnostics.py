from datetime import datetime, timedelta

from appointments.mixins import SuperuserRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from appointments.models import Appointment, BusinessHour, ScheduleBlock, Service


class ScheduleDiagnosticsView(SuperuserRequiredMixin, TemplateView):
    # Shows detailed diagnostics for available and blocked schedule slots

    template_name = "appointments/schedule_diagnostics.html"

    slot_minutes = 30

    def get_selected_service(self):
        # Get selected service from query string
        service_id = self.request.GET.get("service")

        if not service_id:
            return None

        return Service.objects.filter(pk=service_id).first()

    def get_selected_date(self):
        # Get selected date from query string or use today
        date_value = self.request.GET.get("date")

        if not date_value:
            return timezone.localdate()

        try:
            return datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return timezone.localdate()

    def build_diagnostics(self, service, selected_date):
        # Build detailed schedule diagnostics
        if not service:
            return []

        business_hour = BusinessHour.objects.filter(
            weekday=selected_date.weekday(),
            is_active=True,
        ).first()

        if not business_hour:
            return []

        current_datetime = datetime.combine(
            selected_date,
            business_hour.start_time,
        )

        business_end_datetime = datetime.combine(
            selected_date,
            business_hour.end_time,
        )

        now = timezone.localtime()

        appointments = Appointment.objects.filter(
            date=selected_date,
        ).exclude(
            status=Appointment.STATUS_CANCELLED,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "start_time",
        )

        blocks = [
            block
            for block in ScheduleBlock.objects.filter(is_active=True).order_by("start_time")
            if block.applies_to_date(selected_date)
        ]

        diagnostics = []

        while current_datetime < business_end_datetime:
            slot_start = current_datetime
            slot_end = slot_start + timedelta(minutes=service.duration_minutes)

            status = "available"
            reason = "Horário disponível"
            related_object = None

            if slot_end > business_end_datetime:
                status = "blocked"
                reason = "O serviço termina depois do horário de funcionamento."

            elif selected_date == now.date() and slot_start < now.replace(tzinfo=None):
                status = "blocked"
                reason = "Horário já passou."

            else:
                for block in blocks:
                    block_start = block.get_start_datetime_for_date(selected_date)
                    block_end = block.get_end_datetime_for_date(selected_date)

                    if slot_start < block_end and slot_end > block_start:
                        status = "blocked"
                        reason = f"Conflito com bloqueio: {block.title}"
                        related_object = block
                        break

                if status == "available":
                    for appointment in appointments:
                        appointment_start = appointment.get_start_datetime()
                        appointment_end = appointment.get_end_datetime()

                        if slot_start < appointment_end and slot_end > appointment_start:
                            status = "blocked"
                            reason = (
                                f"Conflito com marcação: "
                                f"{appointment.reference_code} - "
                                f"{appointment.customer.full_name}"
                            )
                            related_object = appointment
                            break

            diagnostics.append(
                {
                    "start_time": slot_start.time(),
                    "end_time": slot_end.time(),
                    "status": status,
                    "reason": reason,
                    "related_object": related_object,
                }
            )

            current_datetime += timedelta(minutes=self.slot_minutes)

        return diagnostics

    def get_context_data(self, **kwargs):
        # Add diagnostics data to template context
        context = super().get_context_data(**kwargs)

        selected_service = self.get_selected_service()
        selected_date = self.get_selected_date()

        business_hour = BusinessHour.objects.filter(
            weekday=selected_date.weekday(),
            is_active=True,
        ).first()

        appointments = Appointment.objects.filter(
            date=selected_date,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "start_time",
        )

        blocks = [
            block
            for block in ScheduleBlock.objects.filter(is_active=True).order_by("start_time")
            if block.applies_to_date(selected_date)
        ]

        diagnostics = self.build_diagnostics(
            selected_service,
            selected_date,
        )

        context["services"] = Service.objects.order_by("name")
        context["selected_service"] = selected_service
        context["selected_date"] = selected_date
        context["business_hour"] = business_hour
        context["appointments"] = appointments
        context["blocks"] = blocks
        context["diagnostics"] = diagnostics

        return context


class ReminderDiagnosticsView(SuperuserRequiredMixin, TemplateView):
    # Shows diagnostics for appointment reminders without changing database data

    template_name = "appointments/reminder_diagnostics.html"

    def get_selected_date(self):
        # Get selected date from query string or use tomorrow as default
        date_value = self.request.GET.get("date")

        if not date_value:
            return timezone.localdate() + timedelta(days=1)

        try:
            return datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return timezone.localdate() + timedelta(days=1)

    def build_reminder_diagnostics(self, selected_date):
        # Build reminder diagnostics based on appointment status and customer contact data
        appointments = Appointment.objects.filter(
            date=selected_date,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "start_time",
        )

        diagnostics = []

        for appointment in appointments:
            status = "ready"
            reason = "Lembrete pode ser enviado."
            can_send = True

            if appointment.status == Appointment.STATUS_CANCELLED:
                status = "blocked"
                reason = "A marcação está cancelada."
                can_send = False

            elif appointment.status == Appointment.STATUS_COMPLETED:
                status = "blocked"
                reason = "A marcação já está concluída."
                can_send = False

            elif not appointment.customer.email:
                status = "warning"
                reason = "Cliente não tem email cadastrado."
                can_send = False

            elif selected_date < timezone.localdate():
                status = "blocked"
                reason = "A data da marcação já passou."
                can_send = False

            diagnostics.append(
                {
                    "appointment": appointment,
                    "status": status,
                    "reason": reason,
                    "can_send": can_send,
                }
            )

        return diagnostics

    def get_context_data(self, **kwargs):
        # Add reminder diagnostics to template context
        context = super().get_context_data(**kwargs)

        selected_date = self.get_selected_date()
        diagnostics = self.build_reminder_diagnostics(selected_date)

        context["selected_date"] = selected_date
        context["previous_date"] = selected_date - timedelta(days=1)
        context["next_date"] = selected_date + timedelta(days=1)
        context["diagnostics"] = diagnostics

        context["total_count"] = len(diagnostics)
        context["ready_count"] = len(
            [item for item in diagnostics if item["status"] == "ready"]
        )
        context["warning_count"] = len(
            [item for item in diagnostics if item["status"] == "warning"]
        )
        context["blocked_count"] = len(
            [item for item in diagnostics if item["status"] == "blocked"]
        )

        return context