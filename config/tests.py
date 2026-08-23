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


class TemplateSyntaxNeverReachesThePageTests(ResetLanguageMixin, TestCase):
    """Nenhuma página serve sintaxe de template por processar.

    O `{# ... #}` do Django **só funciona numa linha**: um comentário que
    atravesse várias é impresso como texto visível, no meio da página, sem
    erro nenhum a avisar. Aconteceu, e é uma falha que passa por todos os
    testes normais porque a página continua a responder 200.
    """

    PAGINAS = [
        "/",
        "/en/",
        "/servicos/feed/",
        "/agenda-publica/",
        "/antes-e-depois/",
        "/politica-de-privacidade/",
        "/politica-de-cookies/",
        "/livro-de-reclamacoes/",
    ]

    def test_no_page_leaks_template_syntax(self):
        for caminho in self.PAGINAS:
            with self.subTest(caminho):
                html = self.client.get(caminho, follow=True).content.decode()

                self.assertNotIn("{#", html)
                self.assertNotIn("#}", html)
                self.assertNotIn("{%", html)
                self.assertNotIn("endcomment", html)


class WoundCardFollowsNursingTests(ResetLanguageMixin, TestCase):
    """O cartão "Feridas e pensos" anda com a categoria Enfermagem.

    O penso especializado só se marca quando a enfermagem abrir. Ligar as duas
    coisas por dados, e não por memória, é o que impede o site de continuar a
    dizer "Em breve" depois de a marcação já estar aberta.
    """

    def enfermagem(self, em_breve):
        from appointments.models import ServiceCategory

        ServiceCategory.objects.update_or_create(
            slug="enfermagem",
            defaults={"name": "Enfermagem", "is_active": True, "is_coming_soon": em_breve},
        )

    def cartao(self):
        html = self.client.get(reverse("home")).content.decode()
        inicio = html.index("Feridas e pensos")

        return html[inicio - 700 : inicio + 100]

    def test_the_badge_is_there_while_nursing_is_coming_soon(self):
        self.enfermagem(em_breve=True)

        self.assertIn("coming-soon-badge", self.cartao())

    def test_the_badge_goes_away_when_nursing_opens(self):
        self.enfermagem(em_breve=False)

        self.assertNotIn("coming-soon-badge", self.cartao())

    def test_without_the_nursing_category_there_is_no_badge(self):
        # Uma categoria apagada não pode deixar o cartão preso em "Em breve".
        from appointments.models import Service, ServiceCategory

        # Os serviços protegem a categoria; saem primeiro.
        Service.objects.filter(category__slug="enfermagem").delete()
        ServiceCategory.objects.filter(slug="enfermagem").delete()

        self.assertNotIn("coming-soon-badge", self.cartao())
