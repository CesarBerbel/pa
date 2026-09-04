from django.test import TestCase

from config.test_utils import ResetLanguageMixin

from appointments.models import Service, ServiceCategory


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
        # Avaliação em Podologia: 15 €
        self.assertIn("15 €", html)
        # Verruga plantar – protocolo inicial (5 sessões): 250 €
        self.assertIn("250 €", html)

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

        self.assertNotIn("15 €", html)
        self.assertNotIn("250 €", html)

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
