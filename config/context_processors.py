from urllib.parse import urljoin

from django.conf import settings


def seo_settings(request):
    """Expose site-wide SEO settings to templates."""

    site_url = settings.SITE_URL.rstrip("/")
    current_path = request.path or "/"

    return {
        "SEO_SITE_URL": site_url,
        "SEO_SITE_NAME": settings.SEO_SITE_NAME,
        "SEO_DEFAULT_TITLE": settings.SEO_DEFAULT_TITLE,
        "SEO_DEFAULT_DESCRIPTION": settings.SEO_DEFAULT_DESCRIPTION,
        "SEO_DEFAULT_KEYWORDS": settings.SEO_DEFAULT_KEYWORDS,
        "SEO_DEFAULT_IMAGE_URL": urljoin(
            site_url + "/", settings.SEO_DEFAULT_IMAGE_PATH.lstrip("/")
        ),
        "SEO_CURRENT_URL": urljoin(site_url + "/", current_path.lstrip("/")),
        "SEO_LOCALE": settings.SEO_LOCALE,
        "SEO_THEME_COLOR": settings.SEO_THEME_COLOR,
        "SEO_ROBOTS_DEFAULT": settings.SEO_ROBOTS_DEFAULT,
    }
