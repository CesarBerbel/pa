from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
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

    # O fornecedor liga-se aqui, e não se deixa ao ambiente: `BAILEYS_ENABLED`
    # vem por omissão a False e só está ligado em máquinas com um `.env` que o
    # ligue. Sem isto, o teste passava na máquina de quem o escreveu e falhava
    # no CI, que não tem `.env` nenhum.
    @override_settings(BAILEYS_ENABLED=True)
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

    def agenda(self):
        # A agenda mostra um dia de cada vez, e o botão de concluir só existe
        # numa marcação confirmada.
        self.appointment.status = Appointment.STATUS_CONFIRMED
        self.appointment.save(update_fields=["status"])

        return self.client.get(
            reverse("appointments:visual_schedule"),
            {"date": self.date.strftime("%Y-%m-%d")},
        ).content.decode()

    def test_the_agenda_points_at_the_preview_before_finishing(self):
        # Concluir na agenda gravava sem perguntar nada: nem a pré-visualização
        # aparecia, nem `send_message` ia preenchido — o atendimento fechava e a
        # cliente nunca recebia a mensagem de fim.
        html = self.agenda()

        self.assertIn(self.endereco(), html)
        self.assertIn('data-preview-action="complete"', html)

    def test_the_agenda_carries_the_field_that_holds_the_answer(self):
        html = self.agenda()

        self.assertIn('name="send_message"', html)
        self.assertIn("sendMessageChoiceModal", html)


class PreviewOfAnAppointmentThatDoesNotExistYetTests(TestCase):
    """Criar uma marcação também mostra o que a cliente vai receber.

    A janela de gravar perguntava se a cliente é avisada sem mostrar a
    resposta: nos outros ecrãs há uma marcação gravada para pré-visualizar, e
    ao criar a marcação é justamente o que ainda não existe.
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

        self.client.force_login(self.user)

    def url(self):
        return reverse("appointments:new_appointment_message_preview")

    def dados(self, **campos):
        valores = {
            "acao": "confirm",
            "customer_mode": "existing",
            "customer": self.customer.pk,
            "service": self.service.pk,
            "date": self.date.strftime("%Y-%m-%d"),
            "start_time": "10:00",
        }
        valores.update(campos)

        return valores

    def previa(self, **campos):
        return self.client.post(self.url(), self.dados(**campos)).json()

    def test_the_creation_screen_points_at_it(self):
        html = self.client.get(
            reverse("appointments:appointment_create")
        ).content.decode()

        self.assertIn(self.url(), html)
        self.assertIn("data-preview-with-form", html)

    def test_it_shows_the_message_the_appointment_would_send(self):
        previa = self.previa()

        self.assertEqual(len(previa["emails"]), 1)
        self.assertIn("maria@exemplo.pt", previa["emails"][0]["to"])

    def test_it_is_the_message_of_an_appointment_arranged_at_the_clinic(self):
        # E não a resposta a um pedido feito no site, que é outro texto.
        previa = self.previa()

        self.assertIn("combinámos", previa["emails"][0]["body"])

    def test_it_saves_nothing(self):
        self.previa()
        self.previa(
            customer_mode="new",
            customer="",
            new_customer_name="Ana Nova",
            new_customer_phone="+351911111111",
        )

        self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(mail.outbox, [])

    def test_a_customer_who_is_still_being_typed_is_enough(self):
        # Marcar ao telefone com quem ainda não está registado é o caso mais
        # comum deste ecrã.
        previa = self.previa(
            customer_mode="new",
            customer="",
            new_customer_name="Ana Nova",
            new_customer_phone_0="PT",
            new_customer_phone_1="911111111",
            new_customer_email="ana@exemplo.pt",
        )

        self.assertIn("ana@exemplo.pt", previa["emails"][0]["to"])
        self.assertIn("Ana Nova", previa["emails"][0]["body"])

    def test_the_number_being_typed_reaches_the_whatsapp_preview(self):
        # O telefone passou a ter duas caixas, e a pré-visualização continuava
        # a ler o nome antigo: dizia "nenhum número válido para enviar" para
        # uma cliente que tinha o número escrito à frente de quem marcava.
        from appointments.views.appointments import NewAppointmentMessagePreviewView

        marcacao = NewAppointmentMessagePreviewView().montar(
            self.dados(
                customer_mode="new",
                customer="",
                new_customer_name="Ana Nova",
                new_customer_phone_0="GB",
                new_customer_phone_1="7700900123",
            )
        )

        self.assertEqual(marcacao.customer.phone, "+447700900123")

    def test_a_number_still_being_typed_does_not_break_the_window(self):
        # Quem está a meio do formulário vê a mensagem sem o WhatsApp, e não
        # uma janela partida.
        from appointments.views.appointments import NewAppointmentMessagePreviewView

        marcacao = NewAppointmentMessagePreviewView().montar(
            self.dados(
                customer_mode="new",
                customer="",
                new_customer_name="Ana Nova",
                new_customer_phone_0="PT",
                new_customer_phone_1="91",
            )
        )

        self.assertEqual(marcacao.customer.phone, "")

    def test_a_home_visit_says_so_before_anything_is_saved(self):
        previa = self.previa(
            is_home_visit="on",
            home_street="Rua das Flores",
            home_number="12",
        )

        self.assertIn("somos nós a ir ter consigo", previa["emails"][0]["body"])

    def test_a_form_still_being_filled_in_says_what_is_missing(self):
        # Abrir a janela com metade do formulário escrito não pode rebentar.
        previa = self.client.post(self.url(), {"acao": "confirm"}).json()

        self.assertTrue(previa["is_empty"])
        self.assertTrue(previa["notes"])

    def test_it_says_the_code_is_not_the_final_one(self):
        # O código e a ligação nascem ao gravar. Mostrá-los sem o dizer punha
        # quem lê a compará-los depois com os verdadeiros.
        previa = self.previa()

        self.assertTrue(
            any("ao gravar" in nota for nota in previa["notes"]),
            previa["notes"],
        )

    def test_it_is_closed_to_who_is_not_from_the_internal_area(self):
        self.client.logout()

        resposta = self.client.post(self.url(), self.dados())

        self.assertIn(resposta.status_code, (302, 403))
