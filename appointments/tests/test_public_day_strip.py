import re
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import BusinessHour, ScheduleBlock, SchedulingSetting
from appointments.tests.factories import create_test_service, ensure_test_business_hour


def definir_horizonte(dias):
    definicao = SchedulingSetting.load()
    definicao.booking_horizon_days = dias
    definicao.save()

    return definicao


class PublicDayStripTests(TestCase):
    """A faixa de dias da agenda pública corre para a frente a partir de hoje.

    Antes começava na segunda-feira da semana escolhida: numa quinta-feira,
    metade da faixa eram dias já passados, que nunca teriam horários.
    """

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)
        self.today = timezone.localdate()

        # Todos os dias abertos, para a faixa não depender do dia em que os
        # testes correrem.
        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(18, 0),
            )

    def pagina(self, query=""):
        # O serviço vai sempre no endereço: sem ele a página abre à espera da
        # escolha, e não há faixa nenhuma para inspecionar. As vagas de cada
        # dia dependem da duração do serviço.
        separador = "&" if query else "?"

        return self.client.get(
            f"{reverse('appointments:public_visual_schedule')}"
            f"{query}{separador}service={self.service.pk}"
        )

    def strip_dates(self, query=""):
        return [day["date"] for day in self.pagina(query).context["week_days"]]

    def selected_date(self, query=""):
        return self.pagina(query).context["selected_date"]

    def test_strip_starts_today_by_default(self):
        datas = self.strip_dates()

        self.assertEqual(datas[0], self.today)

    def test_the_strip_covers_the_whole_booking_window(self):
        # O horizonte conta hoje: dez dias vão de hoje a hoje mais nove.
        definir_horizonte(10)

        datas = self.strip_dates()

        self.assertEqual(len(datas), 10)
        self.assertEqual(datas[0], self.today)
        self.assertEqual(datas[-1], self.today + timedelta(days=9))

    def test_the_strip_follows_the_configured_horizon(self):
        # Estava escrito nas definições que o site deixa marcar até N dias, e
        # a faixa mostrava sempre sete — nem chegava lá, nem parava lá.
        for dias in [1, 3, 30]:
            with self.subTest(horizonte=dias):
                definir_horizonte(dias)

                datas = self.strip_dates()

                self.assertEqual(len(datas), dias)
                self.assertEqual(datas[-1], self.today + timedelta(days=dias - 1))

    def test_the_strip_never_goes_past_the_horizon(self):
        definir_horizonte(5)

        limite = self.today + timedelta(days=4)

        self.assertTrue(all(data <= limite for data in self.strip_dates()))

    def test_strip_never_contains_past_days(self):
        datas = self.strip_dates()

        self.assertTrue(all(data >= self.today for data in datas))

    def test_strip_crosses_into_the_next_week(self):
        # Dias seguidos a partir de hoje, independentemente do dia da semana em
        # que hoje calha.
        definir_horizonte(10)

        datas = self.strip_dates()

        self.assertEqual(datas, [self.today + timedelta(days=i) for i in range(10)])

    def test_past_date_in_the_url_falls_back_to_today(self):
        passado = (self.today - timedelta(days=10)).isoformat()

        self.assertEqual(self.selected_date(f"?date={passado}"), self.today)
        self.assertEqual(self.strip_dates(f"?date={passado}")[0], self.today)

    def test_invalid_date_falls_back_to_today(self):
        self.assertEqual(self.selected_date("?date=nao-e-data"), self.today)

    def test_near_future_date_keeps_the_strip_anchored_on_today(self):
        # Escolher depois de amanhã não deve empurrar a faixa: o dia escolhido
        # já lá está.
        futuro = (self.today + timedelta(days=2)).isoformat()
        datas = self.strip_dates(f"?date={futuro}")

        self.assertEqual(datas[0], self.today)
        self.assertIn(self.today + timedelta(days=2), datas)

    def test_the_strip_stays_anchored_on_today_whatever_the_chosen_day(self):
        # Antes a faixa saltava com uma data distante e deixava de começar em
        # hoje: mudava de sítio debaixo de quem a estava a usar. Agora vem
        # inteira, e é o carrossel que anda.
        definir_horizonte(30)

        futuro = self.today + timedelta(days=20)
        datas = self.strip_dates(f"?date={futuro.isoformat()}")

        self.assertEqual(datas[0], self.today)
        self.assertIn(futuro, datas)

    def test_a_date_past_the_horizon_falls_back_to_the_last_bookable_day(self):
        # A seta pára no fim do horizonte; um endereço escrito à mão é a via
        # que sobra para pedir um dia que o site não aceita marcar.
        definir_horizonte(7)

        ultimo = self.today + timedelta(days=6)
        distante = (self.today + timedelta(days=90)).isoformat()

        self.assertEqual(self.selected_date(f"?date={distante}"), ultimo)
        self.assertEqual(self.strip_dates(f"?date={distante}")[-1], ultimo)

    def test_selected_day_is_marked(self):
        futuro = (self.today + timedelta(days=3)).isoformat()
        response = self.pagina(f"?date={futuro}")

        marcados = [
            day["date"] for day in response.context["week_days"] if day["is_selected"]
        ]

        self.assertEqual(len(marcados), 1)
        self.assertEqual(marcados[0].isoformat(), futuro)

    def test_the_strip_never_offers_a_past_day(self):
        # A proteção estava no `min` do campo de data, que era do browser e
        # saiu com o campo. Passou para onde já devia estar: o servidor, que
        # nunca constrói a faixa a começar antes de hoje.
        dias = self.strip_dates()

        self.assertEqual(dias[0], self.today)

    def test_a_past_date_in_the_url_falls_back_to_today(self):
        # Sem o `min` do browser, um endereço escrito à mão é a via que sobra.
        passado = (self.today - timedelta(days=5)).isoformat()

        self.assertEqual(self.selected_date(f"?date={passado}"), self.today)


