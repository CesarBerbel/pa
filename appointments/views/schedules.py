from datetime import datetime, timedelta

from appointments.mixins import SuperuserRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from appointments.availability import AvailabilityService
from appointments.selectors import AppointmentSelectors


class DailyAgendaView(SuperuserRequiredMixin, TemplateView):
    # Shows appointments grouped by a selected day

    template_name = "appointments/daily_agenda.html"

    def get_selected_date(self):
        date_param = self.request.GET.get("date")

        if date_param:
            try:
                return timezone.datetime.strptime(date_param, "%Y-%m-%d").date()
            except ValueError:
                return timezone.localdate()

        return timezone.localdate()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_date = self.get_selected_date()

        context["selected_date"] = selected_date
        context["previous_date"] = selected_date - timedelta(days=1)
        context["next_date"] = selected_date + timedelta(days=1)
        context["appointments"] = AppointmentSelectors.appointments_for_date(
            selected_date
        )
        context["blocks"] = AppointmentSelectors.blocks_for_date(selected_date)

        return context


class VisualScheduleView(SuperuserRequiredMixin, TemplateView):
    # Shows a visual daily schedule with appointments and blocked periods

    template_name = "appointments/visual_schedule.html"
    slot_minutes = 30

    def get_selected_date(self):
        date_param = self.request.GET.get("date")

        if date_param:
            try:
                return datetime.strptime(date_param, "%Y-%m-%d").date()
            except ValueError:
                return timezone.localdate()

        return timezone.localdate()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_date = self.get_selected_date()
        business_hour, slots = AvailabilityService.build_visual_slots(
            selected_date=selected_date,
            slot_minutes=self.slot_minutes,
        )

        context["selected_date"] = selected_date
        context["previous_date"] = selected_date - timedelta(days=1)
        context["next_date"] = selected_date + timedelta(days=1)
        context["business_hour"] = business_hour
        context["slots"] = slots

        return context
