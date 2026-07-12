from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.urls import include, path

from accounts.views import DashboardView
from appointments.models import Service, ServiceCategory
from config.seo import build_home_structured_data
from config.views import cookie_policy, privacy_policy, robots_txt, sitemap_xml
from notifications.models import InstagramPost


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
            "home_structured_data": build_home_structured_data(service_categories),
            "instagram_posts": InstagramPost.objects.filter(is_active=True),
        },
    )


urlpatterns = [
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap_xml"),
    path("politica-de-privacidade/", privacy_policy, name="privacy_policy"),
    path("politica-de-cookies/", cookie_policy, name="cookie_policy"),
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

if settings.DEBUG:
    # Em produção, o servidor web (nginx/whitenoise) é quem deve servir MEDIA_ROOT.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
