from datetime import date
from urllib.parse import quote, urljoin

from django.conf import settings

from config.promotions import get_active_promo_code


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


def promo_settings(request):
    """Expose the current promotional campaign to templates, if still valid."""

    is_active = get_active_promo_code() is not None
    valid_until = None

    if settings.PROMO_ENABLED:
        try:
            valid_until = date.fromisoformat(settings.PROMO_VALID_UNTIL)
        except ValueError:
            pass

    whatsapp_digits = settings.SEO_WHATSAPP_NUMBER.lstrip("+")
    promo_message = quote(
        f"Olá! Vi a promoção de {settings.PROMO_DISCOUNT_PERCENT}% de desconto "
        f"(código {settings.PROMO_CODE}) e gostaria de marcar um horário."
    )

    return {
        "PROMO_ACTIVE": is_active,
        "PROMO_DISCOUNT_PERCENT": settings.PROMO_DISCOUNT_PERCENT,
        "PROMO_CODE": settings.PROMO_CODE,
        "PROMO_VALID_UNTIL": valid_until,
        "PROMO_WHATSAPP_LINK": f"https://wa.me/{whatsapp_digits}?text={promo_message}",
    }


def instagram_settings(request):
    """Expose the Instagram (EmbedSocial) embed to templates, if configured."""

    return {
        "INSTAGRAM_EMBEDSOCIAL_REF": settings.INSTAGRAM_EMBEDSOCIAL_REF,
        "INSTAGRAM_PROFILE_URL": settings.INSTAGRAM_PROFILE_URL,
    }
