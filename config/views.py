from html import escape

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from config.templatetags.assets import asset_version, versioned_static


@require_GET
def robots_txt(request):
    """Return robots.txt dynamically using SITE_URL from settings."""

    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /dashboard/",
        "Disallow: /diagnostico/",
        "Disallow: /clientes/",
        "Disallow: /marcacoes/",
        "Disallow: /bloqueios/",
        "Disallow: /horas-trabalhadas/",
        "Disallow: /minhas-marcacoes/",
        "Allow: /",
        "",
        f"Sitemap: {settings.SITE_URL.rstrip('/')}/sitemap.xml",
        "",
    ]

    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
def sitemap_xml(request):
    """Return a small XML sitemap using the canonical SITE_URL."""

    site_url = settings.SITE_URL.rstrip("/")
    today = timezone.localdate().isoformat()
    sitemap_items = [
        {
            "loc": f"{site_url}{reverse('home')}",
            "lastmod": today,
            "changefreq": "weekly",
            "priority": "1.0",
        },
        {
            "loc": f"{site_url}{reverse('appointments:public_service_feed')}",
            "lastmod": today,
            "changefreq": "weekly",
            "priority": "0.9",
        },
        {
            "loc": f"{site_url}{reverse('appointments:public_visual_schedule')}",
            "lastmod": today,
            "changefreq": "daily",
            "priority": "0.8",
        },
        {
            "loc": f"{site_url}{reverse('privacy_policy')}",
            "lastmod": today,
            "changefreq": "monthly",
            "priority": "0.4",
        },
        {
            "loc": f"{site_url}{reverse('cookie_policy')}",
            "lastmod": today,
            "changefreq": "monthly",
            "priority": "0.4",
        },
        {
            "loc": f"{site_url}{reverse('complaints_book')}",
            "lastmod": today,
            "changefreq": "yearly",
            "priority": "0.3",
        },
    ]

    url_entries = []

    for item in sitemap_items:
        url_entries.append(
            "\n".join(
                [
                    "    <url>",
                    f"        <loc>{escape(item['loc'])}</loc>",
                    f"        <lastmod>{item['lastmod']}</lastmod>",
                    f"        <changefreq>{item['changefreq']}</changefreq>",
                    f"        <priority>{item['priority']}</priority>",
                    "    </url>",
                ]
            )
        )

    xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *url_entries,
            "</urlset>",
            "",
        ]
    )

    return HttpResponse(xml, content_type="application/xml; charset=utf-8")


@require_GET
def privacy_policy(request):
    """Render the public privacy policy page."""

    return render(request, "legal/privacy_policy.html")


@require_GET
def cookie_policy(request):
    """Render the public cookie policy page."""

    return render(request, "legal/cookie_policy.html")


@require_GET
def complaints_book(request):
    """Render the public complaints book page.

    A reclamação em si é feita no portal oficial; esta página só explica as
    vias disponíveis e encaminha para lá.
    """

    return render(
        request,
        "legal/complaints_book.html",
        {"complaints_book_url": settings.COMPLAINTS_BOOK_URL},
    )


@require_GET
def manifest_webmanifest(request):
    """Manifesto da aplicação, servido na raiz.

    É gerado a partir das definições para o nome e a cor acompanharem o resto
    do site sem duplicação.
    """

    manifest = {
        "name": settings.SEO_SITE_NAME,
        "short_name": "Priscila Arantes",
        "description": settings.SEO_DEFAULT_DESCRIPTION,
        "lang": settings.LANGUAGE_CODE,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#FFF7F9",
        "theme_color": settings.SEO_THEME_COLOR,
        "icons": [
            {
                "src": static("img/icon-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": static("img/icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                # O Android recorta o ícone; este tem margem para o logo não
                # sair cortado.
                "src": static("img/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
        "shortcuts": [
            {
                "name": "Marcar horário",
                "url": reverse("appointments:public_visual_schedule"),
            },
            {
                "name": "Consultar marcação",
                "url": reverse("appointments:public_appointment_lookup"),
            },
        ],
    }

    return JsonResponse(manifest, content_type="application/manifest+json")


@require_GET
def service_worker(request):
    """Service worker servido na raiz, para o âmbito cobrir o site inteiro.

    Deliberadamente **não** guarda páginas em cache. Numa agenda, uma página
    guardada mostraria horários que entretanto já foram ocupados, e alguém
    tentaria marcar um horário que já não existe. Só os ficheiros estáticos são
    guardados; sem rede, aparece a página offline.
    """

    conteudo = render_to_string(
        "pwa/service_worker.js",
        {
            "cache_version": _service_worker_version(),
            "offline_url": reverse("offline"),
            # Os URLs têm de ser exatamente os que as páginas pedem, senão o
            # que fica guardado nunca chega a ser usado.
            "precache_urls": [
                versioned_static("css/public.css"),
                static("img/icon-192.png"),
                # O logótipo compacto: é o que a barra mostra no telemóvel,
                # que é onde a página offline aparece.
                static("img/logo-mark.png"),
            ],
        },
    )

    response = HttpResponse(conteudo, content_type="application/javascript")

    # Sem isto, um browser com o service worker antigo em cache podia demorar a
    # aceitar uma versão nova.
    response["Cache-Control"] = "no-cache"

    return response


def _service_worker_version():
    # A versão muda quando o CSS muda, o que faz o browser descartar a cache
    # antiga em vez de servir estilos desatualizados.
    return asset_version("css/public.css")


@require_GET
def offline(request):
    """Página mostrada quando não há rede."""

    return render(request, "pwa/offline.html")
