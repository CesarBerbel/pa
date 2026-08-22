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

    def test_the_legal_links_appear_once_in_the_footer(self):
        # Estavam em dois sítios: na coluna "Links rápidos" e na barra final.
        # Duas ligações para o mesmo sítio a três centímetros uma da outra não
        # ajudam ninguém a encontrá-las — só alongam a coluna.
        html = self.client.get(reverse("home")).content.decode()
        # Limitado ao rodapé: o banner de cookies vem depois e também liga para
        # a política, o que não é duplicação nenhuma.
        rodape = html[html.index("<footer") : html.index("</footer>")]

        for nome in ("privacy_policy", "cookie_policy", "complaints_book"):
            with self.subTest(nome):
                self.assertEqual(rodape.count(f'href="{reverse(nome)}"'), 1)

    def test_the_quick_links_column_has_no_cookie_button(self):
        # O "Gerir cookies" da barra final chega. O do bloqueio do mapa fica,
        # que esse está onde a pessoa topa com o mapa em falta.
        html = self.client.get(reverse("home")).content.decode()

        self.assertNotIn("footer-cookie-link", html)

    def test_the_instagram_widget_waits_for_cookie_consent(self):
        # O widget da Elfsight é JavaScript de terceiros: não pode ser pedido
        # antes de a pessoa aceitar cookies funcionais. Uma tag <script> com o
        # endereço no HTML corria sempre, e é isso que este teste impede.
        html = self.client.get(reverse("home")).content.decode()

        self.assertIn("elfsight-app-", html)
        self.assertNotIn('<script src="https://elfsightcdn.com', html)
        self.assertIn("instagram-cookie-placeholder", html)

    def test_external_links_are_safe(self):
        # target="_blank" sem rel deixaria a página aberta ao window.opener.
        html = self.client.get(reverse("home")).content.decode()

        for ligacao in re.findall(r"<a[^>]*>", html):
            if 'target="_blank"' in ligacao:
                self.assertIn("noopener", ligacao, ligacao)
