"""A vista de mês da agenda interna, e a faixa de controlo partilhada."""

from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, Customer, ScheduleBlock, Service
from appointments.tests.factories import ensure_test_business_hour
from appointments.monthly_schedule import MAX_POR_DIA, build_month


class MonthGridTests(TestCase):
    """O que a grelha do mês mostra em cada dia."""

    def setUp(self):
        User = get_user_model()
        self.profissional = User.objects.create_superuser(
            email="admin@test.com", password="x", full_name="Admin"
        )
        self.servico = Service.objects.create(
            name="Pedicure", duration_minutes=60, price="30.00", is_active=True
        )
        self.hoje = timezone.localdate()

    def cliente(self, nome):
        return Customer.objects.create(
            full_name=nome, email=f"{nome}@t.com", phone="+351911111111"
        )

    def marcar(self, dia, hora, nome, status=None):
        return Appointment.objects.create(
            customer=self.cliente(nome),
            service=self.servico,
            date=dia,
            start_time=time(hora, 0),
            status=status or Appointment.STATUS_CONFIRMED,
            created_by=self.profissional,
        )

    def dia_da_grelha(self, mes, alvo):
        for semana in mes.weeks:
            for dia in semana:
                if dia.date == alvo:
                    return dia

        raise AssertionError(f"{alvo} não está na grelha")

    def test_the_grid_covers_whole_weeks(self):
        # Uma grelha com buracos nos cantos lê-se pior do que uma cheia.
        mes = build_month(date(2026, 8, 15))

        for semana in mes.weeks:
            self.assertEqual(len(semana), 7)

        self.assertEqual(mes.weeks[0][0].date.weekday(), 0)
        self.assertEqual(mes.weeks[-1][-1].date.weekday(), 6)

    def test_days_from_the_neighbouring_months_are_marked(self):
        mes = build_month(date(2026, 8, 15))
        fora = [
            dia
            for semana in mes.weeks
            for dia in semana
            if dia.date.month != 8
        ]

        self.assertTrue(fora)

        for dia in fora:
            self.assertFalse(dia.in_month)

    def test_a_day_shows_who_is_coming(self):
        alvo = self.hoje.replace(day=15)
        self.marcar(alvo, 10, "Ana")
        self.marcar(alvo, 11, "Berta")

        dia = self.dia_da_grelha(build_month(alvo), alvo)

        self.assertEqual([e.name for e in dia.entries], ["Ana", "Berta"])
        self.assertEqual([e.time for e in dia.entries], ["10:00", "11:00"])

    def test_the_names_come_in_time_order(self):
        alvo = self.hoje.replace(day=15)
        self.marcar(alvo, 16, "Tarde")
        self.marcar(alvo, 9, "Manhã")

        dia = self.dia_da_grelha(build_month(alvo), alvo)

        self.assertEqual([e.name for e in dia.entries], ["Manhã", "Tarde"])

    def test_a_full_day_only_shows_the_first_names(self):
        # Uma célula de um sétimo da largura não leva doze nomes.
        alvo = self.hoje.replace(day=15)

        # O dia tem de estar aberto o suficiente para caber tudo isto: o
        # horário semeado pelas migrações não chega para cinco marcações
        # seguidas, e a marcação recusa-se a sair dele.
        ensure_test_business_hour(
            weekday=alvo.weekday(), start_time=time(8, 0), end_time=time(20, 0)
        )

        for indice in range(MAX_POR_DIA + 2):
            self.marcar(alvo, 8 + indice, f"Cliente {indice}")

        dia = self.dia_da_grelha(build_month(alvo), alvo)

        self.assertEqual(len(dia.visible_entries), MAX_POR_DIA)
        self.assertEqual(dia.hidden_count, 2)

    def test_a_cancelled_appointment_is_still_shown(self):
        # O mês mostra o que aconteceu, e não só o que ficou de pé.
        alvo = self.hoje.replace(day=15)
        self.marcar(alvo, 10, "Ana", status=Appointment.STATUS_CANCELLED)

        dia = self.dia_da_grelha(build_month(alvo), alvo)

        self.assertTrue(dia.entries[0].is_cancelled)

    def test_a_day_closed_by_a_block_is_marked(self):
        alvo = self.hoje + timedelta(days=2)

        ScheduleBlock.objects.create(
            date=alvo,
            is_full_day=True,
            is_active=True,
            block_type=ScheduleBlock.objects.model._meta.get_field(
                "block_type"
            ).default,
        )

        dia = self.dia_da_grelha(build_month(alvo), alvo)

        self.assertTrue(dia.is_blocked)

    def test_today_is_marked(self):
        dia = self.dia_da_grelha(build_month(self.hoje), self.hoje)

        self.assertTrue(dia.is_today)


class MonthPageTests(TestCase):
    """A página, e a faixa que liga as três vistas."""

    def setUp(self):
        User = get_user_model()
        User.objects.create_superuser(
            email="admin@test.com", password="x", full_name="Admin"
        )
        self.client.login(email="admin@test.com", password="x")

    def test_the_page_answers(self):
        self.assertEqual(
            self.client.get(reverse("appointments:monthly_schedule")).status_code, 200
        )

    def test_the_three_views_link_to_each_other(self):
        for vista in [
            "appointments:visual_schedule",
            "appointments:weekly_schedule",
            "appointments:monthly_schedule",
        ]:
            html = self.client.get(reverse(vista)).content.decode()

            with self.subTest(vista=vista):
                for destino in [
                    "appointments:visual_schedule",
                    "appointments:weekly_schedule",
                    "appointments:monthly_schedule",
                ]:
                    self.assertIn(reverse(destino), html)

    def test_the_current_view_is_marked(self):
        html = self.client.get(
            reverse("appointments:monthly_schedule")
        ).content.decode()

        self.assertIn('class="agenda-view is-active"', html)
        self.assertIn('aria-current="page"', html)

    def test_the_day_page_no_longer_repeats_what_it_already_does(self):
        # Cada horário livre já tem "+ Marcar", e as caixas de seleção já
        # bloqueiam: os dois botões do cabeçalho eram um segundo caminho para
        # o mesmo, mais longe do sítio onde a decisão é tomada.
        html = self.client.get(
            reverse("appointments:visual_schedule")
        ).content.decode()

        self.assertNotIn("Bloquear horário", html)
        self.assertNotIn("Nova marcação", html)
        self.assertIn("slot-blocking-form", html)

    def test_moving_between_months_keeps_working(self):
        html = self.client.get(
            reverse("appointments:monthly_schedule"), {"date": "2026-08-15"}
        ).content.decode()

        self.assertIn("2026-07-01", html)
        self.assertIn("2026-09-01", html)

    def test_a_broken_date_falls_back_to_today(self):
        response = self.client.get(
            reverse("appointments:monthly_schedule"), {"date": "isto-não-é-uma-data"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_date"], timezone.localdate())
