"""Lembretes das marcações, e o comando que corre de meia em meia hora.

Quem se esquece não avisa, e uma vaga perdida por esquecimento perde-se duas
vezes. O lembrete existe sobretudo para dar tempo de desmarcar.
"""

from datetime import datetime, time, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from appointments import reminder_services
from appointments.models import Appointment, AppointmentReminderLog, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from notifications.models import MessagingSetting


class ReminderBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@exemplo.pt",
            phone="+351910000000",
        )

        self.service = create_test_service(duration_minutes=60)

        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(20, 0),
            )

    def daqui_a(self, **delta):
        """Uma marcação que começa daqui a tanto tempo.

        Marcada como encaixe: consoante a hora a que os testes correrem, a
        marcação pode cair de madrugada, e o horário de funcionamento não é o
        que está a ser testado aqui.
        """

        quando = timezone.localtime() + timedelta(**delta)

        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=quando.date(),
            start_time=quando.time().replace(second=0, microsecond=0),
            created_by=self.user,
            status=Appointment.STATUS_CONFIRMED,
            outside_schedule=True,
        )

    def correr(self, **opcoes):
        saida = StringIO()
        call_command("send_appointment_reminders", stdout=saida, stderr=saida, **opcoes)

        return saida.getvalue()


class WhenAReminderIsDueTests(ReminderBase):
    def test_the_hours_come_from_the_settings(self):
        definicao = MessagingSetting.load()
        definicao.reminder_hours_before = 6
        definicao.save()

        self.assertEqual(MessagingSetting.reminder_hours(), 6)

    def test_zero_hours_sends_nothing(self):
        definicao = MessagingSetting.load()
        definicao.reminder_hours_before = 0
        definicao.save()

        self.daqui_a(hours=2)

        saida = self.correr()

        self.assertEqual(mail.outbox, [])
        self.assertIn("desligados", saida)

    def test_an_appointment_at_the_right_distance_is_reminded(self):
        self.daqui_a(hours=23, minutes=30)

        self.correr()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("maria@exemplo.pt", mail.outbox[0].to)

    def test_one_too_far_away_is_not(self):
        self.daqui_a(hours=48)

        self.correr()

        self.assertEqual(mail.outbox, [])

    def test_one_booked_inside_the_window_is_not_reminded_right_away(self):
        # Marcada hoje para amanhã de manhã, com antecedência de 24 horas: o
        # momento do lembrete já passou há muito, e um lembrete a seguir à
        # confirmação lia-se como a mesma mensagem duas vezes.
        self.daqui_a(hours=12)

        self.correr()

        self.assertEqual(mail.outbox, [])

    def test_a_missed_run_is_caught_on_the_next_one(self):
        # O comando pode ter falhado passagens: a tolerância apanha-as.
        self.daqui_a(hours=22)

        self.correr()

        self.assertEqual(len(mail.outbox), 1)

    def test_an_appointment_that_already_started_is_left_alone(self):
        self.daqui_a(hours=-1)

        self.correr()

        self.assertEqual(mail.outbox, [])

    def test_a_cancelled_appointment_is_not_reminded(self):
        marcacao = self.daqui_a(hours=23)
        marcacao.status = Appointment.STATUS_CANCELLED
        marcacao.save(update_fields=["status"])

        self.correr()

        self.assertEqual(mail.outbox, [])


