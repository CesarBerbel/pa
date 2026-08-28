import json
import re

from django.conf import settings
from django.test import TestCase, override_settings

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

    def test_the_page_does_not_name_the_salon_anywhere(self):
        """O nome de outra marca no mesmo edifício não pertence a esta página.

        Chegou a ficar na consulta do mapa do rodapé, porque era assim que o
        Google encontrava a morada quando a clínica ainda não tinha ficha
        própria. Agora tem, o mapa aponta para ela, e o nome deixou de ser
        preciso em lado nenhum.
        """

        self.assertNotContains(self.client.get(reverse("home")), "DIVAH")

    def test_the_map_points_at_the_clinic_listing(self):
        html = self.client.get(reverse("home")).content.decode()

        self.assertIn("Priscila%20Arantes%20Pedicure%20Terap", html)

    def test_the_map_waits_for_consent(self):
        """O endereço vive em `data-cookie-src` e não em `src`.

        Escrito como `src`, o mapa da Google carregava antes de alguém dizer
        que sim — e a política de cookies desta casa passava a mentir.
        """

        html = self.client.get(reverse("home")).content.decode()

        self.assertIn('data-cookie-src="https://www.google.com/maps/embed', html)

        # Ancorado: `data-cookie-src="..."` contém `src="..."` como
        # sub-cadeia, e uma procura solta dava sempre o alarme. O que se
        # procura é um `src` que não seja o fim de outro atributo.
        self.assertIsNone(
            re.search(r'(?<![-\w])src="https://www\.google\.com/maps/embed', html),
            "o mapa carrega antes do consentimento",
        )

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

    # A primeira versão deste teste só via páginas públicas, e por isso deixou
    # passar um comentário partido numa página interna. Um teste que cobre
    # metade das páginas dá a impressão de cobrir todas.
    PAGINAS_INTERNAS = [
        "/dashboard/",
        "/agenda/horarios/",
        "/agenda/semana/",
        "/agenda/mes/",
        "/marcacoes/",
        "/clientes/",
        "/servicos/",
        "/antes-e-depois/gerir/",
        "/bloqueios/",
        "/horas-trabalhadas/",
        "/agenda/regras/",
        "/marcacoes/auditoria/",
        "/diagnostico/horarios/",
        "/emails/modelos/",
        "/paginas/o-que-tratamos/",
        "/mensagens/whatsapp/",
        "/mensagens/envio/",
    ]

    def verificar(self, caminho, html):
        for resto in ["{#", "#}", "{%", "endcomment"]:
            self.assertNotIn(resto, html, f"{caminho} serve {resto!r}")

    def test_no_public_page_leaks_template_syntax(self):
        for caminho in self.PAGINAS:
            with self.subTest(caminho):
                self.verificar(
                    caminho, self.client.get(caminho, follow=True).content.decode()
                )

    def test_no_internal_page_leaks_template_syntax(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_superuser(
            email="admin@example.com", password="x", full_name="Admin"
        )
        self.client.login(email="admin@example.com", password="x")

        for caminho in self.PAGINAS_INTERNAS:
            with self.subTest(caminho):
                resposta = self.client.get(caminho, follow=True)

                self.assertEqual(resposta.status_code, 200, caminho)
                self.verificar(caminho, resposta.content.decode())


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
            defaults={
                "name": "Enfermagem",
                "is_active": True,
                "is_coming_soon": em_breve,
            },
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


class GoogleBusinessProfileTests(TestCase):
    """A ligação entre o site e a ficha do negócio no Google.

    O site descrevia-se — nome, morada, telefone, horário — mas não dizia qual
    é a ficha dele. Sem isso, o Google pode ficar com uma ficha sem site e um
    site sem ficha, e o botão de marcação da ficha nunca é uma continuação
    desta casa.
    """

    FICHA = "https://g.page/priscila-arantes-pa"

    def json_ld(self):
        html = self.client.get(reverse("home")).content.decode()

        bloco = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            html,
            re.DOTALL,
        )

        self.assertIsNotNone(bloco, "A página inicial ficou sem JSON-LD.")

        return json.loads(bloco.group(1))

    @override_settings(SEO_GOOGLE_BUSINESS_URL=FICHA)
    def test_the_profile_is_declared_as_the_same_business(self):
        dados = self.json_ld()

        self.assertEqual(dados["sameAs"], [self.FICHA])
        self.assertEqual(dados["hasMap"], self.FICHA)

    @override_settings(SEO_GOOGLE_BUSINESS_URL="")
    def test_without_a_profile_nothing_is_declared(self):
        # Um `sameAs` a apontar para lado nenhum é pior do que não o ter.
        dados = self.json_ld()

        self.assertNotIn("sameAs", dados)
        self.assertNotIn("hasMap", dados)

    @override_settings(SEO_GOOGLE_BUSINESS_URL=f"  {FICHA}  ")
    def test_spaces_around_a_pasted_link_do_not_become_the_link(self):
        # Copiado do Google, o endereço vem quase sempre com espaços atrás.
        dados = self.json_ld()

        self.assertEqual(dados["hasMap"], self.FICHA)
