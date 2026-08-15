import re
from datetime import time, timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.tests.css_cascade import Stylesheet
from appointments.tests.factories import create_test_service, ensure_test_business_hour

CSS = Path(settings.BASE_DIR) / "static" / "css" / "public.css"


class PublicScheduleLayoutTests(TestCase):
    """Estrutura da agenda pública no telemóvel.

    O que estes testes protegem é a ordem em que as três áreas aparecem e o
    facto de a folha de estilo as saber colocar. O aspeto em si não se testa
    daqui, mas a estrutura que o torna possível sim.
    """

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)

        self.selected_date = timezone.localdate() + timedelta(days=14)
        while self.selected_date.weekday() != 0:
            self.selected_date += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.selected_date.weekday(),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )

        self.response = self.client.get(
            reverse("appointments:public_visual_schedule"),
            {
                "service": self.service.pk,
                "date": self.selected_date.strftime("%Y-%m-%d"),
            },
        )

        self.html = self.response.content.decode()

    def test_page_loads(self):
        self.assertEqual(self.response.status_code, 200)

    def test_the_three_areas_exist(self):
        self.assertIn('class="app-agenda-filter"', self.html)
        self.assertIn('class="app-agenda-feed"', self.html)
        self.assertIn('class="app-agenda-results"', self.html)

    def test_catalog_comes_after_the_slots_in_the_markup(self):
        # No telemóvel a grelha passa a uma coluna e segue a ordem do HTML.
        # Se o catálogo voltasse para dentro do <aside>, ficava entre a escolha
        # do serviço e os horários, que é o que a página serve para mostrar.
        fim_do_filtro = self.html.index("</aside>")
        catalogo = self.html.index('class="app-agenda-feed"')

        self.assertLess(fim_do_filtro, catalogo)

    def test_catalog_is_not_nested_inside_the_filter(self):
        self.assertEqual(self.html.count("<aside"), 1)
        self.assertEqual(self.html.count("</aside>"), 1)


