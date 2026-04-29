from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView
from appointments.mixins import SuperuserRequiredMixin
from .forms import EmailAuthenticationForm, CustomerSignupForm
from django.views.generic import CreateView
from datetime import datetime
from django.db.models import Sum, Count
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from appointments.appointment_services import AppointmentService
from appointments.models import Appointment, Service, AppointmentReminderLog, ScheduleBlock, Customer    
class UserLoginView(LoginView):
    # Login view using the custom email authentication form

    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


class UserLogoutView(LogoutView):
    # Logout view redirects the user to the login page

    next_page = reverse_lazy("home")

class CustomerSignupView(CreateView):
    form_class = CustomerSignupForm
    template_name = "accounts/customer_signup.html"

    def get_initial(self):
        initial = super().get_initial()

        initial["full_name"] = self.request.GET.get("name", "")
        initial["phone"] = self.request.GET.get("phone", "")
        initial["email"] = self.request.GET.get("email", "")

        return initial

    def form_valid(self, form):
        service_id = self.request.GET.get("service")
        date_value = self.request.GET.get("date")
        start_time_value = self.request.GET.get("start_time")

        try:
            with transaction.atomic():
                self.object = form.save()

                login(self.request, self.object)

                if service_id and date_value and start_time_value:
                    customer = form.customer

                    service = Service.objects.get(
                        pk=service_id,
                        is_active=True,
                    )

                    selected_date = datetime.strptime(
                        date_value,
                        "%Y-%m-%d",
                    ).date()

                    selected_time = datetime.strptime(
                        start_time_value,
                        "%H:%M",
                    ).time()

                    User = get_user_model()

                    system_user = User.objects.filter(
                        is_superuser=True,
                    ).order_by("id").first()

                    if not system_user:
                        raise ValidationError(
                            "Não existe usuário administrador para registrar marcações públicas."
                        )

                    result = AppointmentService.create_public_appointment(
                        customer=customer,
                        service_id=service_id,
                        date_value=date_value,
                        start_time_value=start_time_value,
                        send_email=True,
                    )

                    if not result.success:
                        raise ValidationError(result.message)

                    self.request.session["last_reference_code"] = result.appointment.reference_code

                    return redirect("appointments:public_appointment_success")

        except (Service.DoesNotExist, ValidationError):
            messages.error(
                self.request,
                "Não foi possível concluir a marcação. Escolha outro horário na agenda.",
            )
            return redirect("appointments:public_visual_schedule")

        return redirect("appointments:public_visual_schedule")    
    
