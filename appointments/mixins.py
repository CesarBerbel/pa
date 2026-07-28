from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    # Allow only authenticated superusers to access internal system pages.

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser

    def handle_no_permission(self):
        return redirect("home")

    def get_permission_denied_response(self):
        # Views that need to inspect the object inside dispatch() must run the
        # access check first. Otherwise they load the object and can return an
        # object-dependent redirect before authorization has been validated.
        if self.test_func():
            return None

        return self.handle_no_permission()
