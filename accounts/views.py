from django.utils import timezone
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView
from appointments.mixins import SuperuserRequiredMixin
from appointments.models import Appointment, Customer
from .forms import EmailAuthenticationForm, CustomerSignupForm
from django.views.generic import CreateView
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect

from .services import CustomerSignupService
from datetime import timedelta
from decimal import Decimal
from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce

class UserLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


class UserLogoutView(LogoutView):
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
            result = CustomerSignupService.signup(
                form=form,
                service_id=service_id,
                date_value=date_value,
                start_time_value=start_time_value,
            )

            login(self.request, result.user)

            if result.appointment:
                self.request.session["last_reference_code"] = result.appointment.reference_code
                return redirect("appointments:public_appointment_success")

        except Exception:
            messages.error(
                self.request,
                "Não foi possível concluir a marcação. Escolha outro horário na agenda.",
            )
            return redirect("appointments:public_visual_schedule")

        return redirect("appointments:public_visual_schedule")


class DashboardView(SuperuserRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    def get_percentage(self, part, total):
        if not total:
            return 0

        return round((part / total) * 100, 1)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        month_start = today.replace(day=1)
        next_month_start = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12
            else month_start.replace(month=month_start.month + 1)
        )

        today_appointments = Appointment.objects.filter(date=today)
        month_appointments = Appointment.objects.filter(
            date__gte=month_start,
            date__lt=next_month_start,
        )

        month_total = month_appointments.count()
        month_cancelled = month_appointments.filter(
            status=Appointment.STATUS_CANCELLED
        ).count()

        context["metrics"] = {
            "today_total": today_appointments.count(),
            "today_scheduled": today_appointments.filter(status=Appointment.STATUS_SCHEDULED).count(),
            "today_confirmed": today_appointments.filter(status=Appointment.STATUS_CONFIRMED).count(),
            "today_completed": today_appointments.filter(status=Appointment.STATUS_COMPLETED).count(),
            "today_cancelled": today_appointments.filter(status=Appointment.STATUS_CANCELLED).count(),
            "tomorrow_total": Appointment.objects.filter(date=tomorrow).count(),
            "month_total": month_total,
            "month_completed": month_appointments.filter(status=Appointment.STATUS_COMPLETED).count(),
            "month_cancelled": month_cancelled,
            "month_cancellation_rate": self.get_percentage(month_cancelled, month_total),
            "month_revenue": month_appointments.filter(
                status=Appointment.STATUS_COMPLETED
            ).aggregate(
                total=Coalesce(
                    Sum("service__price"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )["total"],
            "customers_total": Customer.objects.count(),
            "customers_with_email": Customer.objects.exclude(email="").count(),
            "reminders_today_total": 0,
            "reminders_today_success": 0,
            "reminders_today_error": 0,
            "reminders_24h_today": 0,
            "reminders_2h_today": 0,
        }

        return context