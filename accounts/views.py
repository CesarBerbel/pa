from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView
from appointments.mixins import SuperuserRequiredMixin
from .forms import EmailAuthenticationForm, CustomerSignupForm
from django.views.generic import CreateView


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
    success_url = reverse_lazy("appointments:public_visual_schedule")

    def form_valid(self, form):
        response = super().form_valid(form)

        login(self.request, self.object)

        return response    
    
class DashboardView(SuperuserRequiredMixin, TemplateView):
    template_name = "dashboard.html"    