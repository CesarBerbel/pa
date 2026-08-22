from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from appointments.models import (
    Appointment,
    BusinessHour,
    Customer,
    ScheduleBlock,
    SchedulingSetting,
)
from appointments.tests.factories import create_test_service
from appointments.weekly_schedule import build_week, day_agenda, week_start


class WeekStartTests(TestCase):
    def test_the_week_starts_on_monday(self):
        # Segunda e não domingo: é como o calendário é lido em Portugal.
        quarta = date(2026, 8, 19)

        self.assertEqual(week_start(quarta), date(2026, 8, 17))

    def test_a_monday_is_its_own_start(self):
        segunda = date(2026, 8, 17)

        self.assertEqual(week_start(segunda), segunda)

    def test_a_sunday_belongs_to_the_week_that_started_before_it(self):
        domingo = date(2026, 8, 23)

        self.assertEqual(week_start(domingo), date(2026, 8, 17))


class WeeklyGridTests(TestCase):
    """Onde cada coisa cai na grelha.

    Uma marcação mal colocada aqui é uma marcação que se lê à hora errada, e a
    agenda é lida de relance — ninguém confere.
    """

    def setUp(self):
        ScheduleBlock.objects.all().delete()

        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            phone="+351910000000",
        )

        self.service = create_test_service(duration_minutes=60)

        for weekday in range(5):
            BusinessHour.objects.update_or_create(
                weekday=weekday,
                defaults={
                    "start_time": time(9, 0),
                    "end_time": time(18, 0),
                    "is_active": True,
                },
            )

        BusinessHour.objects.filter(weekday__in=[5, 6]).update(is_active=False)

        hoje = timezone.localdate()
        self.segunda = hoje - timedelta(days=hoje.weekday())

    def marcar(self, dias=0, hora=10, minuto=0, **extra):
        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.segunda + timedelta(days=dias),
            start_time=time(hora, minuto),
            created_by=self.user,
            **extra,
        )

    def dia(self, semana, indice):
        return semana.days[indice]

    def test_the_week_has_seven_days_starting_on_monday(self):
        semana = build_week(self.segunda + timedelta(days=3))

        self.assertEqual(len(semana.days), 7)
        self.assertEqual(semana.days[0].date, self.segunda)
        self.assertEqual(semana.days[6].date, self.segunda + timedelta(days=6))

    def test_the_rows_cover_the_business_hours(self):
        semana = build_week(self.segunda)

        # 09:00 às 18:00, de meia em meia hora.
        self.assertEqual(semana.first_slot, time(9, 0))
        self.assertEqual(semana.rows, 18)

    def test_an_appointment_lands_on_its_own_hour(self):
        self.marcar(dias=0, hora=10)

        evento = self.dia(build_week(self.segunda), 0).events[0]

        # 09:00 é a linha 1; 10:00 é a terceira meia hora.
        self.assertEqual(evento["row"], 3)
        self.assertEqual(evento["span"], 2)

    def test_a_longer_service_takes_more_rows(self):
        longo = create_test_service(duration_minutes=120, name="Serviço longo")
        Appointment.objects.create(
            customer=self.customer,
            service=longo,
            date=self.segunda,
            start_time=time(9, 0),
            created_by=self.user,
        )

        evento = self.dia(build_week(self.segunda), 0).events[0]

        self.assertEqual(evento["span"], 4)

    def test_a_service_shorter_than_a_slot_still_has_height(self):
        # Com altura zero desaparecia da grelha sem deixar de existir.
        curto = create_test_service(duration_minutes=15, name="Serviço curto")
        Appointment.objects.create(
            customer=self.customer,
            service=curto,
            date=self.segunda,
            start_time=time(9, 0),
            created_by=self.user,
        )

        self.assertEqual(self.dia(build_week(self.segunda), 0).events[0]["span"], 1)

    def test_a_cancelled_appointment_does_not_take_up_the_grid(self):
        self.marcar(hora=10, status=Appointment.STATUS_CANCELLED)

        self.assertEqual(self.dia(build_week(self.segunda), 0).events, [])

    def test_a_block_shows_up_as_its_own_band(self):
        ScheduleBlock.objects.create(
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=self.segunda,
            start_time=time(13, 0),
            end_time=time(14, 0),
            notes="Almoço",
        )

        evento = self.dia(build_week(self.segunda), 0).events[0]

        self.assertEqual(evento["kind"], "block")
        self.assertEqual(evento["row"], 9)
        self.assertEqual(evento["span"], 2)

    def test_a_closed_day_is_marked_as_such(self):
        semana = build_week(self.segunda)

        self.assertTrue(semana.days[0].is_open)
        self.assertFalse(semana.days[5].is_open)

    def test_the_grid_stretches_to_fit_an_appointment_outside_hours(self):
        # Um encaixe às 20:00 num dia que fecha às 18:00. Não alargar a grelha
        # era esconder uma marcação que existe — e um encaixe é precisamente
        # uma marcação posta fora do horário de propósito.
        self.marcar(hora=20, outside_schedule=True)

        semana = build_week(self.segunda)

        self.assertGreater(semana.rows, 18)
        self.assertTrue(self.dia(semana, 0).events)

    def test_a_week_without_business_hours_still_draws_a_grid(self):
        BusinessHour.objects.update(is_active=False)

        semana = build_week(self.segunda)

        self.assertEqual(semana.first_slot, time(8, 0))
        self.assertEqual(semana.rows, 24)

    def test_today_is_marked(self):
        semana = build_week(timezone.localdate())

        marcados = [dia.date for dia in semana.days if dia.is_today]

        self.assertEqual(marcados, [timezone.localdate()])

    def test_the_whole_week_costs_a_handful_of_queries(self):
        # Sem o lote de leitura seriam três consultas por dia. Uma agenda que
        # se folheia semana a semana paga isso a cada clique.
        for indice in range(5):
            self.marcar(dias=indice, hora=9 + indice)

        with CaptureQueriesContext(connection) as consultas:
            build_week(self.segunda)

        self.assertLessEqual(len(consultas), 6, [c["sql"][:80] for c in consultas])


