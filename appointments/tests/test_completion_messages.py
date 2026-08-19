from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from appointments.models import Appointment, BusinessHour, Customer
from appointments.tests.factories import create_test_service
from appointments.use_cases import CompleteAppointmentUseCase
from notifications.models import EmailTemplate, ServiceFollowUp


class CompletionMessageTests(TestCase):
    """O que a cliente recebe quando o atendimento é dado por concluído.

    Duas decisões separadas: se sai alguma coisa — que é a pergunta feita no
    ecrã — e, saindo, se sai o texto do serviço ou o agradecimento comum.
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
        self.date = date(2026, 5, 4)

        BusinessHour.objects.update_or_create(
            weekday=self.date.weekday(),
            defaults={
                "start_time": time(9, 0),
                "end_time": time(18, 0),
                "is_active": True,
            },
        )

        self.appointment = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(10, 0),
            status=Appointment.STATUS_CONFIRMED,
            created_by=self.user,
        )

    def mensagem_do_servico(self, trigger=ServiceFollowUp.TRIGGER_COMPLETION):
        modelo = EmailTemplate.objects.create(
            key=f"cuidados_{trigger}",
            name="Cuidados depois da remoção de calos",
            subject="Cuidados a ter nos próximos dias",
            body_text="Olá {{ customer_name }}, evite calçado apertado.",
            is_active=True,
        )

        return ServiceFollowUp.objects.create(
            service=self.service,
            email_template=modelo,
            trigger=trigger,
            days_after=0,
        )

    def concluir(self, **kwargs):
        with patch("appointments.use_cases.notify_whatsapp"):
            with self.captureOnCommitCallbacks(execute=True):
                return CompleteAppointmentUseCase.execute(
                    appointment=self.appointment, user=self.user, **kwargs
                )

    def test_without_a_service_message_the_common_thank_you_goes_out(self):
        self.concluir()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Obrigada pela sua visita")

    def test_a_service_with_its_own_message_replaces_the_common_one(self):
        # As instruções de cuidados de uma remoção de calos não são as de uma
        # manicure. Quando o serviço tem texto próprio, é esse que conta.
        self.mensagem_do_servico()

        self.concluir()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Cuidados a ter nos próximos dias")

    def test_answering_no_sends_nothing(self):
        self.mensagem_do_servico()

        resultado = self.concluir(send_message=False)

        self.assertTrue(resultado.success)
        self.assertEqual(mail.outbox, [])
        self.assertIn("Não foi enviada mensagem", resultado.message)

    def test_a_manual_message_never_goes_out_on_its_own(self):
        # A mensagem manual existe para estar à mão no ecrã da marcação. Sair
        # sozinha ao concluir seria enviá-la sem ninguém a ter escolhido.
        self.mensagem_do_servico(trigger=ServiceFollowUp.TRIGGER_MANUAL)

        self.concluir()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Obrigada pela sua visita")

    def test_an_inactive_service_message_falls_back_to_the_common_one(self):
        mensagem = self.mensagem_do_servico()
        mensagem.is_active = False
        mensagem.save(update_fields=["is_active"])

        self.concluir()

        self.assertEqual(mail.outbox[0].subject, "Obrigada pela sua visita")

    def test_the_screen_asks_before_sending(self):
        self.client.force_login(self.user)

        pagina = self.client.get(
            reverse("appointments:appointment_detail", args=[self.appointment.pk])
        ).content.decode()

        self.assertIn("sendMessageChoiceModal", pagina)
        self.assertIn('name="send_message"', pagina)

    def test_the_answer_travels_from_the_screen(self):
        self.client.force_login(self.user)
        url = reverse("appointments:appointment_complete", args=[self.appointment.pk])

        with patch("appointments.use_cases.notify_whatsapp"):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(url, {"send_message": "0"})

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.status, Appointment.STATUS_COMPLETED)
        self.assertEqual(mail.outbox, [])
