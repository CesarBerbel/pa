import re
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Service
from appointments.tests.factories import (
    create_test_service,
    ensure_test_business_hour,
    get_test_service_category,
)


class PageWaitsForAServiceTests(TestCase):
    """A agenda abre sem horários, à espera da escolha no catálogo.

    Antes escolhia o primeiro serviço da lista por conta própria: a página
    abria cheia de horas que eram de um serviço que ninguém tinha pedido. E é
    a duração do serviço que decide quais são as horas livres, portanto eram
    horas que podiam não servir para nada.
    """

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)

        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(18, 0),
            )

    def pagina(self, **params):
        return self.client.get(reverse("appointments:public_visual_schedule"), params)

    def test_no_service_is_chosen_for_the_visitor(self):
        self.assertIsNone(self.pagina().context["selected_service"])

    def test_the_page_opens_without_a_single_hour(self):
        resposta = self.pagina()

        self.assertEqual(resposta.context["slots"], [])
        self.assertEqual(resposta.context["week_days"], [])

    def test_the_page_asks_for_a_service(self):
        html = self.pagina().content.decode()

        self.assertIn("Escolha um serviço", html)
        self.assertNotIn("app-week-strip", html)
        self.assertNotIn("Escolha um dia acima", html)

    def test_nothing_comes_pre_chosen(self):
        # Entrar na página não escolhe nada por ninguém: nem serviço, nem dia.
        # A única coisa que a página pede é a escolha do serviço.
        resposta = self.pagina()
        html = resposta.content.decode()

        self.assertIsNone(resposta.context["selected_service"])
        self.assertFalse(resposta.context["day_chosen"])
        # `is-selected` marca o serviço no catálogo; `is-active`, o dia na
        # faixa. Nenhum dos dois pode estar escrito ao entrar.
        self.assertNotIn("is-selected", html)
        self.assertNotIn("app-week-day is-active", html)

    def test_choosing_the_service_still_does_not_choose_the_day(self):
        # Escolhido o serviço, a página mostra os dias e volta a esperar.
        resposta = self.pagina(service=self.service.pk)
        html = resposta.content.decode()

        self.assertFalse(resposta.context["day_chosen"])
        self.assertNotIn("app-week-day is-active", html)
        self.assertIn("Escolha um dia acima", html)

    def test_choosing_a_service_brings_the_days(self):
        html = self.pagina(service=self.service.pk).content.decode()

        self.assertIn("app-week-strip", html)
        self.assertIn("Escolha um dia acima", html)
        self.assertNotIn("Escolha um serviço", html)

    def test_the_catalog_opens_on_the_chosen_category(self):
        # Depois de escolher, o catálogo fechava-se todo e o serviço marcado
        # ficava escondido dentro de uma sanfona por abrir.
        categoria = self.service.category
        html = self.pagina(service=self.service.pk).content.decode()

        painel = re.search(
            rf'<div\s+id="service-category-{categoria.id}"(.*?)>', html, re.S
        ).group(1)

        self.assertIn("show", painel)

    def test_the_catalog_starts_closed_before_a_service_is_chosen(self):
        categoria = self.service.category
        html = self.pagina().content.decode()

        painel = re.search(
            rf'<div\s+id="service-category-{categoria.id}"(.*?)>', html, re.S
        ).group(1)

        self.assertNotIn("show", painel)

    def test_only_the_chosen_category_opens(self):
        outra = get_test_service_category(
            name="Categoria dos testes", slug="categoria-dos-testes", display_order=99
        )
        create_test_service(category=outra, name="Serviço da outra categoria")

        html = self.pagina(service=self.service.pk).content.decode()
        sanfonas = re.findall(r'class="accordion-collapse collapse ?(show)?"', html)

        self.assertGreater(len(sanfonas), 1)
        self.assertEqual(sanfonas.count("show"), 1)

    def test_the_side_panel_with_the_chosen_service_is_gone(self):
        # Repetia o nome do serviço que o catálogo já assinala, e ocupava a
        # primeira área da grelha — no telemóvel, o primeiro ecrã inteiro.
        html = self.pagina(service=self.service.pk).content.decode()

        self.assertNotIn("app-service-summary", html)
        self.assertNotIn("Serviço selecionado", html)

    def test_the_catalog_link_carries_no_day_before_one_is_chosen(self):
        # Com a data no endereço, escolher o serviço saltava logo para a
        # grelha de um dia, sem passar pela faixa.
        ligacao = self.ligacao_do_catalogo(self.pagina())

        self.assertIn(f"service={self.service.pk}", ligacao)
        self.assertNotIn("date=", ligacao)

    def test_the_catalog_link_keeps_the_day_once_one_is_chosen(self):
        # Trocar de serviço a meio não deve desfazer a escolha do dia.
        escolhido = (timezone.localdate() + timedelta(days=3)).isoformat()

        ligacao = self.ligacao_do_catalogo(
            self.pagina(service=self.service.pk, date=escolhido)
        )

        self.assertIn(f"date={escolhido}", ligacao)

    def ligacao_do_catalogo(self, resposta):
        # O catálogo traz também os serviços sedeados pelas migrações: a
        # ligação que interessa é a do serviço destes testes.
        html = resposta.content.decode()
        catalogo = html[html.index('class="app-agenda-feed') :]

        return re.search(
            rf'href="([^"]*service={self.service.pk}[^"]*)"', catalogo
        ).group(1)

    def test_without_any_active_service_the_page_says_so(self):
        Service.objects.update(is_active=False)

        html = self.pagina().content.decode()

        self.assertIn("Nenhum serviço ativo registado", html)
        self.assertNotIn("Escolha um serviço<", html)
