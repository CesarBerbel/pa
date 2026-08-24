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

    O que estes testes protegem é a ordem em que as duas áreas aparecem e o
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

    def test_the_two_areas_exist(self):
        self.assertIn('class="app-agenda-feed"', self.html)
        self.assertIn('class="app-agenda-results"', self.html)

    def test_the_side_panel_is_gone(self):
        # Era um <aside> só para repetir o nome do serviço já assinalado no
        # catálogo, e ocupava a primeira área da grelha — no telemóvel, o
        # primeiro ecrã inteiro.
        self.assertNotIn("<aside", self.html)
        self.assertNotIn("app-service-summary", self.html)

    def test_the_catalog_is_a_cell_of_its_own(self):
        # Dentro dos resultados ficava entre a escolha do dia e os horários,
        # que é o que a página serve para mostrar.
        resultados = self.html.index('class="app-agenda-results"')
        catalogo = self.html.index('class="app-agenda-feed"')

        self.assertLess(catalogo, resultados)
        self.assertEqual(self.html.count('class="app-agenda-feed"'), 1)


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

    def test_slots_fit_three_to_a_row_on_a_phone(self):
        # Era uma coluna só porque o cartão levava a hora, o estado e o botão
        # "Marcar", que transbordava em duas colunas. Sem eles cabem três
        # horas por linha, e vê-se o dia inteiro sem rolar.
        self.assertVence(
            ".app-slots-grid",
            "grid-template-columns",
            "repeat(3, 1fr)",
            self.TELEMOVEL,
        )

    def test_slots_stay_in_a_grid_on_wider_screens(self):
        for largura in [self.TABLET, self.COMPUTADOR]:
            self.assertIn(
                "repeat",
                self.valor(".app-slots-grid", "grid-template-columns", largura) or "",
            )

    def test_the_slot_card_holds_only_the_hour(self):
        # Passou a ser uma peça só, centrada, em qualquer largura: era uma
        # linha de três colunas no telemóvel para caber a hora, o estado e o
        # botão. Nada disso existe agora.
        for largura in [self.TELEMOVEL, self.COMPUTADOR]:
            self.assertVence(".app-slot-card", "display", "flex", largura)
        self.assertVence(".app-slot-card", "display", "flex", self.COMPUTADOR)

    def test_catalog_is_placed_last_on_narrow_screens(self):
        areas = self.valor(".app-agenda-shell", "grid-template-areas", self.TELEMOVEL)

        self.assertIsNotNone(areas)

        ordem = re.findall(r'"([^"]+)"', areas)

        self.assertEqual([o.split()[0] for o in ordem], ["results", "feed"])

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

    def test_the_hand_points_at_what_has_to_be_clicked(self):
        # O convite a escolher o serviço aponta para o catálogo: ao lado
        # esquerdo no computador, por baixo dos horários no telemóvel. O
        # ícone é o mesmo do convite a escolher o dia — aponta para cima — e
        # roda. A regra do telemóvel tem de vir depois da genérica, senão
        # perde: uma media query não acrescenta especificidade.
        seletor = ".app-pick-service-state .app-empty-icon i"

        self.assertVence(seletor, "transform", "rotate(-90deg)", self.COMPUTADOR)
        self.assertVence(seletor, "transform", "rotate(180deg)", self.TELEMOVEL)

    def test_the_hand_that_asks_for_a_day_keeps_pointing_up(self):
        # A faixa de dias está por cima do convite, em qualquer largura.
        for largura in [self.TELEMOVEL, self.COMPUTADOR]:
            self.assertIsNone(
                self.valor(
                    ".app-pick-day-state .app-empty-icon i", "transform", largura
                )
            )

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


