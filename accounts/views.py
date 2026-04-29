from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView
from appointments.mixins import SuperuserRequiredMixin
from .forms import EmailAuthenticationForm, CustomerSignupForm
from django.views.generic import CreateView
from datetime import datetime
from django.db.models import Sum
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from appointments.appointment_services import AppointmentService
from appointments.models import Appointment, Service

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
    template_name = "dashboard.html"    

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()

        today_appointments = Appointment.objects.filter(
            date=today,
        ).select_related("customer", "service").order_by("start_time")

        month_appointments = Appointment.objects.filter(
            date__year=today.year,
            date__month=today.month,
        ).select_related("service")

        context["today"] = today
        context["today_appointments"] = today_appointments

        context["metrics"] = {
            "today_total": today_appointments.count(),
            "today_confirmed": today_appointments.filter(status=Appointment.STATUS_CONFIRMED).count(),
            "today_scheduled": today_appointments.filter(status=Appointment.STATUS_SCHEDULED).count(),
            "month_total": month_appointments.count(),
            "month_cancelled": month_appointments.filter(status=Appointment.STATUS_CANCELLED).count(),
            "month_completed": month_appointments.filter(status=Appointment.STATUS_COMPLETED).count(),
            "month_revenue": month_appointments.filter(
                status=Appointment.STATUS_COMPLETED,
            ).aggregate(total=Sum("service__price"))["total"] or 0,
        }

        return context