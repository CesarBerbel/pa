import re

from django.conf import settings
from django.test import TestCase

from config.test_utils import ResetLanguageMixin
from django.urls import reverse


class HomePageTests(ResetLanguageMixin, TestCase):
    """O que a página inicial garante depois de o modal do salão sair.

    Os testes que morreram com ele eram sobre o texto, o mapa e os botões
    dentro do modal. Os que ficam não dependiam dele: valem para a página, e
    é aqui que continuam a valer.
    """

    def test_navigation_links_to_the_instagram_section(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode()

        # The anchor must exist in the navigation and match a rendered section,
        # otherwise the menu entry scrolls nowhere.
        self.assertIn('href="/#instagram"', html)
        self.assertIn('<section id="instagram"', html)

    def test_the_page_text_does_not_name_the_salon(self):
        # O nome de outra marca no mesmo edifício não pertence ao que se lê na
        # página. Continua na consulta do mapa, e é o teste seguinte que o diz.
        html = self.client.get(reverse("home")).content.decode()
        texto = re.sub(r"<[^>]+>", " ", html)

        self.assertNotIn("DIVAH", texto)

    def test_the_map_still_finds_the_place(self):
        # O nome sai do texto, mas continua na consulta do mapa do rodapé: é
        # assim que o Google encontra a loja.
        self.assertContains(self.client.get(reverse("home")), "q=DIVAH")

    def test_the_page_does_not_link_to_the_salon_instagram(self):
        self.assertNotContains(
            self.client.get(reverse("home")), "instagram.com/divah.pt"
        )

    def test_whatsapp_uses_the_practice_number(self):
        digitos = settings.SEO_WHATSAPP_NUMBER.lstrip("+")
        html = self.client.get(reverse("home")).content.decode()

        self.assertIn(f"https://wa.me/{digitos}", html)

    def test_external_links_are_safe(self):
        # target="_blank" sem rel deixaria a página aberta ao window.opener.
        html = self.client.get(reverse("home")).content.decode()

        for ligacao in re.findall(r"<a[^>]*>", html):
            if 'target="_blank"' in ligacao:
                self.assertIn("noopener", ligacao, ligacao)
