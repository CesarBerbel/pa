from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView
from appointments.mixins import SuperuserRequiredMixin
from .forms import EmailAuthenticationForm, CustomerSignupForm
from django.views.generic import CreateView
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect

from .services import CustomerSignupService


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
