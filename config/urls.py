from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import include, path


from accounts.views import DashboardView


def home_view(request):
    # Show public homepage for anonymous users and dashboard for authenticated users
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("dashboard")

    return render(request, "home.html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home_view, name="home"),
    path("", include("accounts.urls")),
    path("", include("appointments.urls")),
    path(
        "dashboard/",
        DashboardView.as_view(),
        name="dashboard",
    ),
]
