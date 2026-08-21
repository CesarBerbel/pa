from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from notifications.models import (
    EmailTemplate,
    MessagingSetting,
    ServiceFollowUp,
    WhatsAppEventSetting,
)


class MessagePreviewTests(TestCase):
    """A pré-visualização mostrada antes de decidir se a cliente é avisada.

    O que a torna útil é ser a mensagem verdadeira: sai das mesmas funções que
    o envio a sério, com a entrega desviada. Um texto escrito à parte para o
    ecrã mentiria à primeira vez que alguém editasse um modelo.
    """

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
            origin=Appointment.ORIGIN_PUBLIC,
        )

        self.client.force_login(self.user)
        self.url = reverse(
            "appointments:appointment_message_preview",
            kwargs={"pk": self.appointment.pk},
        )

    def previsualizar(self, acao, **extra):
        return self.client.post(self.url, {"acao": acao, **extra}).json()

    def test_it_shows_the_message_the_action_would_send(self):
        # A marcação ainda está agendada: sem pôr o estado que vai ter, saía a
        # mensagem de "pedido recebido" em vez da confirmação.
        previa = self.previsualizar("confirm")

        self.assertEqual(len(previa["emails"]), 1)
        self.assertIn("confirmada", previa["emails"][0]["subject"])
        self.assertIn("maria@exemplo.pt", previa["emails"][0]["to"])

    def test_it_sends_nothing(self):
        self.previsualizar("confirm")
        self.previsualizar("complete")
        self.previsualizar("cancel", cancellation_reason="Motivo qualquer.")

        self.assertEqual(mail.outbox, [])

    def test_it_does_not_touch_the_appointment(self):
        # O estado é forçado em memória para a mensagem sair certa; gravá-lo
        # seria confirmar a marcação só por alguém ter aberto a janela.
        self.previsualizar("confirm")

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.status, Appointment.STATUS_SCHEDULED)

    def test_the_cancellation_quotes_the_reason_being_typed(self):
        # O motivo ainda não está gravado: vem do formulário aberto.
        previa = self.previsualizar(
            "cancel", cancellation_reason="A profissional está doente."
        )

        para_cliente = next(
            email for email in previa["emails"] if "maria@exemplo.pt" in email["to"]
        )

        self.assertIn("A profissional está doente", para_cliente["body"])

    def test_the_cancellation_shows_the_internal_notice_too(self):
        # Quem cancela vê tudo o que a ação faz sair, e não só o lado da cliente.
        previa = self.previsualizar("cancel", cancellation_reason="Motivo qualquer.")

        self.assertEqual(len(previa["emails"]), 2)

    def test_a_service_with_its_own_message_is_the_one_shown(self):
        modelo = EmailTemplate.objects.create(
            key="cuidados_teste",
            name="Cuidados",
            subject="Cuidados a ter nos próximos dias",
            body_text="Olá {{ customer_name }}, evite calçado apertado.",
            is_active=True,
        )
        ServiceFollowUp.objects.create(
            service=self.service,
            email_template=modelo,
            trigger=ServiceFollowUp.TRIGGER_COMPLETION,
            days_after=0,
        )

        previa = self.previsualizar("complete")

        self.assertEqual(
            previa["emails"][0]["subject"], "Cuidados a ter nos próximos dias"
        )

    def test_the_whatsapp_message_shows_up_with_its_recipient(self):
        WhatsAppEventSetting.objects.filter(
            event_type=WhatsAppEventSetting.EVENT_APPOINTMENT_CONFIRMED,
            audience=WhatsAppEventSetting.AUDIENCE_CUSTOMER,
        ).update(is_active=True, provider=WhatsAppEventSetting.PROVIDER_BAILEYS)

        previa = self.previsualizar("confirm")

        self.assertEqual(len(previa["whatsapp"]), 1)
        self.assertIn("+351910000000", previa["whatsapp"][0]["to"])
        self.assertIn("Maria Silva", previa["whatsapp"][0]["body"])

    def test_a_channel_that_is_off_says_so_instead_of_showing_a_message(self):
        definicao = MessagingSetting.load()
        definicao.send_emails = False
        definicao.save()

        previa = self.previsualizar("confirm")

        self.assertEqual(previa["emails"], [])
        self.assertIn(
            "O envio de emails está desligado nas configurações.", previa["notes"]
        )

    def test_a_customer_without_email_says_so(self):
        self.customer.email = ""
        self.customer.save()

        previa = self.previsualizar("confirm")

        self.assertEqual(previa["emails"], [])
        self.assertIn("A cliente não tem email registado.", previa["notes"])

    def test_nothing_to_send_is_said_out_loud(self):
        self.customer.email = ""
        self.customer.save()

        previa = self.previsualizar("confirm")

        self.assertTrue(previa["is_empty"])

    def test_an_unknown_action_is_refused(self):
        resposta = self.client.post(self.url, {"acao": "apagar"})

        self.assertEqual(resposta.status_code, 400)

    def test_it_is_closed_to_who_is_not_from_the_internal_area(self):
        self.client.logout()

        self.assertNotEqual(
            self.client.post(self.url, {"acao": "confirm"}).status_code, 200
        )


class PreviewIsWiredToTheScreensTests(TestCase):
    """Os ecrãs que perguntam têm de saber onde ir buscar a mensagem."""

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
            status=Appointment.STATUS_SCHEDULED,
            origin=Appointment.ORIGIN_PUBLIC,
        )

        self.client.force_login(self.user)

    def endereco(self):
        return reverse(
            "appointments:appointment_message_preview",
            kwargs={"pk": self.appointment.pk},
        )

    def test_the_detail_screen_points_at_the_preview(self):
        html = self.client.get(
            reverse("appointments:appointment_detail", args=[self.appointment.pk])
        ).content.decode()

        self.assertIn(self.endereco(), html)
        self.assertIn('data-preview-action="confirm"', html)

    def test_the_cancellation_screen_points_at_the_preview(self):
        html = self.client.get(
            reverse("appointments:appointment_cancel", args=[self.appointment.pk])
        ).content.decode()

        self.assertIn(self.endereco(), html)
        self.assertIn('data-preview-action="cancel"', html)

    def test_the_dashboard_points_at_the_preview(self):
        html = self.client.get(reverse("dashboard")).content.decode()

        self.assertIn(self.endereco(), html)
        self.assertIn('data-preview-action="confirm"', html)
