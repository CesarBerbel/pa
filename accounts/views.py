from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy

from .forms import EmailAuthenticationForm


class UserLoginView(LoginView):
    # Login view using the custom email authentication form

    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


class UserLogoutView(LogoutView):
    # Logout view redirects the user to the login page

    next_page = reverse_lazy("home")