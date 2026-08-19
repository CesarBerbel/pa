from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, BusinessHour, Customer
from appointments.tests.factories import create_test_service


class DashboardPendingConfirmationsTests(TestCase):
    """O painel de marcações por confirmar.

    É a pendência que custa dinheiro: um pedido feito no site fica reservado
    mas ninguém o viu ainda deste lado. O painel existe para se agir sobre ele
    sem sair do sítio.
    """

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.service = create_test_service()
        self.today = timezone.localdate()

        for weekday in range(7):
            BusinessHour.objects.update_or_create(
                weekday=weekday,
                defaults={
                    "start_time": time(8, 0),
                    "end_time": time(20, 0),
                    "is_active": True,
                },
            )

        self.client.force_login(self.user)
        self.url = reverse("dashboard")

    def marcacao(self, dias=1, status=Appointment.STATUS_SCHEDULED, hora=10):
        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.today + timedelta(days=dias),
            start_time=time(hora, 0),
            status=status,
            created_by=self.user,
            origin=Appointment.ORIGIN_PUBLIC,
        )

    def test_a_pending_appointment_shows_up_with_a_confirm_button(self):
        marcacao = self.marcacao()

        resposta = self.client.get(self.url)
        html = resposta.content.decode()

        self.assertIn(marcacao.customer.full_name, html)
        self.assertIn(
            reverse("appointments:appointment_confirm", args=[marcacao.pk]), html
        )
        self.assertEqual(resposta.context["pending_confirmations_total"], 1)

    def test_confirmed_appointments_are_not_pending(self):
        self.marcacao(status=Appointment.STATUS_CONFIRMED)

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.context["pending_confirmations_total"], 0)
        self.assertContains(resposta, "Nenhuma marcação por confirmar")

    def test_a_pending_appointment_in_the_past_is_left_out(self):
        # Já não se confirma: o que se faz a essa é cancelá-la. Pô-la ao lado
        # do botão de confirmar prometia uma ação que não resolve nada.
        self.marcacao(dias=-3)

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.context["pending_confirmations_total"], 0)

    def test_the_list_is_capped_and_says_so(self):
        for indice in range(10):
            self.marcacao(dias=indice + 1, hora=9 + (indice % 8))

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.context["pending_confirmations_total"], 10)
        self.assertEqual(len(resposta.context["pending_confirmations"]), 8)
        self.assertContains(resposta, "Mostradas 8 de")

    def test_the_soonest_come_first(self):
        longe = self.marcacao(dias=20)
        perto = self.marcacao(dias=2)

        listadas = list(self.client.get(self.url).context["pending_confirmations"])

        self.assertEqual([m.pk for m in listadas], [perto.pk, longe.pk])

    def test_confirming_from_the_panel_asks_before_notifying(self):
        marcacao = self.marcacao()

        html = self.client.get(self.url).content.decode()

        self.assertIn("sendMessageChoiceModal", html)
        self.assertIn('name="send_message"', html)
        self.assertIn(marcacao.customer.full_name, html)

    def test_confirming_without_notifying_keeps_the_customer_quiet(self):
        marcacao = self.marcacao()

        with patch("appointments.use_cases.notify_whatsapp"):
            with self.captureOnCommitCallbacks(execute=True):
                resposta = self.client.post(
                    reverse("appointments:appointment_confirm", args=[marcacao.pk]),
                    {"send_message": "0", "next": self.url},
                )

        marcacao.refresh_from_db()

        self.assertEqual(marcacao.status, Appointment.STATUS_CONFIRMED)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(resposta.headers["Location"], self.url)

    def test_confirming_and_notifying_sends_the_confirmation(self):
        marcacao = self.marcacao()

        with patch("appointments.use_cases.notify_whatsapp"):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    reverse("appointments:appointment_confirm", args=[marcacao.pk]),
                    {"send_message": "1", "next": self.url},
                )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("maria@example.com", mail.outbox[0].to)

    def test_a_next_pointing_outside_the_site_is_ignored(self):
        # Sem esta guarda, o botão de confirmar servia para levar quem clica a
        # uma página que imita esta.
        marcacao = self.marcacao()

        with patch("appointments.use_cases.notify_whatsapp"):
            with self.captureOnCommitCallbacks(execute=True):
                resposta = self.client.post(
                    reverse("appointments:appointment_confirm", args=[marcacao.pk]),
                    {"send_message": "0", "next": "https://exemplo-malicioso.pt/"},
                )

        self.assertEqual(
            resposta.headers["Location"], reverse("appointments:appointment_list")
        )

    def test_the_removed_shortcuts_are_gone(self):
        # Só os atalhos do painel. As duas páginas continuam a existir e a ser
        # alcançáveis pelo menu de configurações — o que saiu daqui foi o
        # destaque, não o caminho.
        html = self.client.get(self.url).content.decode()
        painel = html.split('<section class="internal-dashboard">', 1)[1].split(
            "</section>", 1
        )[0]

        self.assertNotIn("Horas trabalhadas", painel)
        self.assertNotIn("Catálogo", painel)

        self.assertIn("/horas-trabalhadas/", html)
        self.assertIn("/servicos/", html)
