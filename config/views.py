from html import escape

from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET


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