class DayCarouselTests(TestCase):
    """As setas do carrossel e os limites que elas têm de respeitar.

    O carrossel corre sobre a janela de marcação inteira, e as duas pontas são
    as regras da agenda: hoje de um lado, o fim do horizonte do outro.
    """

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)
        self.hoje = timezone.localdate()

        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(18, 0),
            )

    def html(self, **params):
        params.setdefault("service", self.service.pk)

        return self.client.get(
            reverse("appointments:public_visual_schedule"), params
        ).content.decode()

    def test_the_strip_has_an_arrow_on_each_side(self):
        html = self.html()

        self.assertIn('data-week-arrow="prev"', html)
        self.assertIn('data-week-arrow="next"', html)

    def test_the_back_arrow_starts_disabled(self):
        # O primeiro cartão é hoje, e antes de hoje não há nada para onde ir:
        # a seta nasce desligada em vez de rolar para o vazio.
        html = self.html()

        recuar = re.search(
            r'<button[^>]*data-week-arrow="prev".*?</button>', html, re.S
        ).group(0)

        self.assertIn("disabled", recuar)

    def test_the_forward_arrow_starts_enabled(self):
        definir_horizonte(21)

        html = self.html()

        avancar = re.search(
            r'<button[^>]*data-week-arrow="next".*?</button>', html, re.S
        ).group(0)

        self.assertNotIn("disabled", avancar)

    def test_today_is_always_the_first_card(self):
        definir_horizonte(21)

        for query in [{}, {"date": (self.hoje + timedelta(days=10)).isoformat()}]:
            with self.subTest(endereco=query):
                html = self.html(**query)
                faixa = re.search(
                    r'<div class="app-week-strip".*?</div>', html, re.S
                ).group(0)
                datas = re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"', faixa)

                self.assertEqual(datas[0], self.hoje.isoformat())

    def test_the_carousel_ends_on_the_last_bookable_day(self):
        definir_horizonte(9)

        faixa = re.search(
            r'<div class="app-week-strip".*?</div>', self.html(), re.S
        ).group(0)
        datas = re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"', faixa)

        self.assertEqual(datas[-1], (self.hoje + timedelta(days=8)).isoformat())


