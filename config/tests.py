import re

from django.conf import settings
from django.test import TestCase

from config.test_utils import ResetLanguageMixin
from django.urls import reverse


class HomeSalonAnnouncementTests(ResetLanguageMixin, TestCase):
    # O aviso do novo espaço aparece a cada entrada na página inicial. Não
    # guarda estado de dispensa de propósito, por isso um recarregamento
    # mostra-o outra vez.

    def test_homepage_shows_salon_announcement(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "salon-modal")
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

    def test_the_announcement_does_not_name_the_salon(self):
        # O texto passou a "Atendimento também com hora marcada": quem lê o
        # aviso precisa de saber onde e quando, não de que outra marca está
        # no mesmo edifício.
        html = self.client.get(reverse("home")).content.decode()

        inicio = html.index('class="modal-body"')
        corpo = html[inicio : html.index('class="modal-footer"', inicio)]
        texto = re.sub(r"<[^>]+>", " ", corpo)

        self.assertIn("Atendimento também com hora marcada", " ".join(texto.split()))
        self.assertNotIn("DIVAH", texto)

    def test_the_announcement_does_not_link_to_the_salon_instagram(self):
        # Quem entra no modal está a decidir sobre um atendimento, não a
        # navegar para outra conta.
        self.assertNotContains(
            self.client.get(reverse("home")), "instagram.com/divah.pt"
        )

    def test_the_map_still_finds_the_place(self):
        # O nome sai do texto, mas continua na consulta do mapa: é assim que o
        # Google encontra a loja.
        self.assertContains(self.client.get(reverse("home")), "q=DIVAH")

    def test_the_modal_offers_a_way_to_ask_questions(self):
        # A alternativa a marcar às cegas: quem tem dúvidas sobre um espaço
        # novo pergunta antes.
        response = self.client.get(reverse("home"))

        self.assertContains(response, "Dúvidas")
        self.assertContains(response, "https://wa.me/")

    def test_the_questions_button_opens_whatsapp_with_the_practice_number(self):
        digitos = settings.SEO_WHATSAPP_NUMBER.lstrip("+")
        html = self.client.get(reverse("home")).content.decode()

        self.assertIn(f"https://wa.me/{digitos}", html)

    def test_external_links_are_safe(self):
        # target="_blank" sem rel deixaria a página aberta ao window.opener.
        html = self.client.get(reverse("home")).content.decode()

        for ligacao in re.findall(r"<a\b[^>]*>", html):
            if 'target="_blank"' in ligacao:
                self.assertIn("noopener", ligacao, ligacao)

    def test_announcement_is_rendered_again_on_every_reload(self):
        self.client.get(reverse("home"))
        self.client.get(reverse("home"))

        response = self.client.get(reverse("home"))

        self.assertContains(response, "salon-modal")
        self.assertContains(response, "Galeria Avenida")