class TheReminderIsNotRepeatedTests(ReminderBase):
    def test_running_twice_sends_once(self):
        # Corre de meia em meia hora: repetir seria mandar quarenta e oito.
        self.daqui_a(hours=23)

        self.correr()
        self.correr()

        self.assertEqual(len(mail.outbox), 1)

    def test_the_send_is_recorded(self):
        marcacao = self.daqui_a(hours=23)

        self.correr()

        registo = AppointmentReminderLog.objects.get(appointment=marcacao)

        self.assertEqual(registo.reminder_type, "reminder_24h")
        self.assertEqual(registo.status, AppointmentReminderLog.STATUS_SUCCESS)

    def test_changing_the_antecedence_is_a_different_reminder(self):
        # Quem já recebeu o de 24 horas pode receber o de 2 sem que o registo
        # os confunda.
        marcacao = self.daqui_a(hours=23)

        self.correr()
        self.assertEqual(len(mail.outbox), 1)

        AppointmentReminderLog.objects.filter(appointment=marcacao).update(
            reminder_type="reminder_2h"
        )

        self.correr()

        self.assertEqual(len(mail.outbox), 2)

    def test_the_dry_run_sends_nothing_and_records_nothing(self):
        self.daqui_a(hours=23)

        saida = self.correr(dry_run=True)

        self.assertEqual(mail.outbox, [])
        self.assertEqual(AppointmentReminderLog.objects.count(), 0)
        self.assertIn("simulação", saida)


class WhatTheReminderSaysTests(ReminderBase):
    def test_it_carries_the_day_the_time_and_the_way_out(self):
        marcacao = self.daqui_a(hours=23)

        self.correr()

        corpo = mail.outbox[0].body

        self.assertIn(marcacao.start_time.strftime("%H:%M"), corpo)
        self.assertIn(marcacao.reference_code, corpo)

    def test_a_home_visit_says_where_we_are_going(self):
        marcacao = self.daqui_a(hours=23)
        marcacao.is_home_visit = True
        marcacao.home_street = "Rua das Flores"
        marcacao.home_number = "12"
        marcacao.save()

        self.correr()

        self.assertIn("Rua das Flores 12", mail.outbox[0].body)

    def test_an_english_customer_is_reminded_in_english(self):
        marcacao = self.daqui_a(hours=23)
        marcacao.customer_speaks_english = True
        marcacao.save(update_fields=["customer_speaks_english"])

        self.correr()

        self.assertIn("Reminder", mail.outbox[0].subject)


class TheDailyCommandTests(TestCase):
    """Os dois comandos diários passaram a um só."""

    def test_it_runs_both(self):
        saida = StringIO()

        call_command("send_daily_messages", stdout=saida, stderr=saida)

        texto = saida.getvalue()

        self.assertIn("Seguimentos", texto)
        self.assertIn("Avisos de retorno", texto)
        self.assertIn("concluídas", texto)

    def test_the_dry_run_reaches_both(self):
        saida = StringIO()

        call_command("send_daily_messages", dry_run=True, stdout=saida, stderr=saida)

        self.assertIn("Avisos de retorno", saida.getvalue())

    def test_the_reminders_are_not_part_of_it(self):
        # Correm de meia em meia hora: uma antecedência de duas horas não se
        # cumpre com um comando que passa uma vez por dia.
        from notifications.management.commands import send_daily_messages

        comandos = [nome for nome, _titulo in send_daily_messages.COMANDOS]

        self.assertNotIn("send_appointment_reminders", comandos)


class ReminderWindowTests(TestCase):
    """A janela, sem passar pelo comando."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@exemplo.pt",
            phone="+351910000000",
        )

        self.service = create_test_service(duration_minutes=60)

        ensure_test_business_hour(
            weekday=(timezone.localdate() + timedelta(days=1)).weekday(),
            start_time=time(8, 0),
            end_time=time(20, 0),
        )

    def marcacao_em(self, quando):
        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=quando.date(),
            start_time=quando.time(),
            created_by=self.user,
            status=Appointment.STATUS_CONFIRMED,
            outside_schedule=True,
        )

    def test_zero_hours_is_an_empty_window(self):
        self.assertEqual(list(reminder_services.due(0)), [])

    def test_the_log_key_carries_the_hours(self):
        self.assertEqual(reminder_services.log_key(24), "reminder_24h")
        self.assertEqual(reminder_services.log_key(2), "reminder_2h")

    def test_the_window_holds_what_is_due(self):
        agora = timezone.localtime()
        amanha = agora + timedelta(hours=23)
        marcacao = self.marcacao_em(
            datetime.combine(amanha.date(), amanha.time().replace(second=0))
        )

        self.assertIn(marcacao, reminder_services.due(24))