class OnlyWorkingDaysAreOfferedTests(TestCase):
    """A faixa só mostra dias em que se trabalha.

    Um domingo fechado ou uma semana de férias não são uma escolha: ocupavam
    cartões a dizer que não há nada, e com a janela de marcação inteira à
    frente eram muitos de cada vez.
    """

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)
        self.hoje = timezone.localdate()

        definir_horizonte(21)

        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(18, 0),
            )

    def pagina(self, **params):
        params.setdefault("service", self.service.pk)

        return self.client.get(reverse("appointments:public_visual_schedule"), params)

    def faixa(self, **params):
        return [dia["date"] for dia in self.pagina(**params).context["week_days"]]

    def test_a_weekday_the_clinic_does_not_open_never_shows_up(self):
        fechado = (self.hoje + timedelta(days=3)).weekday()

        ensure_test_business_hour(weekday=fechado, is_active=False)

        for data in self.faixa():
            self.assertNotEqual(data.weekday(), fechado)

    def test_a_day_closed_by_a_full_day_block_never_shows_up(self):
        ferias = self.hoje + timedelta(days=5)

        ScheduleBlock.objects.create(
            notes="Férias",
            block_type=ScheduleBlock.BLOCK_TYPE_VACATION,
            date=ferias,
            is_full_day=True,
            is_active=True,
        )

        self.assertNotIn(ferias, self.faixa())

    def test_a_working_day_with_no_free_slots_stays(self):
        # Cheio não é fechado: trabalha-se nele, e uma desmarcação pode abri-lo
        # a qualquer momento. Tirá-lo escondia um dia que existe.
        cheio = self.hoje + timedelta(days=2)

        ScheduleBlock.objects.create(
            notes="Formação",
            block_type=ScheduleBlock.BLOCK_TYPE_OTHER,
            date=cheio,
            start_time=time(8, 0),
            end_time=time(17, 30),
            is_active=True,
        )

        dias = {dia["date"]: dia for dia in self.pagina().context["week_days"]}

        self.assertIn(cheio, dias)
        self.assertEqual(dias[cheio]["free_slots"], 0)

    def test_the_first_card_is_the_first_working_day(self):
        # Hoje é o primeiro cartão enquanto hoje for dia de trabalho. Num dia
        # fechado, o primeiro é o dia de trabalho seguinte — e nunca um dia já
        # passado.
        ensure_test_business_hour(weekday=self.hoje.weekday(), is_active=False)

        faixa = self.faixa()

        self.assertNotIn(self.hoje, faixa)
        self.assertEqual(faixa[0], self.hoje + timedelta(days=1))

    def test_the_page_speaks_of_the_first_card_and_not_of_a_closed_today(self):
        # O rótulo do estado dizia "dia sem atendimento" por cima de uma faixa
        # cheia de dias com vagas, porque continuava preso a hoje.
        ensure_test_business_hour(weekday=self.hoje.weekday(), is_active=False)

        resposta = self.pagina()

        self.assertEqual(
            resposta.context["selected_date"],
            resposta.context["week_days"][0]["date"],
        )

    def test_a_chosen_day_still_wins_over_the_first_card(self):
        escolhido = self.hoje + timedelta(days=4)

        resposta = self.pagina(date=escolhido.isoformat())

        self.assertEqual(resposta.context["selected_date"], escolhido)

    def test_without_a_single_working_day_the_page_says_so(self):
        # Férias a cobrir o horizonte inteiro: não há faixa nenhuma acima para
        # onde mandar a cliente, e a página tem de o dizer em vez de a mandar
        # escolher um dia que não existe.
        BusinessHour.objects.update(is_active=False)

        resposta = self.pagina()
        html = resposta.content.decode()

        self.assertEqual(resposta.context["week_days"], [])
        self.assertIn("Sem dias de atendimento", html)
        self.assertNotIn("Escolha um dia acima", html)
