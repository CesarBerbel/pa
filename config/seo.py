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


def google_business_profile():
    """A ficha do Google, ligada ao site — se houver uma configurada.

    O site já se descrevia ao Google com nome, morada, telefone e horário, mas
    não dizia *qual* é a ficha dele. São duas coisas que o Google pode tratar
    como não sendo a mesma casa, e é o que faz um negócio aparecer com uma
    ficha sem site e um site sem ficha.

    `sameAs` é a afirmação de identidade e `hasMap` é o sítio no mapa. Vão os
    dois com o mesmo endereço porque é o mesmo endereço: o link de partilha do
    Perfil de Empresa serve para ambos.

    Sem nada configurado devolve um dicionário vazio, e o JSON-LD sai como
    saía. Um `sameAs` a apontar para lado nenhum é pior do que não o ter.
    """

    endereco = (settings.SEO_GOOGLE_BUSINESS_URL or "").strip()

    if not endereco:
        return {}

    return {"sameAs": [endereco], "hasMap": endereco}


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

    payload.update(google_business_profile())

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


def build_condition_structured_data(condition, page_url):
    """O JSON-LD da página de um problema.

    Três peças, e cada uma responde a uma pergunta diferente do Google:

    * `BreadcrumbList` diz onde a página fica dentro do site, e é o que faz
      aparecer o caminho em vez do endereço cru no resultado da pesquisa;
    * `FAQPage` é a única aqui que muda o aspeto do resultado — as perguntas
      aparecem abertas por baixo do link. Só entra se houver perguntas: um
      `FAQPage` sem perguntas é uma promessa por cumprir;
    * `WebPage` diz de que trata a página e quem a publica.

    Fica deliberadamente fora `MedicalWebPage`. É um tipo legítimo e o site
    tem quem o assine, mas declarar conteúdo médico é assumir uma revisão
    clínica de cada frase — e isso é uma decisão da profissional, tomada
    depois de ler o texto, não um efeito lateral de uma migração.
    """

    negocio = {
        "@type": "HealthAndBeautyBusiness",
        "name": settings.SEO_SITE_NAME,
        "url": settings.SITE_URL.rstrip("/"),
    }

    grafo = [
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "Início",
                    "item": settings.SITE_URL.rstrip("/"),
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": "O que tratamos",
                    "item": absolute_url(
                        reverse("appointments:treated_condition_list")
                    ),
                },
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": condition.display_name,
                    "item": page_url,
                },
            ],
        },
        {
            "@type": "WebPage",
            "@id": page_url,
            "url": page_url,
            "name": condition.seo_title(),
            "description": condition.seo_description(),
            "inLanguage": "pt-PT",
            "about": {"@type": "Thing", "name": condition.display_name},
            "publisher": negocio,
        },
    ]

    # A imagem de abertura, se houver. Em endereço absoluto: um `/media/...`
    # dentro de um JSON-LD é lido por um robô que não sabe de que site veio, e
    # uma imagem declarada que não carrega é pior do que nenhuma.
    if condition.display_hero:
        grafo[-1]["primaryImageOfPage"] = {
            "@type": "ImageObject",
            "url": absolute_url(condition.display_hero.url),
            "caption": condition.hero_description,
        }

    perguntas = list(condition.questions.all())

    if perguntas:
        grafo.append(
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": pergunta.display_question,
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": pergunta.display_answer,
                        },
                    }
                    for pergunta in perguntas
                ],
            }
        )

    return json.dumps(
        {"@context": "https://schema.org", "@graph": grafo},
        ensure_ascii=False,
        indent=2,
    )
