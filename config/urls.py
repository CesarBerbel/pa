from django.conf import settings
from django.contrib import admin
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.urls import include, path

from accounts.views import DashboardView
from appointments.models import Service, ServiceCategory


def home_view(request):
    # Show public homepage for anonymous users and dashboard for authenticated users.
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("dashboard")

    service_categories = (
        ServiceCategory.objects.filter(
            is_active=True,
            services__is_active=True,
        )
        .prefetch_related(
            Prefetch(
                "services",
                queryset=Service.objects.filter(is_active=True).order_by("name"),
            )
        )
        .distinct()
        .order_by("display_order", "name")
    )

    return render(
        request,
        "home.html",
        {
            "home_hero_layout": settings.HOME_HERO_LAYOUT,
            "service_categories": service_categories,
        },
    )


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
