from django.test import TestCase

from config.test_utils import ResetLanguageMixin
from django.urls import reverse


class HomeSalonAnnouncementTests(ResetLanguageMixin, TestCase):
    # The DIVAH announcement must render on every homepage load. It keeps no
    # dismissal state on purpose, so a reload always shows it again.

    def test_homepage_shows_salon_announcement(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "salon-modal")
        self.assertContains(response, "DIVAH")
        self.assertContains(response, "hora marcada")
        self.assertContains(response, "Av. Sá da Bandeira")
        self.assertContains(response, "Loja 108")
        self.assertContains(response, "Galeria Avenida")

    def test_modal_script_waits_for_bootstrap_to_load(self):
        # O bloco de conteúdo é renderizado antes dos <script> do base.html.
        # Sem esperar pelo DOMContentLoaded, "bootstrap" ainda não existe e o
        # modal nunca chega a abrir.
        html = self.client.get(reverse("home")).content.decode()

        posicao_script = html.find("getOrCreateInstance")
        posicao_bootstrap = html.find("bootstrap.bundle.min.js")

        self.assertLess(posicao_script, posicao_bootstrap)
        self.assertIn('addEventListener("DOMContentLoaded"', html)

    def test_modal_map_stays_behind_the_cookie_consent(self):
        # O mapa do modal usa o mesmo mecanismo do rodapé: o src só é injetado
        # depois de aceitar cookies funcionais, nunca no HTML servido.
        response = self.client.get(reverse("home"))
        html = response.content.decode()

        self.assertIn('data-cookie-category="functional"', html)
        self.assertIn('data-cookie-placeholder="#salon-modal-map-placeholder"', html)
        self.assertNotIn('<iframe src="https://www.google.com/maps', html)

    def test_navigation_links_to_the_instagram_section(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode()

        # The anchor must exist in the navigation and match a rendered section,
        # otherwise the menu entry scrolls nowhere.
        self.assertIn('href="/#instagram"', html)
        self.assertIn('<section id="instagram"', html)

    def test_salon_name_links_to_its_instagram(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "https://www.instagram.com/divah.pt")
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_announcement_is_rendered_again_on_every_reload(self):
        self.client.get(reverse("home"))
        self.client.get(reverse("home"))

        response = self.client.get(reverse("home"))

        self.assertContains(response, "salon-modal")
        self.assertContains(response, "DIVAH")
