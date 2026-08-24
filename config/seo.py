import json
from urllib.parse import urljoin

from django.conf import settings
from django.urls import reverse


def absolute_url(path: str) -> str:
    return urljoin(settings.SITE_URL.rstrip("/") + "/", path.lstrip("/"))


def opening_hours_specification():
    """O horário para o Google, tirado do que a profissional configurou.

    Enquanto não houver nenhum dia configurado, valem as definições — uma
    ficha sem horário nenhum é pior do que uma com um horário genérico.
    """

    from appointments.opening_hours import structured_data_specification

    configurado = structured_data_specification()

    if configurado:
        return configurado

    return [
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
    ]

def build_home_structured_data(service_categories):
    """Build JSON-LD for the public homepage."""

    services = []

    for category in service_categories:
        for service in category.services.all():
            services.append(
                {
                    "@type": "Service",
                    "name": service.display_name,
                    "description": (
                        service.display_description
                        or f"Serviço de {category.display_name}"
                    ),
                    "serviceType": category.display_name,
                    "provider": {
                        "@type": "HealthAndBeautyBusiness",
                        "name": settings.SEO_SITE_NAME,
                    },
                }
            )

    payload = {
        "@context": "https://schema.org",
        # `medicalSpecialty: Podiatric` esteve aqui e saiu: em Portugal
        # podologia é um título com formação própria, e declará-lo ao Google
        # seria afirmar uma qualificação que não é a desta casa. O que fica
        # descreve o que se faz, não um título que não se tem.
        "@type": "HealthAndBeautyBusiness",
        "knowsAbout": [
            "Pedicure terapêutica",
            "Saúde do pé",
            "Unha encravada",
            "Onicomicose",
            "Calosidades",
            "Risco podológico",
            "Verruga plantar",
            "Órtese ungueal",
            "Cuidados de enfermagem",
        ],
        "name": settings.SEO_SITE_NAME,
        "url": settings.SITE_URL.rstrip("/"),
        "image": absolute_url(settings.SEO_DEFAULT_IMAGE_PATH),
        "description": settings.SEO_DEFAULT_DESCRIPTION,
        "telephone": settings.SEO_WHATSAPP_NUMBER,
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
        "openingHoursSpecification": opening_hours_specification(),
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
                        "url": absolute_url(
                            reverse("appointments:public_visual_schedule")
                        ),
                    },
                }
            )
            position += 1

    payload = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Serviços disponíveis",
        "description": "Serviços de pedicure terapêutica, manicure e enfermagem disponíveis para marcação online.",
        "itemListElement": items,
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)
