from datetime import date

from django.conf import settings


def get_active_promo_code():
    """Return the current promo code, or None if no promotion is active."""

    if not settings.PROMO_ENABLED:
        return None

    try:
        valid_until = date.fromisoformat(settings.PROMO_VALID_UNTIL)
    except ValueError:
        return None

    if date.today() > valid_until:
        return None

    return settings.PROMO_CODE
