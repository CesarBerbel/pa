from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from appointments.models import Appointment, BusinessHour, Customer
from appointments.tests.factories import create_test_service
from notifications.models import WhatsAppEventSetting


class InternalConfirmationChoiceTests(TestCase):
    """A pergunta que aparece ao gravar uma marcação na área interna.

    A marcação nasce confirmada, e confirmada é um estado que a cliente devia
    saber. Mas nem toda a marcação interna quer aviso: metade delas é combinada
    ao telefone, com a cliente do outro lado a ouvir a data. Por isso pergunta-se
    em vez de decidir.
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
        self.appointment_date = date(2026, 5, 4)

        BusinessHour.objects.update_or_create(
            weekday=self.appointment_date.weekday(),
            defaults={
                "start_time": time(9, 0),
                "end_time": time(18, 0),
                "is_active": True,
            },
        )

        self.client.force_login(self.user)
        self.url = reverse("appointments:appointment_create")

    def post_appointment(self, **overrides):
        data = {
            "customer_mode": "existing",
            "customer": self.customer.pk,
            "service": self.service.pk,
            "date": self.appointment_date.isoformat(),
            "start_time": "10:00",
            "status": Appointment.STATUS_CONFIRMED,
            "notes": "",
            "new_customer_name": "",
            "new_customer_phone": "",
            "new_customer_email": "",
        }
        data.update(overrides)

        with patch("appointments.use_cases.notify_whatsapp") as whatsapp:
            with self.captureOnCommitCallbacks(execute=True):
                resposta = self.client.post(self.url, data, follow=True)

        return resposta, whatsapp

    def test_choosing_to_notify_sends_the_confirmation(self):
        resposta, whatsapp = self.post_appointment(send_confirmation="1")

        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("maria@example.com", mail.outbox[0].to)

        # Criada na área interna: sai o texto da marcação combinada, não a
        # resposta a um pedido que ninguém fez.
        whatsapp.assert_called_once()
        self.assertEqual(
            whatsapp.call_args.args[1],
            WhatsAppEventSetting.EVENT_APPOINTMENT_CONFIRMED_INTERNAL,
        )

        self.assertContains(resposta, "confirmação enviada")

    def test_choosing_not_to_notify_sends_nothing(self):
        resposta, whatsapp = self.post_appointment(send_confirmation="0")

        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(mail.outbox, [])
        whatsapp.assert_not_called()

        self.assertContains(resposta, "Não foi enviada mensagem")

    def test_a_submission_without_the_answer_stays_quiet(self):
        # É o que acontece sem JavaScript: a marcação grava na mesma, e o que
        # falha é o aviso — nunca ao contrário.
        resposta, whatsapp = self.post_appointment()

        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(mail.outbox, [])
        whatsapp.assert_not_called()

    def test_a_customer_without_email_is_told_apart(self):
        sem_email = Customer.objects.create(
            full_name="Ana Sem Email",
            phone="+351920000000",
        )

        resposta, _ = self.post_appointment(
            customer=sem_email.pk,
            send_confirmation="1",
        )

        self.assertEqual(mail.outbox, [])
        self.assertContains(resposta, "não tem email registado")

    def test_the_question_is_only_asked_when_creating(self):
        pagina = self.client.get(self.url).content.decode()

        self.assertIn("sendMessageChoiceModal", pagina)
        self.assertIn('name="send_confirmation"', pagina)

    def test_editing_never_asks(self):
        # Editar não anuncia nada: quem quiser avisar a cliente tem o ecrã de
        # detalhe, e a pergunta aqui daria a entender que a edição é que envia.
        self.post_appointment(send_confirmation="0")
        marcacao = Appointment.objects.get()

        pagina = self.client.get(
            reverse("appointments:appointment_update", args=[marcacao.pk])
        ).content.decode()

        self.assertNotIn("sendMessageChoiceModal", pagina)
        self.assertNotIn('name="send_confirmation"', pagina)