class DashboardView(SuperuserRequiredMixin, TemplateView):
    # Internal dashboard with operational, financial and notification metrics.

    template_name = "dashboard.html"

    def get_percentage(self, part, total):
        # Calculate safe percentage values.
        if not total:
            return 0

        return round((part / total) * 100, 1)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()
        tomorrow = today + timezone.timedelta(days=1)
        week_start = today - timezone.timedelta(days=today.weekday())
        week_end = week_start + timezone.timedelta(days=6)
        next_7_days = today + timezone.timedelta(days=7)

        month_start = today.replace(day=1)

        today_appointments = Appointment.objects.filter(
            date=today,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "start_time",
        )

        tomorrow_appointments = Appointment.objects.filter(
            date=tomorrow,
        )

        week_appointments = Appointment.objects.filter(
            date__gte=week_start,
            date__lte=week_end,
        )

        month_appointments = Appointment.objects.filter(
            date__gte=month_start,
            date__lte=today,
        ).select_related(
            "service",
        )

        month_completed = month_appointments.filter(
            status=Appointment.STATUS_COMPLETED,
        )

        month_cancelled_count = month_appointments.filter(
            status=Appointment.STATUS_CANCELLED,
        ).count()

        month_completed_count = month_completed.count()
        month_total = month_appointments.count()

        month_revenue = month_completed.aggregate(
            total=Sum("service__price"),
        )["total"] or 0

        upcoming_appointments = Appointment.objects.filter(
            date__gte=today,
            date__lte=next_7_days,
        ).exclude(
            status=Appointment.STATUS_CANCELLED,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "date",
            "start_time",
        )[:10]

        pending_confirmations = Appointment.objects.filter(
            status=Appointment.STATUS_SCHEDULED,
            date__gte=today,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "date",
            "start_time",
        )[:10]

        recent_cancellations = Appointment.objects.filter(
            status=Appointment.STATUS_CANCELLED,
        ).select_related(
            "customer",
            "service",
        ).order_by(
            "-cancelled_at",
            "-updated_at",
        )[:8]

        top_services = month_completed.values(
            "service__name",
        ).annotate(
            total=Count("id"),
            revenue=Sum("service__price"),
        ).order_by(
            "-total",
            "-revenue",
        )[:5]

        reminder_logs_today = AppointmentReminderLog.objects.filter(
            sent_at__date=today,
        )

        recent_reminder_errors = AppointmentReminderLog.objects.filter(
            status=AppointmentReminderLog.STATUS_ERROR,
        ).select_related(
            "appointment",
            "appointment__customer",
            "appointment__service",
        ).order_by(
            "-sent_at",
        )[:8]

        context["today"] = today
        context["tomorrow"] = tomorrow
        context["week_start"] = week_start
        context["week_end"] = week_end

        context["today_appointments"] = today_appointments
        context["upcoming_appointments"] = upcoming_appointments
        context["pending_confirmations"] = pending_confirmations
        context["recent_cancellations"] = recent_cancellations
        context["top_services"] = top_services
        context["recent_reminder_errors"] = recent_reminder_errors

        context["metrics"] = {
            "today_total": today_appointments.count(),
            "today_confirmed": today_appointments.filter(status=Appointment.STATUS_CONFIRMED).count(),
            "today_scheduled": today_appointments.filter(status=Appointment.STATUS_SCHEDULED).count(),
            "today_completed": today_appointments.filter(status=Appointment.STATUS_COMPLETED).count(),
            "today_cancelled": today_appointments.filter(status=Appointment.STATUS_CANCELLED).count(),

            "tomorrow_total": tomorrow_appointments.count(),

            "week_total": week_appointments.count(),
            "week_confirmed": week_appointments.filter(status=Appointment.STATUS_CONFIRMED).count(),
            "week_completed": week_appointments.filter(status=Appointment.STATUS_COMPLETED).count(),
            "week_cancelled": week_appointments.filter(status=Appointment.STATUS_CANCELLED).count(),

            "month_total": month_total,
            "month_completed": month_completed_count,
            "month_cancelled": month_cancelled_count,
            "month_revenue": month_revenue,
            "month_completion_rate": self.get_percentage(month_completed_count, month_total),
            "month_cancellation_rate": self.get_percentage(month_cancelled_count, month_total),

            "customers_total": Customer.objects.count(),
            "customers_with_email": Customer.objects.exclude(email="").count(),

            "active_services": Service.objects.filter(is_active=True).count(),
            "inactive_services": Service.objects.filter(is_active=False).count(),

            "active_blocks": ScheduleBlock.objects.filter(is_active=True).count(),

            "reminders_today_total": reminder_logs_today.count(),
            "reminders_today_success": reminder_logs_today.filter(status=AppointmentReminderLog.STATUS_SUCCESS).count(),
            "reminders_today_error": reminder_logs_today.filter(status=AppointmentReminderLog.STATUS_ERROR).count(),
            "reminders_24h_today": reminder_logs_today.filter(reminder_type=AppointmentReminderLog.REMINDER_TYPE_24H).count(),
            "reminders_2h_today": reminder_logs_today.filter(reminder_type=AppointmentReminderLog.REMINDER_TYPE_2H).count(),
        }

        return context