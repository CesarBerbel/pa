"""Quem marca na versão inglesa do site recebe em inglês.

A profissional continua a receber tudo em português: quem lê os avisos
internos é sempre a mesma pessoa.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from appointments import emails
from appointments.customer_services import find_or_create_customer
from appointments.models import Appointment, Customer, Service
from notifications.models import EmailTemplate, WhatsAppEventSetting
from notifications.services import EmailTemplateService


class CustomerLanguageIsRememberedTests(TestCase):
    """De onde vem a língua: da versão do site em que a pessoa marcou."""

    def test_booking_in_portuguese_stores_portuguese(self):
        with self.settings(LANGUAGE_CODE="pt-pt"):
            cliente = find_or_create_customer(
                name="Ana", phone="+351911111111", email="ana@exemplo.pt"
            )

        self.assertEqual(cliente.language, "pt-pt")
        self.assertFalse(cliente.prefers_english)

    def test_booking_in_english_stores_english(self):
        from django.utils.translation import override

        with override("en"):
            cliente = find_or_create_customer(
                name="Jane", phone="+351922222222", email="jane@example.com"
            )

        self.assertEqual(cliente.language, "en")
        self.assertTrue(cliente.prefers_english)

    def test_booking_again_in_another_language_moves_with_the_person(self):
        # Quem marcou em português e volta a marcar em inglês está a dizer em
        # que língua quer ser tratado.
        from django.utils.translation import override

        cliente = find_or_create_customer(
            name="Ana", phone="+351911111111", email="ana@exemplo.pt"
        )
        self.assertEqual(cliente.language, "pt-pt")

        with override("en"):
            find_or_create_customer(
                name="Ana", phone="+351911111111", email="ana@exemplo.pt"
            )

        cliente.refresh_from_db()
        self.assertEqual(cliente.language, "en")


class EmailTemplateLanguageTests(TestCase):
    def setUp(self):
        self.modelo = EmailTemplate.objects.create(
            key="teste",
            name="Teste",
            subject="Assunto",
            body_text="Corpo",
            body_html="<p>Corpo</p>",
            subject_en="Subject",
            body_text_en="Body",
            body_html_en="<p>Body</p>",
        )

    def test_portuguese_is_what_comes_by_default(self):
        self.assertEqual(self.modelo.for_language(None)["subject"], "Assunto")
        self.assertEqual(self.modelo.for_language("pt-pt")["subject"], "Assunto")

    def test_english_comes_for_english(self):
        versao = self.modelo.for_language("en")

        self.assertEqual(versao["subject"], "Subject")
        self.assertEqual(versao["body_text"], "Body")

    def test_a_missing_translation_falls_back_field_by_field(self):
        # Traduzir só metade não pode deixar o assunto numa língua e o corpo
        # noutra por acidente — cada campo cai para o português sozinho.
        self.modelo.body_text_en = ""
        self.modelo.save()

        versao = self.modelo.for_language("en")

        self.assertEqual(versao["subject"], "Subject")
        self.assertEqual(versao["body_text"], "Corpo")

    def test_rendering_uses_the_language_asked_for(self):
        self.modelo.subject = "Olá {{ customer_name }}"
        self.modelo.subject_en = "Hello {{ customer_name }}"
        self.modelo.save()

        contexto = {"customer_name": "Jane"}

        self.assertEqual(
            EmailTemplateService.render_template_object(
                self.modelo, contexto, language="en"
            )["subject"],
            "Hello Jane",
        )
        self.assertEqual(
            EmailTemplateService.render_template_object(self.modelo, contexto)["subject"],
            "Olá Jane",
        )


class WhatsAppTemplateLanguageTests(TestCase):
    def test_english_body_is_used_when_there_is_one(self):
        regra = WhatsAppEventSetting(
            body_template="Olá",
            body_template_en="Hello",
            content_sid="HX1",
            content_sid_en="HX2",
        )

        self.assertEqual(regra.for_language("en")["body"], "Hello")
        self.assertEqual(regra.for_language("en")["content_sid"], "HX2")

    def test_without_an_english_version_the_portuguese_goes_out(self):
        # Uma mensagem na língua errada continua a avisar a pessoa; uma
        # mensagem por enviar não avisa ninguém.
        regra = WhatsAppEventSetting(body_template="Olá", content_sid="HX1")

        self.assertEqual(regra.for_language("en")["body"], "Olá")
        self.assertEqual(regra.for_language("en")["content_sid"], "HX1")

    def test_the_professional_always_reads_portuguese(self):
        from notifications.whatsapp_common import audience_language

        regra = WhatsAppEventSetting(
            audience=WhatsAppEventSetting.AUDIENCE_PROFESSIONAL
        )
        cliente = Customer(language="en")
        marcacao = Appointment(customer=cliente)

        self.assertEqual(audience_language(regra, marcacao), "pt-pt")

    def test_the_customer_reads_her_own_language(self):
        from notifications.whatsapp_common import audience_language

        regra = WhatsAppEventSetting(audience=WhatsAppEventSetting.AUDIENCE_CUSTOMER)
        marcacao = Appointment(customer=Customer(language="en"))

        self.assertEqual(audience_language(regra, marcacao), "en")


class EmailsGoOutInTheCustomerLanguageTests(TestCase):
    """O caminho inteiro: da marcação até ao email que sai."""

    def setUp(self):
        User = get_user_model()
        self.profissional = User.objects.create_superuser(
            email="admin@test.com", password="x", full_name="Admin"
        )

        self.servico = Service.objects.create(
            name="Podologia", duration_minutes=60, price="50.00", is_active=True
        )

    def marcacao(self, language):
        cliente = Customer.objects.create(
            full_name="Jane",
            email="jane@example.com",
            phone="+351922222222",
            language=language,
        )

        amanha = timezone.localdate() + timedelta(days=1)

        return Appointment.objects.create(
            customer=cliente,
            service=self.servico,
            date=amanha,
            start_time=time(10, 0),
            status=Appointment.STATUS_CONFIRMED,
            created_by=self.profissional,
        )

    def enviado(self, marcacao):
        with emails.capture_emails() as apanhados:
            emails.send_appointment_confirmation_email(marcacao)

        return apanhados

    def test_an_english_customer_gets_the_english_email(self):
        apanhados = self.enviado(self.marcacao("en"))

        self.assertTrue(apanhados)
        assunto = apanhados[0]["subject"].lower()
        corpo = apanhados[0]["body"].lower()

        self.assertIn("appointment", assunto)
        self.assertNotIn("marcação", assunto)
        self.assertIn("kind regards", corpo)
        self.assertNotIn("cumprimentos", corpo)

    def test_a_portuguese_customer_still_gets_portuguese(self):
        apanhados = self.enviado(self.marcacao("pt-pt"))

        self.assertTrue(apanhados)

        self.assertIn("marcação", apanhados[0]["subject"].lower())
        self.assertIn("cumprimentos", apanhados[0]["body"].lower())

    def test_the_professional_notice_stays_in_portuguese(self):
        # A cliente é inglesa; o aviso interno não é.
        marcacao = self.marcacao("en")

        with emails.capture_emails() as apanhados:
            emails.send_professional_notification_email(
                marcacao,
                event_type="appointment_created",
                template_key="appointment_created_professional",
            )

        if not apanhados:
            self.skipTest("O aviso à profissional está desligado nesta configuração.")

        texto = (apanhados[0]["subject"] + apanhados[0]["body"]).lower()

        self.assertNotIn("kind regards", texto)
        self.assertIn("marcação", texto)
