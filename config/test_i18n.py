import re
from decimal import Decimal

from django.test import TestCase, override_settings

from config.test_utils import ResetLanguageMixin
from django.urls import reverse
from django.utils import translation

from appointments.models import Service, ServiceCategory
from config.views import SITEMAP_ROUTES


class LanguagePrefixRoutingTests(ResetLanguageMixin, TestCase):
    # Portuguese stays at the site root and English lives under /en/, because
    # config/urls.py uses i18n_patterns with prefix_default_language=False.

    def test_portuguese_homepage_stays_at_the_root(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agendar horário")
        self.assertContains(response, 'lang="pt-pt"')

    def test_english_homepage_is_served_under_the_en_prefix(self):
        response = self.client.get("/en/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Book an appointment")
        self.assertContains(response, 'lang="en"')
        self.assertNotContains(response, "Agendar horário")

    def test_crawler_files_are_not_language_prefixed(self):
        # robots.txt and sitemap.xml must keep working at the root.
        self.assertEqual(self.client.get("/robots.txt").status_code, 200)
        self.assertEqual(self.client.get("/sitemap.xml").status_code, 200)
        self.assertEqual(self.client.get("/en/robots.txt").status_code, 404)

    def test_public_booking_pages_answer_in_both_languages(self):
        self.assertEqual(self.client.get("/agenda-publica/").status_code, 200)
        self.assertEqual(self.client.get("/en/agenda-publica/").status_code, 200)


@override_settings(SITE_URL="https://exemplo.pt")
class SitemapLanguageTests(ResetLanguageMixin, TestCase):
    """O sitemap tem de trazer as duas versões, e sempre as mesmas.

    É servido fora do `i18n_patterns`, portanto o `reverse()` lá dentro segue o
    idioma do pedido. Sem forçar cada idioma à mão, o ficheiro mudava conforme
    quem o pedisse — e o Google, que chega em inglês ou em português conforme o
    robô, via metade do site de cada vez.
    """

    def enderecos(self, **extra):
        xml = self.client.get("/sitemap.xml", **extra).content.decode()

        return re.findall(r"<loc>(.*?)</loc>", xml)

    def test_lista_as_duas_versoes_de_cada_pagina(self):
        enderecos = self.enderecos()

        self.assertIn("https://exemplo.pt/", enderecos)
        self.assertIn("https://exemplo.pt/en/", enderecos)
        self.assertIn("https://exemplo.pt/agenda-publica/", enderecos)
        self.assertIn("https://exemplo.pt/en/agenda-publica/", enderecos)

    def test_ha_uma_entrada_por_pagina_e_por_idioma(self):
        enderecos = self.enderecos()

        self.assertEqual(len(enderecos), len(SITEMAP_ROUTES) * 2)
        self.assertEqual(len(set(enderecos)), len(enderecos))

    def test_o_idioma_do_pedido_nao_muda_o_ficheiro(self):
        em_portugues = self.enderecos(HTTP_ACCEPT_LANGUAGE="pt-pt")
        em_ingles = self.enderecos(HTTP_ACCEPT_LANGUAGE="en")

        self.assertEqual(em_portugues, em_ingles)


class LanguageSelectorTests(ResetLanguageMixin, TestCase):
    def test_homepage_renders_the_language_selector(self):
        response = self.client.get("/")

        self.assertContains(response, "language-switcher")
        self.assertContains(response, reverse("set_language"))
        self.assertContains(response, 'value="en"')
        self.assertContains(response, 'value="pt-pt"')

    def test_selecting_english_redirects_to_the_prefixed_url(self):
        response = self.client.post(
            reverse("set_language"),
            {"language": "en", "next": "/"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/en/")

    def test_selecting_portuguese_returns_to_the_unprefixed_url(self):
        # The selector submits the already translated path, because inside the
        # set_language request the active language no longer matches /en/ and
        # Django's own translate_url would leave the URL untouched.
        response = self.client.post(
            reverse("set_language"),
            {"language": "pt-pt", "next": "/"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_english_page_offers_the_portuguese_path_in_the_selector(self):
        # Cada bandeira leva no seu formulário o caminho já traduzido: sem
        # isso, mudar de idioma numa página interior devolvia à raiz.
        response = self.client.get("/en/agenda-publica/")

        self.assertContains(response, 'name="next" value="/agenda-publica/"')
        self.assertContains(response, 'name="next" value="/en/agenda-publica/"')

    def test_pages_declare_hreflang_alternates(self):
        response = self.client.get("/")
        html = response.content.decode()

        self.assertIn('hreflang="pt-pt"', html)
        self.assertIn('hreflang="en"', html)


class CatalogTranslationFallbackTests(ResetLanguageMixin, TestCase):
    # Service names and descriptions live in the database, so they are
    # translated through dedicated fields instead of gettext.

    def setUp(self):
        # As migrations semeiam categorias reais e "name" é único, por isso o
        # teste usa um nome próprio em vez de colidir com os dados semeados.
        self.category = ServiceCategory.objects.create(
            name="Reflexologia",
            slug="reflexologia-teste",
            description="Cuidados de reflexologia.",
            name_en="Reflexology",
            description_en="Reflexology care.",
        )

        self.service = Service.objects.create(
            category=self.category,
            name="Sessão de reflexologia",
            description="Tratamento de reflexologia.",
            duration_minutes=60,
            price=Decimal("40.00"),
        )

    def test_english_values_are_used_when_filled(self):
        with translation.override("en"):
            self.assertEqual(self.category.display_name, "Reflexology")
            self.assertEqual(self.category.display_description, "Reflexology care.")

    def test_portuguese_values_are_used_by_default(self):
        with translation.override("pt-pt"):
            self.assertEqual(self.category.display_name, "Reflexologia")
            self.assertEqual(
                self.category.display_description,
                "Cuidados de reflexologia.",
            )

    def test_empty_english_field_falls_back_to_portuguese(self):
        # The service was created without translations on purpose.
        with translation.override("en"):
            self.assertEqual(self.service.display_name, "Sessão de reflexologia")
            self.assertEqual(
                self.service.display_description,
                "Tratamento de reflexologia.",
            )

    def test_homepage_shows_translated_catalog_content(self):
        response = self.client.get("/en/")

        self.assertContains(response, "Reflexology")
        self.assertNotContains(response, "Cuidados de reflexologia.")
