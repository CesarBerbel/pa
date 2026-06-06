import json
from urllib.parse import urljoin

from django.conf import settings
from django.urls import reverse


def absolute_url(path: str) -> str:
    return urljoin(settings.SITE_URL.rstrip("/") + "/", path.lstrip("/"))


def build_home_structured_data(service_categories):
    """Build JSON-LD for the public homepage."""

    services = []

    for category in service_categories:
        for service in category.services.all():
            services.append(
                {
                    "@type": "Service",
                    "name": service.name,
                    "description": service.description or f"Serviço de {category.name}",
                    "serviceType": category.name,
                    "provider": {
                        "@type": "HealthAndBeautyBusiness",
                        "name": settings.SEO_SITE_NAME,
                    },
                    "offers": {
                        "@type": "Offer",
                        "price": str(service.price),
                        "priceCurrency": "EUR",
                        "availability": "https://schema.org/InStock",
                        "url": absolute_url(
                            reverse("appointments:public_visual_schedule")
                        ),
                    },
                }
            )

    payload = {
        "@context": "https://schema.org",
        "@type": "HealthAndBeautyBusiness",
        "name": settings.SEO_SITE_NAME,
        "url": settings.SITE_URL.rstrip("/"),
        "image": absolute_url(settings.SEO_DEFAULT_IMAGE_PATH),
        "description": settings.SEO_DEFAULT_DESCRIPTION,
        "telephone": settings.SEO_BUSINESS_PHONE,
        "email": settings.SEO_BUSINESS_EMAIL,
        "priceRange": "€€",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": settings.SEO_BUSINESS_STREET_ADDRESS,
            "addressLocality": settings.SEO_BUSINESS_LOCALITY,
            "postalCode": settings.SEO_BUSINESS_POSTAL_CODE,
            "addressCountry": settings.SEO_BUSINESS_COUNTRY,
        },
        "areaServed": settings.SEO_BUSINESS_AREA_SERVED,
        "openingHoursSpecification": [
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ],
                "opens": settings.SEO_BUSINESS_OPENS_AT,
                "closes": settings.SEO_BUSINESS_CLOSES_AT,
            }
        ],
        "makesOffer": services,
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_service_feed_structured_data(service_categories):
    """Build JSON-LD ItemList for the public services feed."""

    items = []
    position = 1

    for category in service_categories:
        for service in category.services.all():
            items.append(
                {
                    "@type": "ListItem",
                    "position": position,
                    "item": {
                        "@type": "Service",
                        "name": service.name,
                        "description": service.description
                        or f"Serviço de {category.name}",
                        "serviceType": category.name,
                        "provider": {
                            "@type": "HealthAndBeautyBusiness",
                            "name": settings.SEO_SITE_NAME,
                            "url": settings.SITE_URL.rstrip("/"),
                        },
                        "offers": {
                            "@type": "Offer",
                            "price": str(service.price),
                            "priceCurrency": "EUR",
                            "url": absolute_url(
                                reverse("appointments:public_visual_schedule")
                            ),
                        },
                    },
                }
            )
            position += 1

    payload = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Serviços disponíveis",
        "description": "Serviços de podologia, manicure, pedicure e enfermagem disponíveis para marcação online.",
        "itemListElement": items,
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)
