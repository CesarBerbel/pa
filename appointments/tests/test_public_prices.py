import re

from django.test import TestCase

from appointments.models import Service, ServiceCategory
from config.test_utils import ResetLanguageMixin

# O preço é desenhado dentro de `service-public-meta`, e é só aí que a bandeira
# `show_prices` manda. Procurar "15 €" na página inteira apanhava também as
# descrições — e uma delas passou a dizer "Entre 15 € e 20 €", o que pôs o
# teste a falhar por causa de um texto que nunca foi um preço.
METAS = re.compile(r'<div class="service-public-meta">(.*?)</div>', re.S)
VALOR = re.compile(r"\d+(?:,\d+)?\s*€")


def precos_desenhados(html):
    return [valor for bloco in METAS.findall(html) for valor in VALOR.findall(bloco)]


class PublicPriceVisibilityTests(ResetLanguageMixin, TestCase):
    # Prices are shown only in categories where show_prices is enabled, so that
    # values that have not been reviewed are never published by accident.

    def test_only_reviewed_categories_have_prices_enabled(self):
        enabled = set(
            ServiceCategory.objects.filter(show_prices=True).values_list(
                "slug", flat=True
            )
        )

        self.assertEqual(enabled, {"podologia", "laserterapia"})

    def test_service_feed_shows_prices_for_enabled_categories(self):
        response = self.client.get("/servicos/feed/")
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)

        desenhados = precos_desenhados(html)

        # Avaliação em Podologia: 15 €
        self.assertIn("15 €", desenhados)
        # Verruga plantar – protocolo inicial (5 sessões): 250 €
        self.assertIn("250 €", desenhados)

    def test_service_feed_keeps_price_on_request_for_other_categories(self):
        response = self.client.get("/servicos/feed/")

        self.assertContains(response, "Sob consulta")

    def test_homepage_teaser_shows_prices_for_enabled_categories(self):
        response = self.client.get("/")

        self.assertContains(response, "service-teaser-price")
        self.assertContains(response, "15 €")

    def test_disabling_the_flag_hides_the_prices_again(self):
        ServiceCategory.objects.filter(slug="podologia").update(show_prices=False)
        ServiceCategory.objects.filter(slug="laserterapia").update(show_prices=False)

        response = self.client.get("/servicos/feed/")
        html = response.content.decode()

        # Nenhum valor onde os preços se desenham. Uma descrição que fale de
        # dinheiro — "Entre 15 € e 20 €" — é texto escrito de propósito e não
        # um preço publicado por engano, que é o que esta bandeira trava.
        self.assertEqual(precos_desenhados(html), [])

    def test_prices_are_whole_numbers_without_trailing_decimals(self):
        # floatformat:"-2" keeps decimals only when they exist, so a 15.00 price
        # must render as "15 €" and not "15,00 €".
        response = self.client.get("/servicos/feed/")
        html = response.content.decode()

        self.assertIn("15 €", html)
        self.assertNotIn("15,00 €", html)

    def test_english_page_also_shows_the_prices(self):
        response = self.client.get("/en/servicos/feed/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "15 €")

    def test_every_priced_service_renders_a_value(self):
        expected = Service.objects.filter(
            category__show_prices=True,
            is_active=True,
        ).count()

        html = self.client.get("/servicos/feed/").content.decode()

        for service in Service.objects.filter(
            category__show_prices=True,
            is_active=True,
        ):
            self.assertIn(service.display_name, html)

        self.assertEqual(expected, 16)