class MobileDayAgendaTests(WeeklyGridTests):
    """O mesmo dia, em lista, para quem o lê num telemóvel.

    A grelha da semana não cabe num ecrã de telemóvel — nem esticada, nem
    encolhida. O que muda é a forma, não a informação: sai da mesma semana já
    lida, sem uma consulta a mais.
    """

    def linhas(self, dias=0):
        semana = build_week(self.segunda)

        return day_agenda(semana.days[dias])

    def horas(self, dias=0):
        return [linha["cell"].time.strftime("%H:%M") for linha in self.linhas(dias)]

    def test_an_appointment_is_one_row_and_not_one_per_slot(self):
        # Uma consulta de uma hora numa grelha de 15 minutos são quatro linhas
        # na grelha. Em lista, repetir o nome quatro vezes seria ilegível.
        definicao = SchedulingSetting.load()
        definicao.slot_minutes = 15
        definicao.save()

        self.marcar(hora=10)

        marcacoes = [
            linha
            for linha in self.linhas()
            if linha["event"] and linha["event"]["kind"] == "appointment"
        ]

        self.assertEqual(len(marcacoes), 1)
        self.assertEqual(marcacoes[0]["cell"].time, time(10, 0))

    def test_the_hours_covered_by_an_appointment_do_not_come_back_as_free(self):
        self.marcar(hora=10)

        livres = [
            linha["cell"].time.strftime("%H:%M")
            for linha in self.linhas()
            if not linha["event"] and linha["cell"].is_free
        ]

        self.assertNotIn("10:00", livres)
        self.assertNotIn("10:30", livres)

    def test_hours_outside_the_working_day_are_left_out(self):
        # Numa lista vertical, uma hora fechada e vazia é ecrã gasto a dizer
        # nada. Na grelha ela desenha a coluna; aqui não desenha coisa nenhuma.
        horas = self.horas()

        self.assertNotIn("08:00", horas)
        self.assertNotIn("19:00", horas)

    def test_a_closed_day_with_an_encaixe_still_shows_it(self):
        # O dia está fechado, mas há lá uma marcação posta de propósito. Não a
        # mostrar era escondê-la de quem a pôs.
        self.marcar(dias=5, hora=10, outside_schedule=True)

        marcacoes = [linha for linha in self.linhas(dias=5) if linha["event"]]

        self.assertEqual(len(marcacoes), 1)

    def test_a_block_keeps_its_place(self):
        ScheduleBlock.objects.create(
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=self.segunda,
            start_time=time(13, 0),
            end_time=time(14, 0),
            notes="Almoço",
        )

        bloqueios = [
            linha
            for linha in self.linhas()
            if linha["event"] and linha["event"]["kind"] == "block"
        ]

        self.assertEqual(len(bloqueios), 1)
        self.assertEqual(bloqueios[0]["cell"].time, time(13, 0))


class WeeklyScheduleViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva", phone="+351910000000"
        )
        self.service = create_test_service(duration_minutes=60)

        for weekday in range(7):
            BusinessHour.objects.update_or_create(
                weekday=weekday,
                defaults={
                    "start_time": time(9, 0),
                    "end_time": time(18, 0),
                    "is_active": True,
                },
            )

        hoje = timezone.localdate()
        self.segunda = hoje - timedelta(days=hoje.weekday())

        self.client.force_login(self.user)
        self.url = reverse("appointments:weekly_schedule")

    def test_it_is_closed_to_who_is_not_from_the_internal_area(self):
        self.client.logout()

        self.assertNotEqual(self.client.get(self.url).status_code, 200)

    def test_it_opens_on_the_current_week(self):
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["week_start"], self.segunda)

    def test_it_walks_to_another_week(self):
        outra = self.segunda + timedelta(days=21)

        resposta = self.client.get(self.url, {"date": outra.isoformat()})

        self.assertEqual(resposta.context["week_start"], outra)

    def test_a_broken_date_falls_back_to_today(self):
        resposta = self.client.get(self.url, {"date": "não é uma data"})

        self.assertEqual(resposta.context["week_start"], self.segunda)

    def test_an_appointment_links_to_its_own_screen(self):
        marcacao = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.segunda,
            start_time=time(10, 0),
            created_by=self.user,
        )

        html = self.client.get(self.url).content.decode()

        self.assertIn(
            reverse("appointments:appointment_detail", args=[marcacao.pk]), html
        )
        self.assertIn("Maria Silva", html)

    def test_each_day_opens_the_day_view(self):
        html = self.client.get(self.url).content.decode()

        self.assertIn(
            f"{reverse('appointments:visual_schedule')}?date={self.segunda:%Y-%m-%d}",
            html,
        )

    def test_each_day_has_a_column_of_its_own(self):
        """A coluna de fundo carrega o estado do dia e o encaixe do deslize.

        No telemóvel é ela que faz o deslize parar em cima de um dia em vez de
        a meio dele. Sem coluna, cada célula era um alvo de encaixe.
        """

        html = self.client.get(self.url).content.decode()

        self.assertEqual(html.count('class="week-column'), 7)

    def test_today_and_closed_days_are_marked_on_the_column(self):
        BusinessHour.objects.filter(weekday=6).update(is_active=False)

        html = self.client.get(self.url).content.decode()

        self.assertIn("week-column is-today", html)
        self.assertIn("is-closed", html)

    def test_the_corner_sits_above_both_sticky_edges(self):
        # O canto é o único sítio onde o cabeçalho e a coluna das horas se
        # cruzam; sem elemento próprio viam-se um por baixo do outro.
        html = self.client.get(self.url).content.decode()

        self.assertIn('class="week-corner"', html)

    def test_the_phone_gets_the_day_and_the_wide_screen_the_week(self):
        # Uma página só, duas formas: sem depender de adivinhar o telemóvel
        # pelo cabeçalho do pedido, que falha e não sobrevive a rodar o ecrã.
        html = self.client.get(self.url).content.decode()

        self.assertIn('class="week-grid-scroll d-none d-md-block"', html)
        self.assertIn('<div class="d-md-none">', html)

    def test_the_day_strip_switches_days_without_leaving_the_page(self):
        html = self.client.get(self.url).content.decode()

        self.assertEqual(html.count('class="day-strip-item'), 7)
        self.assertIn(f"{self.url}?date={self.segunda:%Y-%m-%d}", html)

    def test_the_day_shown_follows_the_date_asked_for(self):
        quarta = self.segunda + timedelta(days=2)

        resposta = self.client.get(self.url, {"date": quarta.isoformat()})

        self.assertEqual(resposta.context["selected_day"].date, quarta)

    def test_a_free_hour_in_the_list_opens_a_new_appointment(self):
        html = self.client.get(self.url).content.decode()

        endereco = (
            f"{reverse('appointments:appointment_create')}"
            f"?date={self.segunda:%Y-%m-%d}&start_time=09:00"
        )

        self.assertIn(endereco, html)

    def test_the_agenda_in_the_menu_is_the_weekly_one(self):
        html = self.client.get(self.url).content.decode()
        navegacao = html.split("<nav", 1)[1].split("</nav>", 1)[0]

        self.assertIn(reverse("appointments:weekly_schedule"), navegacao)