class DayStripServesEveryScreenTests(TestCase):
    """A faixa de dias substituiu a lista que existia no telemóvel.

    Havia dois controlos de data — a faixa no computador, uma lista no
    telemóvel — e agora há um só. O que a lista garantia tem de continuar a
    valer na faixa, senão a substituição perdeu qualidades pelo caminho.
    """

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)
        self.hoje = timezone.localdate()

    def pagina(self, **params):
        # Sem serviço a página abre à espera da escolha, e não há faixa.
        params.setdefault("service", self.service.pk)

        return self.client.get(reverse("appointments:public_visual_schedule"), params)

    def dias(self, response):
        return [dia["date"] for dia in response.context["week_days"]]

    def test_the_old_mobile_list_is_gone(self):
        html = self.pagina().content.decode()

        self.assertNotIn('id="day-select"', html)

    def test_the_strip_is_no_longer_desktop_only(self):
        # Era escondida no telemóvel porque a lista tratava disso lá. Sem a
        # lista, escondê-la deixava a página sem forma de escolher o dia.
        html = self.pagina(service=self.service.pk).content.decode()
        faixa = re.search(r'<div class="app-week-strip[^>]*>', html).group(0)

        self.assertNotIn("data-agenda-desktop-only", faixa)

    def test_past_days_are_never_offered(self):
        for dia in self.dias(self.pagina()):
            self.assertGreaterEqual(dia, self.hoje)

    def test_a_distant_chosen_day_is_shown(self):
        # Senão a faixa mostraria dias diferentes do que a página apresenta. A
        # faixa traz a janela de marcação inteira, por isso qualquer dia que se
        # possa escolher está lá — basta correr o carrossel até ele.
        distante = self.hoje + timedelta(days=15)

        dias = self.dias(self.pagina(date=distante.strftime("%Y-%m-%d")))

        self.assertIn(distante, dias)

    def test_every_day_says_how_many_slots_it_has(self):
        # É o que faz a faixa valer a pena: sem o número, escolher um dia é
        # adivinhar.
        for dia in self.pagina(service=self.service.pk).context["week_days"]:
            self.assertIn("free_slots", dia)


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

    def test_the_strip_and_the_catalog_are_on_every_screen(self):
        # Os dois eram escondidos no telemóvel, quando havia uma lista de dias
        # e um seletor de serviço a fazer o mesmo trabalho lá. Sem eles, a
        # faixa e o catálogo passaram a ser a única forma de escolher — e uma
        # página onde não se escolhe nada não serve para marcar.
        html = self.client.get(
            reverse("appointments:public_visual_schedule"),
            {"service": self.service.pk},
        ).content.decode()

        faixa = re.search(r'<div class="app-week-strip[^>]*>', html).group(0)
        catalogo = re.search(r'<section class="app-agenda-feed[^>]*>', html).group(0)

        self.assertNotIn("data-agenda-desktop-only", faixa)
        self.assertNotIn("data-agenda-desktop-only", catalogo)

    def test_the_slot_cards_are_never_hidden(self):
        # É o que sobra no telemóvel: esconder isto esvaziava a página.
        for largura in [self.TELEMOVEL, self.COMPUTADOR]:
            self.assertNotEqual(
                self.folha.resolve(".app-slots-grid", "display", largura), "none"
            )


class AgendaNeverWiderThanTheScreenTests(TestCase):
    """Nada na agenda pode esticar a página para fora do ecrã.

    A faixa de dias traz a janela de marcação inteira e só se vê a rolar. As
    células da grelha são o sítio onde essa largura toda pode escapar: com
    `min-width: auto`, uma célula nunca fica mais estreita do que aquilo que
    tem dentro, e estica a página atrás dela — o carrossel deixa de rolar e as
    setas saem do ecrã, uma para cada lado.
    """

    TELEMOVEL = 390
    COMPUTADOR = 1280

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folha = Stylesheet(CSS.read_text(encoding="utf-8"))

    def test_the_agenda_cells_can_shrink_below_their_content(self):
        celulas = [
            ".app-agenda-feed",
            ".app-agenda-results",
        ]

        for celula in celulas:
            for largura in [self.TELEMOVEL, self.COMPUTADOR]:
                with self.subTest(celula=celula, largura=largura):
                    self.assertEqual(
                        self.folha.resolve(celula, "min-width", largura), "0"
                    )

    def test_the_strip_is_the_only_part_of_the_carousel_that_shrinks(self):
        # A faixa encolhe até ao que sobra e rola por dentro; as setas ficam
        # do tamanho que têm, senão desapareciam com os dias a mais.
        for largura in [self.TELEMOVEL, self.COMPUTADOR]:
            with self.subTest(largura=largura):
                self.assertEqual(
                    self.folha.resolve(".app-week-strip", "min-width", largura), "0"
                )
                self.assertEqual(
                    self.folha.resolve(".app-week-arrow", "flex", largura), "0 0 auto"
                )

    def test_the_day_cards_scroll_instead_of_being_squeezed(self):
        # Espremidos, cabiam todos e o carrossel deixava de ter para onde ir.
        for largura in [self.TELEMOVEL, self.COMPUTADOR]:
            with self.subTest(largura=largura):
                self.assertEqual(
                    self.folha.resolve(".app-week-day", "flex", largura), "0 0 auto"
                )
