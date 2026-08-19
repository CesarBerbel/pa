from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.urls import include, path

from accounts.views import DashboardView
from appointments.homepage import build_home_service_cards
from appointments.models import Service, ServiceCategory
from config.seo import build_home_structured_data
from config.views import (
    complaints_book,
    cookie_policy,
    manifest_webmanifest,
    offline,
    privacy_policy,
    robots_txt,
    service_worker,
    sitemap_xml,
)
from notifications.models import InstagramPost


def home_view(request):
    # Show public homepage for anonymous users and dashboard for authenticated users.
    if request.user.is_authenticated and request.user.has_internal_access:
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
            "service_cards": build_home_service_cards(service_categories),
            "home_structured_data": build_home_structured_data(service_categories),
            "instagram_posts": InstagramPost.objects.filter(is_active=True),
        },
    )


# Fora do i18n_patterns: ficheiros lidos por crawlers e o admin do Django, que
# não devem ganhar prefixo de idioma. "i18n/" expõe a view set_language usada
# pelo seletor de idioma.
urlpatterns = [
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap_xml"),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    # Manifesto e service worker vivem na raiz: o âmbito de um service
    # worker é a pasta onde é servido, e a partir de /static/ não cobriria
    # o site todo.
    path("manifest.webmanifest", manifest_webmanifest, name="manifest"),
    path("sw.js", service_worker, name="service_worker"),
]

# prefix_default_language=False mantém o português na raiz (priarantes.com/) e
# coloca o inglês sob /en/. Nenhum URL existente muda.
urlpatterns += i18n_patterns(
    path("politica-de-privacidade/", privacy_policy, name="privacy_policy"),
    path("politica-de-cookies/", cookie_policy, name="cookie_policy"),
    path("livro-de-reclamacoes/", complaints_book, name="complaints_book"),
    path("offline/", offline, name="offline"),
    path("", home_view, name="home"),
    path("", include("accounts.urls")),
    path("", include("appointments.urls")),
    path("", include("notifications.urls")),
    path(
        "dashboard/",
        DashboardView.as_view(),
        name="dashboard",
    ),
    prefix_default_language=False,
)

if settings.DEBUG:
    # Em produção, o servidor web (nginx/whitenoise) é quem deve servir MEDIA_ROOT.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
