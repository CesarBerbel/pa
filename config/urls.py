from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.urls import include, path, re_path

from accounts.views import DashboardView
from appointments.models import SchedulingSetting, Service, ServiceCategory
from config.google_reviews import get_reviews
from config.seo import build_home_structured_data
from config.views import (
    complaints_book,
    cookie_policy,
    manifest_webmanifest,
    media_file,
    offline,
    privacy_policy,
    robots_txt,
    service_worker,
    sitemap_xml,
)


def home_view(request):
    # Show public homepage for anonymous users and dashboard for authenticated users.
    if request.user.is_authenticated and request.user.has_internal_access:
        return redirect("dashboard")

    service_categories = (
        ServiceCategory.objects.filter(
            is_active=True,
            services__is_active=True,
            # A página inicial mostra o que posiciona a casa; a lista
            # completa vive na página de serviços.
            show_on_homepage=True,
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
            "google_reviews": get_reviews(),
            # As perguntas frequentes dizem o prazo de cancelamento. Escrito à
            # mão ficaria a mentir assim que a profissional o mudasse nas
            # regras de agenda.
            # O cartão "Feridas e pensos" depende da enfermagem: o penso
            # especializado só se marca quando a categoria abrir. Ler o estado
            # dela aqui faz as duas coisas andarem juntas sozinhas, em vez de
            # dependerem de alguém se lembrar de mexer nas duas.
            "nursing_coming_soon": ServiceCategory.objects.filter(
                slug="enfermagem", is_coming_soon=True
            ).exists(),
            "cancellation_min_advance_hours": (
                SchedulingSetting.get_cancellation_min_advance_hours()
            ),
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
    # Sob um prefixo próprio: é uma área da casa e não mais um ecrã da
    # agenda, e um endereço que o diz poupa explicações.
    path("financeiro/", include("finance.urls")),
    path(
        "dashboard/",
        DashboardView.as_view(),
        name="dashboard",
    ),
    prefix_default_language=False,
)

# Ficheiros carregados (as fotografias do antes e depois). O `static()` acima
# só funciona com `DEBUG=True` — devolve uma lista vazia em produção — e o
# comentário que aqui estava dizia que o servidor web trataria disto. Não
# trata: o Caddy encaminha tudo para o Django e o WhiteNoise serve apenas o
# `STATIC_ROOT`, que é outra pasta. Sem esta rota as fotografias dão 404
# assim que o site sai de desenvolvimento.
#
# Quem serve é o `django.views.static.serve`, que a documentação desaconselha
# em produção por ser mais lento do que um servidor de ficheiros dedicado.
# Aqui são poucas imagens numa página que quase ninguém abre ao mesmo tempo,
# e a alternativa — montar a pasta no Caddy — obriga a mexer na configuração
# do servidor a cada deploy. Se um dia forem muitas, `docs/deploy.md` explica
# como passar isto para o Caddy.
urlpatterns += [
    re_path(
        r"^%s(?P<path>.*)$" % settings.MEDIA_URL.lstrip("/"),
        media_file,
    ),
]
