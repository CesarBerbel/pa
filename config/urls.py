from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import include, path
from django.views.generic import TemplateView


def home_view(request):
    # Show public homepage for anonymous users and dashboard for authenticated users
    if request.user.is_authenticated:
        return redirect("dashboard")

    return render(request, "home.html")


urlpatterns = [
    path("admin/", admin.site.urls),

    path("", home_view, name="home"),

    path("", include("accounts.urls")),
    path("", include("appointments.urls")),

    path(
        "dashboard/",
        login_required(
            TemplateView.as_view(template_name="dashboard.html")
        ),
        name="dashboard",
    ),
]