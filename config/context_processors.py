from urllib.parse import quote, urljoin

from django.conf import settings
from django.urls import translate_url


def _format_pt_phone(phone):
    """Formats a +351XXXXXXXXX number as '+351 XXX XXX XXX' for display."""

    digits = phone.lstrip("+")

    if digits.startswith("351") and len(digits) == 12:
        return f"+351 {digits[3:6]} {digits[6:9]} {digits[9:12]}"

    return phone


def seo_settings(request):
    """Expose site-wide SEO settings to templates."""

    site_url = settings.SITE_URL.rstrip("/")
    current_path = request.path or "/"

    whatsapp_number = settings.SEO_WHATSAPP_NUMBER
    whatsapp_digits = whatsapp_number.lstrip("+")
    whatsapp_message = quote("Olá, gostaria de mais informações.")

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
        "SEO_WHATSAPP_NUMBER": whatsapp_number,
        "SEO_WHATSAPP_DISPLAY": _format_pt_phone(whatsapp_number),
        "SEO_WHATSAPP_LINK": f"https://wa.me/{whatsapp_digits}?text={whatsapp_message}",
    }


def instagram_settings(request):
    """Expose the Instagram profile link to templates."""

    return {
        "INSTAGRAM_PROFILE_URL": settings.INSTAGRAM_PROFILE_URL,
    }


def language_alternates(request):
    """Expose the current page in every language, for hreflang tags.

    translate_url() returns the path unchanged when it cannot be resolved, so
    pages outside i18n_patterns (admin, robots.txt) degrade harmlessly.
    """

    site_url = settings.SITE_URL.rstrip("/")
    current_path = request.get_full_path()

    alternates = []

    for code, name in settings.LANGUAGES:
        translated_path = translate_url(current_path, code)

        alternates.append(
            {
                "code": code,
                "name": name,
                "path": translated_path,
                "url": urljoin(site_url + "/", translated_path.lstrip("/")),
            }
        )

    return {"LANGUAGE_ALTERNATES": alternates}
