"""Quem marca na versão inglesa do site recebe em inglês.

A profissional continua a receber tudo em português: quem lê os avisos
internos é sempre a mesma pessoa.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone, translation

from appointments import emails
from appointments.customer_services import find_or_create_customer
from appointments.models import Appointment, Customer, Service
from appointments.tests.factories import (
    create_test_service,
    ensure_test_business_hour,
)
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
            EmailTemplateService.render_template_object(self.modelo, contexto)[
                "subject"
            ],
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

    def test_without_an_english_text_the_portuguese_goes_out(self):
        # Uma mensagem na língua errada continua a avisar a pessoa; uma
        # mensagem por enviar não avisa ninguém.
        regra = WhatsAppEventSetting(body_template="Olá", content_sid="HX1")

        self.assertEqual(regra.for_language("en")["body"], "Olá")

    def test_the_portuguese_approved_template_is_not_used_for_english(self):
        # Um modelo aprovado em português é texto português. Mandá-lo a quem
        # fala inglês não é um recurso: é a mensagem errada com a aparência de
        # estar tudo bem.
        regra = WhatsAppEventSetting(
            body_template="Olá",
            body_template_en="Hello",
            content_sid="HX1",
        )

        self.assertEqual(regra.for_language("en")["content_sid"], "")

    def test_without_an_approved_english_template_the_free_text_goes_out(self):
        # É isto que tira a necessidade de um Content SID para falar inglês.
        from notifications import twilio_whatsapp

        regra = WhatsAppEventSetting(
            body_template="Olá {{ customer_name }}",
            body_template_en="Hello {{ customer_name }}",
            content_sid="HX1",
        )

        payload = twilio_whatsapp.build_payload(
            regra,
            {"customer_name": "Jane"},
            "whatsapp:+351910000000",
            language="en",
        )

        self.assertEqual(payload["Body"], "Hello Jane")
        self.assertNotIn("ContentSid", payload)

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


class TheAppointmentRemembersItsLanguageTests(TestCase):
    """A língua da marcação, e não a da última vez que a cliente marcou.

    A língua guardada na cliente acompanha a última marcação: quem marcou em
    inglês e volta a marcar em português mudava-a, e as mensagens das marcações
    antigas mudavam com ela — uma confirmação inglesa passava a sair em
    português a meio caminho.
    """

    def setUp(self):
        # A marcação pública é gravada em nome do primeiro administrador.
        get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.service = create_test_service(duration_minutes=60)

        self.hoje = timezone.localdate() + timedelta(days=7)
        while self.hoje.weekday() != 0:
            self.hoje += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.hoje.weekday(),
            start_time=time(8, 0),
            end_time=time(18, 0),
        )

    def marcacao(self, **campos):
        cliente = Customer.objects.create(
            full_name="Jane Doe",
            email="jane@example.com",
            phone="+351911111111",
            **{"language": campos.pop("lingua_da_cliente", "pt-pt")},
        )

        return Appointment(customer=cliente, service=self.service, **campos)

    def test_the_flag_decides_the_email_language(self):
        from appointments.emails import customer_language

        marcacao = self.marcacao(customer_speaks_english=True)

        self.assertEqual(customer_language(marcacao), "en")

    def test_without_the_flag_the_customer_still_decides(self):
        # O que já existia continua a valer: uma marcação antiga não perde a
        # língua por não ter a marca nova.
        from appointments.emails import customer_language

        marcacao = self.marcacao(lingua_da_cliente="en")

        self.assertEqual(customer_language(marcacao), "en")

    def test_the_flag_decides_the_whatsapp_language_too(self):
        from notifications.whatsapp_common import audience_language

        regra = WhatsAppEventSetting(audience=WhatsAppEventSetting.AUDIENCE_CUSTOMER)
        marcacao = self.marcacao(customer_speaks_english=True)

        self.assertEqual(audience_language(regra, marcacao), "en")

    def test_the_professional_keeps_reading_portuguese(self):
        from notifications.whatsapp_common import audience_language

        regra = WhatsAppEventSetting(
            audience=WhatsAppEventSetting.AUDIENCE_PROFESSIONAL
        )
        marcacao = self.marcacao(customer_speaks_english=True)

        self.assertEqual(audience_language(regra, marcacao), "pt-pt")

    def test_a_booking_finished_in_english_is_marked(self):
        # É isto que faz as mensagens saírem em inglês a quem marcou em /en/.
        from appointments.appointment_services import AppointmentService

        with translation.override("en"):
            cliente = find_or_create_customer(
                name="Jane Doe",
                phone="+351911111111",
                email="jane@example.com",
            )

            resultado = AppointmentService.create_public_appointment(
                customer=cliente,
                service_id=self.service.pk,
                date_value=self.hoje.strftime("%Y-%m-%d"),
                start_time_value="10:00",
                send_email=False,
            )

        self.assertTrue(resultado.appointment.customer_speaks_english)

    def test_a_booking_finished_in_portuguese_is_not(self):
        from appointments.appointment_services import AppointmentService

        with translation.override("pt-pt"):
            cliente = find_or_create_customer(
                name="Maria Silva",
                phone="+351912222222",
                email="maria@exemplo.pt",
            )

            resultado = AppointmentService.create_public_appointment(
                customer=cliente,
                service_id=self.service.pk,
                date_value=self.hoje.strftime("%Y-%m-%d"),
                start_time_value="11:00",
                send_email=False,
            )

        self.assertFalse(resultado.appointment.customer_speaks_english)


class TheServiceNameIsTranslatedTooTests(TestCase):
    """Uma mensagem em inglês não pode ter o serviço em português.

    O nome do serviço está guardado na base de dados e não passa pelo gettext.
    `display_name` resolve-o pela página onde alguém está, o que serve o site e
    não serve as mensagens: uma confirmação em inglês é escrita a partir da
    área interna, que está em português, e saía "Your appointment for Pedicure
    terapêutica".
    """

    def setUp(self):
        get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.service = create_test_service(duration_minutes=60)
        self.service.name = "Pedicure terapêutica"
        self.service.name_en = "Therapeutic pedicure"
        self.service.save(update_fields=["name", "name_en"])

        self.customer = Customer.objects.create(
            full_name="Jane Doe",
            email="jane@example.com",
            phone="+351911111111",
        )

        self.hoje = timezone.localdate() + timedelta(days=7)
        while self.hoje.weekday() != 0:
            self.hoje += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.hoje.weekday(),
            start_time=time(8, 0),
            end_time=time(18, 0),
        )

    def marcacao(self, **campos):
        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.hoje,
            start_time=time(10, 0),
            created_by=get_user_model().objects.first(),
            **campos,
        )

    def test_the_service_says_its_name_in_the_language_asked_for(self):
        self.assertEqual(self.service.name_for_language("en"), "Therapeutic pedicure")
        self.assertEqual(
            self.service.name_for_language("pt-pt"), "Pedicure terapêutica"
        )

    def test_a_service_without_an_english_name_keeps_the_portuguese(self):
        # Um campo inglês vazio é um nome por traduzir, não um nome vazio.
        self.service.name_en = ""

        self.assertEqual(self.service.name_for_language("en"), "Pedicure terapêutica")

    def test_the_english_email_carries_the_english_name(self):
        from appointments.emails import build_appointment_context, customer_language

        marcacao = self.marcacao(customer_speaks_english=True)
        contexto = build_appointment_context(marcacao, customer_language(marcacao))

        self.assertEqual(contexto["service_name"], "Therapeutic pedicure")

    def test_the_portuguese_email_keeps_the_portuguese_name(self):
        from appointments.emails import build_appointment_context, customer_language

        marcacao = self.marcacao()
        contexto = build_appointment_context(marcacao, customer_language(marcacao))

        self.assertEqual(contexto["service_name"], "Pedicure terapêutica")

    def test_the_notice_to_the_professional_stays_in_portuguese(self):
        # Quem lê os avisos internos é sempre a mesma pessoa, e o serviço
        # chama-se o que está escrito na agenda dela.
        from appointments.emails import build_appointment_context

        contexto = build_appointment_context(
            self.marcacao(customer_speaks_english=True)
        )

        self.assertEqual(contexto["service_name"], "Pedicure terapêutica")

    def test_the_whatsapp_message_carries_it_too(self):
        from notifications.whatsapp_common import audience_language, build_context

        regra = WhatsAppEventSetting(audience=WhatsAppEventSetting.AUDIENCE_CUSTOMER)
        marcacao = self.marcacao(customer_speaks_english=True)

        contexto = build_context(marcacao, audience_language(regra, marcacao))

        self.assertEqual(contexto["service_name"], "Therapeutic pedicure")

    def test_the_confirmation_that_goes_out_says_it(self):
        # Do princípio ao fim: a marcação marcada como inglesa produz uma
        # mensagem inteira em inglês.
        from appointments.message_preview import build_preview

        previa = build_preview(self.marcacao(customer_speaks_english=True), "confirm")
        corpo = previa.emails[0]["body"]

        self.assertIn("Therapeutic pedicure", corpo)
        self.assertNotIn("Pedicure terapêutica", corpo)