class PublicScheduleStylesheetTests(TestCase):
    """O que o browser acaba mesmo por aplicar na agenda, por largura de ecrã.

    Escrever a regra não chega: `public.css` redefine estes seletores em várias
    camadas sem media query, e como uma media query não acrescenta
    especificidade, a última a aparecer é a que ganha. Foi assim que a versão
    para telemóvel se partiu. Estes testes resolvem a cascata em vez de
    procurarem o texto da regra.
    """

    TELEMOVEL = 390
    TABLET = 768
    COMPUTADOR = 1280

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS.read_text(encoding="utf-8")
        cls.folha = Stylesheet(cls.css)

    def valor(self, seletor, prop, width, hover=False):
        return self.folha.resolve(seletor, prop, width, hover=hover)

    def assertVence(self, seletor, prop, esperado, width, hover=False):
        obtido = self.valor(seletor, prop, width, hover=hover)

        self.assertEqual(
            obtido,
            esperado,
            f"{seletor} {{ {prop} }} a {width}px vale {obtido!r}, "
            f"esperado {esperado!r}. Definido em: "
            f"{self.folha.declaring_rules(seletor, prop)}",
        )

    def test_slots_are_a_single_column_on_a_phone(self):
        # Em duas colunas o botão "Marcar" transbordava do cartão.
        self.assertVence(
            ".app-slots-grid", "grid-template-columns", "1fr", self.TELEMOVEL
        )

    def test_slots_stay_in_a_grid_on_wider_screens(self):
        for largura in [self.TABLET, self.COMPUTADOR]:
            self.assertIn(
                "repeat",
                self.valor(".app-slots-grid", "grid-template-columns", largura) or "",
            )

    def test_slot_card_becomes_a_row_on_a_phone(self):
        self.assertVence(".app-slot-card", "display", "grid", self.TELEMOVEL)
        self.assertVence(".app-slot-card", "display", "flex", self.COMPUTADOR)

    def test_catalog_is_placed_last_on_narrow_screens(self):
        areas = self.valor(".app-agenda-shell", "grid-template-areas", self.TELEMOVEL)

        self.assertIsNotNone(areas)

        ordem = re.findall(r'"([^"]+)"', areas)

        self.assertEqual([o.split()[0] for o in ordem], ["filter", "results", "feed"])

    def test_single_column_on_narrow_screens(self):
        for largura in [self.TELEMOVEL, self.TABLET]:
            self.assertVence(
                ".app-agenda-shell", "grid-template-columns", "1fr", largura
            )

    def test_two_columns_on_a_computer(self):
        colunas = self.valor(
            ".app-agenda-shell", "grid-template-columns", self.COMPUTADOR
        )

        self.assertIn("1fr", colunas)
        self.assertNotEqual(colunas, "1fr")

    def test_results_header_stacks_on_a_phone(self):
        # O título e a etiqueta de estado lado a lado empurravam a página para
        # fora do ecrã, porque a etiqueta é nowrap.
        self.assertVence(
            ".app-agenda-results-header", "flex-direction", "column", self.TELEMOVEL
        )

    def test_status_pill_may_wrap_on_a_phone(self):
        self.assertVence(
            ".availability-status-pill", "white-space", "normal", self.TELEMOVEL
        )

    def test_status_pill_stays_on_one_line_on_a_computer(self):
        self.assertVence(
            ".availability-status-pill", "white-space", "nowrap", self.COMPUTADOR
        )

    def test_no_reserved_empty_space_on_a_phone(self):
        # Reservar 620px para oito horários deixava um retângulo branco enorme
        # por baixo da agenda.
        for largura in [self.TELEMOVEL, self.TABLET]:
            self.assertIsNone(self.valor(".app-agenda-results", "min-height", largura))

        self.assertVence(".app-agenda-results", "min-height", "620px", self.COMPUTADOR)

    def test_hover_lift_does_not_apply_on_touch(self):
        # Num ecrã tátil o :hover fica agarrado depois do toque: o cartão
        # levantava-se e assim ficava.
        self.assertIsNone(
            self.valor(".app-slot-card:hover", "transform", self.TELEMOVEL, hover=False)
        )
        self.assertIsNone(
            self.valor(".app-week-day:hover", "transform", self.TELEMOVEL, hover=False)
        )

    def test_hover_lift_still_applies_with_a_pointer(self):
        self.assertIsNotNone(
            self.valor(".app-slot-card:hover", "transform", self.COMPUTADOR, hover=True)
        )

    def test_stylesheet_braces_are_balanced(self):
        sem_comentarios = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)

        self.assertEqual(
            sem_comentarios.count("{"),
            sem_comentarios.count("}"),
        )


