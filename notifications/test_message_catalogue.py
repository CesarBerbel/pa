from datetime import date, time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.template import Context, Template
from django.test import TestCase

from appointments.appointment_services import AppointmentService
from appointments.models import Appointment, BusinessHour, Customer
from appointments.tests.factories import create_test_service
from notifications.models import EmailEventSetting, EmailTemplate, WhatsAppEventSetting
from notifications.services import EmailTemplateService


class MessageCatalogueTests(TestCase):
    """O catálogo que o sistema traz instalado, momento a momento.

    Cada teste corresponde a um momento do atendimento em que alguém tem de
    ser avisado. A lista é a razão de existir do catálogo: uma entrada que
    desapareça é um momento em que o sistema fica calado sem ninguém dar por
    isso.
    """

    def modelo(self, key):
        modelo = EmailTemplate.objects.filter(key=key).first()

        self.assertIsNotNone(modelo, f"falta o modelo de email {key}")

        return modelo

    def regra_email(self, event_type, audience):
        regra = EmailEventSetting.objects.filter(
            event_type=event_type, audience=audience
        ).first()

        self.assertIsNotNone(regra, f"falta a regra de email {event_type}/{audience}")
        self.assertIsNotNone(regra.email_template, "a regra ficou sem modelo")

        return regra

    def regra_whatsapp(self, event_type, audience):
        regra = WhatsAppEventSetting.objects.filter(
            event_type=event_type, audience=audience
        ).first()

        self.assertIsNotNone(regra, f"falta a mensagem {event_type}/{audience}")

        return regra

    # -- pedido feito no site ------------------------------------------
    def test_a_request_answers_the_customer(self):
        self.regra_email("appointment_created", "customer")
        self.regra_whatsapp("appointment_requested", "customer")

        modelo = self.modelo("appointment_created")

        # O ponto desta mensagem é dizer que ainda não está confirmado.
        self.assertIn("confirmar", modelo.body_text.lower())

    def test_a_request_tells_the_professional_to_confirm(self):
        self.regra_email("appointment_created", "professional")
        self.regra_whatsapp("appointment_requested", "professional")

        modelo = self.modelo("appointment_created_professional")

        # Quem o lê vai agir sobre a marcação: precisa do contacto e do caminho.
        self.assertIn("{{ customer_phone }}", modelo.body_text)
        self.assertIn("{{ internal_link }}", modelo.body_text)

    # -- confirmação, nas suas duas versões ----------------------------
    def test_the_two_confirmations_say_different_things(self):
        do_site = self.modelo("appointment_confirmed")
        da_clinica = self.modelo("appointment_confirmed_internal")

        self.regra_email("appointment_confirmed", "customer")
        self.regra_email("appointment_confirmed_internal", "customer")
        self.regra_whatsapp("appointment_confirmed", "customer")
        self.regra_whatsapp("appointment_confirmed_internal", "customer")

        self.assertNotEqual(do_site.body_text, da_clinica.body_text)

        # Uma responde a um pedido; a outra regista o que foi combinado.
        self.assertIn("pedido", do_site.body_text.lower())
        self.assertIn("combinámos", da_clinica.body_text.lower())

    def test_both_confirmations_say_where_to_go(self):
        # É a mensagem que a cliente vai reler à porta do prédio.
        for key in ["appointment_confirmed", "appointment_confirmed_internal"]:
            with self.subTest(modelo=key):
                self.assertIn("Sá da Bandeira", self.modelo(key).body_text)

    # -- fim do atendimento --------------------------------------------
    def test_there_is_a_thank_you_for_the_end_of_the_visit(self):
        self.regra_email("appointment_completed", "customer")
        self.regra_whatsapp("appointment_completed", "customer")

        modelo = self.modelo("appointment_completed")

        self.assertIn("obrigada", modelo.body_text.lower())

    # -- cancelamento ---------------------------------------------------
    def test_a_cancellation_reaches_both_sides(self):
        self.regra_email("appointment_cancelled", "customer")
        self.regra_email("appointment_cancelled", "professional")
        self.regra_whatsapp("appointment_cancelled", "customer")
        self.regra_whatsapp("appointment_cancelled", "professional")

        interno = self.modelo("appointment_cancelled_professional")

        self.assertIn("{{ internal_link }}", interno.body_text)

    def test_a_cancellation_always_says_why(self):
        # "A sua marcação foi cancelada", sozinho, deixa quem lê sem saber se
        # foi engano, doença da profissional, ou o cancelamento que pediu.
        for audience in ["customer", "professional"]:
            with self.subTest(quem=audience):
                regra = self.regra_whatsapp("appointment_cancelled", audience)

                self.assertIn("{{ cancellation_reason }}", regra.body_template)
                self.assertIn("Motivo", regra.body_template)

        for key in ["appointment_cancelled", "appointment_cancelled_professional"]:
            with self.subTest(modelo=key):
                self.assertIn("{{ cancellation_reason }}", self.modelo(key).body_text)

    # -- mensagens por serviço ------------------------------------------
    def test_the_per_service_templates_are_ready_to_be_chosen(self):
        # Não pertencem a acontecimento nenhum: são escolhidos numa mensagem
        # de serviço, e é isso que os torna diferentes por serviço.
        for key in ["service_followup", "service_manual"]:
            with self.subTest(modelo=key):
                modelo = self.modelo(key)

                self.assertFalse(
                    EmailEventSetting.objects.filter(email_template=modelo).exists(),
                    "um modelo por serviço não deve estar preso a um acontecimento",
                )

    def test_the_follow_up_says_how_long_ago_the_visit_was(self):
        self.assertIn("{{ days_after }}", self.modelo("service_followup").body_text)

    # -- o catálogo inteiro ---------------------------------------------
    def test_every_template_renders_with_the_data_the_system_provides(self):
        # Uma variável mal escrita não rebenta: sai vazia, e o email chega ao
        # cliente com um buraco no meio da frase.
        contexto = Context(EmailTemplateService.get_sample_context())

        for modelo in EmailTemplate.objects.all():
            with self.subTest(modelo=modelo.key):
                for campo in ["subject", "body_text", "body_html"]:
                    texto = getattr(modelo, campo)

                    if not texto:
                        continue

                    self.assertNotIn("{{", Template(texto).render(contexto))

    def test_the_email_rules_arrive_switched_on(self):
        # Ao contrário do WhatsApp, o email já saía antes: deixá-los desligados
        # seria trocar um email por email nenhum.
        self.assertFalse(
            EmailEventSetting.objects.filter(is_active=False).exists(),
        )


