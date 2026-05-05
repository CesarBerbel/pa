from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    # Allow only authenticated superusers to access internal system pages.

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser

    def handle_no_permission(self):
        return redirect("home")
