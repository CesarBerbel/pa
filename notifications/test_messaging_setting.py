"""O interruptor geral de mensagens.

Com ele desligado não pode sair nada: nem email, nem WhatsApp, nem envios
manuais, nem testes de configuração. O valor de um interruptor destes está em
não haver exceções — é por isso que cada caminho de saída tem aqui o seu teste,
incluindo os que não passam pelo despacho normal.
"""

from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.emails import send_rendered_email
from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from notifications import whatsapp_dispatch
from notifications.models import MessagingSetting, WhatsAppEventSetting


class MessagingSettingModelTests(TestCase):
    def test_messaging_is_enabled_by_default(self):
        self.assertTrue(MessagingSetting.messaging_enabled())

    def test_only_one_row_ever_exists(self):
        MessagingSetting.load()

        outra = MessagingSetting(is_enabled=False)
        outra.save()

        self.assertEqual(MessagingSetting.objects.count(), 1)
        self.assertFalse(MessagingSetting.load().is_enabled)

    def test_a_database_failure_does_not_silence_messages(self):
        # Falhar a ler a definição não pode calar as mensagens: ninguém daria
        # por isso até uma cliente aparecer sem ter sido avisada.
        with patch.object(
            MessagingSetting, "load", side_effect=RuntimeError("sem base de dados")
        ):
            self.assertTrue(MessagingSetting.messaging_enabled())


class MessagingSettingEmailTests(TestCase):
    def enviar(self):
        send_rendered_email(
            subject="Assunto",
            body_text="Corpo",
            body_html="",
            recipient_list=["maria@example.com"],
        )

    def test_email_is_sent_while_messaging_is_on(self):
        self.enviar()

        self.assertEqual(len(mail.outbox), 1)

    def test_email_is_not_sent_while_messaging_is_off(self):
        definicao = MessagingSetting.load()
        definicao.is_enabled = False
        definicao.save()

        self.enviar()

        self.assertEqual(mail.outbox, [])


class MessagingSettingWhatsAppTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.service = create_test_service(duration_minutes=60)

        self.date = timezone.localdate() + timedelta(days=14)
        while self.date.weekday() != 0:
            self.date += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.date.weekday(),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        self.appointment = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(10, 0),
            created_by=self.user,
        )

        # As regras vêm criadas pelas migrações de seed: reaproveitar em vez de
        # inserir, que a combinação acontecimento/destinatário é única.
        self.setting, _ = WhatsAppEventSetting.objects.update_or_create(
            event_type=WhatsAppEventSetting.EVENT_APPOINTMENT_CONFIRMED,
            audience=WhatsAppEventSetting.AUDIENCE_CUSTOMER,
            defaults={
                "provider": WhatsAppEventSetting.PROVIDER_BAILEYS,
                "is_active": True,
                "body_template": "Olá",
            },
        )

        definicao = MessagingSetting.load()
        definicao.is_enabled = False
        definicao.save()

    def test_notify_sends_nothing_while_messaging_is_off(self):
        with patch.object(whatsapp_dispatch, "provider_module") as fornecedor:
            resultado = whatsapp_dispatch.notify(
                self.appointment,
                WhatsAppEventSetting.EVENT_APPOINTMENT_CONFIRMED,
            )

        fornecedor.assert_not_called()

        self.assertTrue(resultado.success)
        self.assertTrue(resultado.skipped)

    def test_manual_send_is_blocked_while_messaging_is_off(self):
        with patch.object(whatsapp_dispatch, "provider_module") as fornecedor:
            resultado = whatsapp_dispatch.send_manual(self.appointment, self.setting)

        fornecedor.assert_not_called()
        self.assertTrue(resultado.skipped)

    def test_test_send_is_blocked_while_messaging_is_off(self):
        with patch.object(whatsapp_dispatch, "provider_module") as fornecedor:
            resultado = whatsapp_dispatch.send_test(self.setting, "+351910000000")

        fornecedor.assert_not_called()
        self.assertTrue(resultado.skipped)

    def test_meta_cloud_api_is_blocked_while_messaging_is_off(self):
        # Este caminho não passa pelo despacho: é chamado à parte, ao confirmar
        # uma marcação, e tinha de ser travado no próprio serviço.
        from notifications.whatsapp import WhatsAppAppointmentNotificationService

        with patch("notifications.whatsapp.urlopen") as pedido:
            resultado = WhatsAppAppointmentNotificationService.send_confirmation(
                self.appointment
            )

        pedido.assert_not_called()
        self.assertTrue(resultado.skipped)

    def test_notify_sends_again_once_messaging_is_back_on(self):
        definicao = MessagingSetting.load()
        definicao.is_enabled = True
        definicao.save()

        # O fornecedor é forçado a ligado: o que está a ser medido é o
        # interruptor geral, não o TWILIO_ENABLED/BAILEYS_ENABLED do servidor
        # onde os testes correm.
        with patch.object(whatsapp_dispatch, "provider_enabled", return_value=True):
            with patch.object(whatsapp_dispatch, "provider_module") as fornecedor:
                fornecedor.return_value.validate_settings.return_value = ""
                whatsapp_dispatch.notify(
                    self.appointment,
                    WhatsAppEventSetting.EVENT_APPOINTMENT_CONFIRMED,
                )

        self.assertTrue(fornecedor.called)


class MessagingSettingViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.url = reverse("notifications:messaging_setting")

    def test_the_page_requires_internal_access(self):
        resposta = self.client.get(self.url)

        self.assertNotEqual(resposta.status_code, 200)

    def test_the_page_loads_for_internal_users(self):
        self.client.force_login(self.user)

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)

    def test_turning_it_off_records_who_did_it(self):
        self.client.force_login(self.user)

        self.client.post(self.url, {})

        definicao = MessagingSetting.load()

        self.assertFalse(definicao.is_enabled)
        self.assertEqual(definicao.updated_by, self.user)

    def test_turning_it_back_on(self):
        self.client.force_login(self.user)

        self.client.post(self.url, {})
        self.client.post(self.url, {"is_enabled": "on"})

        self.assertTrue(MessagingSetting.load().is_enabled)