class CancellationReasonTests(TestCase):
    """O motivo, tal como entra no meio da frase da mensagem."""

    def motivo(self, texto):
        from types import SimpleNamespace

        from notifications.whatsapp_common import cancellation_reason

        return cancellation_reason(SimpleNamespace(cancellation_reason=texto))

    def test_a_reason_written_with_a_full_stop_does_not_double_it(self):
        # A mensagem põe o ponto a seguir. Metade dos motivos vem com ponto e a
        # outra metade sem, e sem isto saía "não poderá comparecer..".
        self.assertEqual(self.motivo("Não poderá comparecer."), "Não poderá comparecer")

    def test_a_reason_written_without_one_is_left_alone(self):
        self.assertEqual(self.motivo("Doença"), "Doença")

    def test_an_empty_reason_never_leaves_a_hole(self):
        # Um modelo aprovado pela Meta é recusado se uma posição chegar vazia.
        # O cancelamento exige motivo, mas a mensagem também sai à mão.
        self.assertEqual(self.motivo("   "), "não indicado")
        self.assertEqual(self.motivo(None), "não indicado")


class ProfessionalNoticeTests(TestCase):
    """O aviso interno de que entrou um pedido pelo site."""

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

    def marcar(self, origem):
        with self.captureOnCommitCallbacks(execute=True):
            return AppointmentService.create_appointment(
                customer=self.customer,
                service=self.service,
                date=self.date,
                start_time=time(10, 0),
                created_by=self.user,
                origin=origem,
            )

    def test_a_booking_from_the_site_warns_the_professional(self):
        self.marcar(Appointment.ORIGIN_PUBLIC)

        para_profissional = [
            enviado
            for enviado in mail.outbox
            if settings.PROFESSIONAL_EMAIL in enviado.to
        ]

        self.assertEqual(len(para_profissional), 1)
        self.assertIn("Maria Silva", para_profissional[0].subject)
        self.assertIn("+351910000000", para_profissional[0].body)

    def test_an_appointment_typed_in_the_clinic_warns_nobody_internally(self):
        # Quem a criou estava a olhar para a agenda: avisá-la do que acabou de
        # escrever seria ruído.
        self.marcar(Appointment.ORIGIN_INTERNAL)

        self.assertEqual(
            [
                enviado
                for enviado in mail.outbox
                if settings.PROFESSIONAL_EMAIL in enviado.to
            ],
            [],
        )