class MobileDaySelectorTests(TestCase):
    """No telemóvel a data escolhe-se por lista, não pela faixa de dias."""

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)
        self.hoje = timezone.localdate()

    def pagina(self, **params):
        return self.client.get(reverse("appointments:public_visual_schedule"), params)

    def opcoes(self, response):
        return list(response.context["day_options"])

    def test_the_selector_offers_the_coming_days(self):
        opcoes = self.opcoes(self.pagina())

        self.assertGreater(len(opcoes), 7)
        self.assertEqual(opcoes[0], self.hoje)
        self.assertEqual(opcoes, sorted(opcoes))

    def test_past_days_are_never_offered(self):
        for dia in self.opcoes(self.pagina()):
            self.assertGreaterEqual(dia, self.hoje)

    def test_closed_weekdays_are_left_out(self):
        # Uma lista com dias que aparecem sempre esgotados faria a cliente
        # pensar que não há vaga nenhuma.
        fechado = (self.hoje.weekday() + 2) % 7
        ensure_test_business_hour(weekday=fechado, is_active=False)

        for dia in self.opcoes(self.pagina()):
            if dia == self.hoje:
                continue

            self.assertNotEqual(dia.weekday(), fechado)

    def test_the_chosen_day_is_always_in_the_list(self):
        # Senão a lista mostraria um dia diferente do que a página apresenta.
        fechado = (self.hoje.weekday() + 2) % 7
        ensure_test_business_hour(weekday=fechado, is_active=False)

        alvo = self.hoje + timedelta(days=1)
        while alvo.weekday() != fechado:
            alvo += timedelta(days=1)

        opcoes = self.opcoes(self.pagina(date=alvo.strftime("%Y-%m-%d")))

        self.assertIn(alvo, opcoes)
        self.assertEqual(opcoes, sorted(opcoes))

    def test_a_distant_day_is_added_to_the_list(self):
        distante = self.hoje + timedelta(days=200)

        opcoes = self.opcoes(self.pagina(date=distante.strftime("%Y-%m-%d")))

        self.assertIn(distante, opcoes)

    def test_the_selector_marks_the_chosen_day(self):
        alvo = self.hoje + timedelta(days=3)

        html = self.pagina(date=alvo.strftime("%Y-%m-%d")).content.decode()
        lista = re.search(r'<select\s+id="day-select".*?</select>', html, re.S).group(0)

        escolhida = re.search(r'value="([^"]+)"[^>]*selected', lista)

        self.assertIsNotNone(escolhida)
        self.assertEqual(escolhida.group(1), alvo.strftime("%Y-%m-%d"))

    def test_the_selector_never_submits_its_own_date(self):
        # Sem name, a lista é só um controlo que escreve em #date. Com name,
        # passariam duas datas no pedido e ganhava a última.
        html = self.pagina().content.decode()
        lista = re.search(r'<select\s+id="day-select"[^>]*>', html, re.S).group(0)

        self.assertNotIn("name=", lista)

    def test_the_date_field_is_still_the_one_that_counts(self):
        html = self.pagina().content.decode()

        self.assertIn('id="date"', html)
        self.assertIn('name="date"', html)


class MobileAgendaVisibilityTests(TestCase):
    """O que desaparece no telemóvel, resolvido pela cascata e não pelo texto."""

    TELEMOVEL = 390
    COMPUTADOR = 1280

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folha = Stylesheet(CSS.read_text(encoding="utf-8"))

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)

    def test_browsing_aids_are_hidden_on_a_phone(self):
        self.assertEqual(
            self.folha.resolve("[data-agenda-desktop-only]", "display", self.TELEMOVEL),
            "none",
        )

    def test_browsing_aids_stay_on_a_computer(self):
        self.assertNotEqual(
            self.folha.resolve(
                "[data-agenda-desktop-only]", "display", self.COMPUTADOR
            ),
            "none",
        )

    def test_the_day_list_only_exists_on_a_phone(self):
        self.assertEqual(
            self.folha.resolve("[data-agenda-mobile-only]", "display", self.COMPUTADOR),
            "none",
        )
        self.assertEqual(
            self.folha.resolve("[data-agenda-mobile-only]", "display", self.TELEMOVEL),
            "block",
        )

    def test_the_week_strip_and_the_catalog_carry_the_mark(self):
        html = self.client.get(
            reverse("appointments:public_visual_schedule")
        ).content.decode()

        faixa = re.search(r'<div class="app-week-strip[^>]*>', html).group(0)
        catalogo = re.search(r'<section class="app-agenda-feed[^>]*>', html).group(0)

        self.assertIn("data-agenda-desktop-only", faixa)
        self.assertIn("data-agenda-desktop-only", catalogo)

    def test_the_slot_cards_are_never_hidden(self):
        # É o que sobra no telemóvel: esconder isto esvaziava a página.
        for largura in [self.TELEMOVEL, self.COMPUTADOR]:
            self.assertNotEqual(
                self.folha.resolve(".app-slots-grid", "display", largura), "none"
            )
