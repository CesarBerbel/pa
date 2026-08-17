"""Mensagens de WhatsApp pelo Baileys, e a escolha do caminho por regra.

O serviço Node não é chamado nos testes; o que se verifica é o que lhe seria
pedido, para quem, e o que fica registado deste lado.
"""

from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.appointment_services import AppointmentService
from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from notifications import baileys_whatsapp, whatsapp_dispatch
from notifications.models import WhatsAppEventSetting, WhatsAppMessageLog

BAILEYS_LIGADO = {
    "BAILEYS_ENABLED": True,
    "BAILEYS_API_URL": "http://baileys:3000",
    "BAILEYS_API_TOKEN": "token-de-teste",
    "BAILEYS_PROFESSIONAL_WHATSAPP": "+351938594367",
}

TWILIO_LIGADA = {
    "TWILIO_ENABLED": True,
    "TWILIO_ACCOUNT_SID": "ACtestesid",
    "TWILIO_AUTH_TOKEN": "token-de-teste",
    "TWILIO_WHATSAPP_FROM": "whatsapp:+14155238886",
    "TWILIO_PROFESSIONAL_WHATSAPP": "+351938594367",
}


class BaileysBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.client.force_login(self.user)

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.service = create_test_service(duration_minutes=60)

        self.date = timezone.localdate() + timedelta(days=7)
        while self.date.weekday() != 0:
            self.date += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.date.weekday(),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        # As regras semeadas pela migração saem pela Twilio. Os testes daqui
        # criam as suas, e estas ficariam a disparar por cima.
        WhatsAppEventSetting.objects.update(is_active=False)

        self.enviados = []

        def falso_envio(recipient, text):
            self.enviados.append({"to": recipient, "text": text})
            return {"success": True, "id": f"BAE{len(self.enviados)}"}

        self.patcher = patch.object(
            baileys_whatsapp, "send_text", side_effect=falso_envio
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def regra(self, event_type, audience, **extra):
        dados = {
            "provider": WhatsAppEventSetting.PROVIDER_BAILEYS,
            "body_template": "Olá {{ customer_name }}, {{ appointment_date }}.",
            "meta_template_body": "",
            "content_sid": "",
            "content_variables": "",
            "is_active": True,
        }
        dados.update(extra)

        regra, _ = WhatsAppEventSetting.objects.update_or_create(
            event_type=event_type,
            audience=audience,
            defaults=dados,
        )

        return regra

    def marcacao(self, status=Appointment.STATUS_SCHEDULED):
        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(10, 0),
            status=status,
            created_by=self.user,
        )


@override_settings(**BAILEYS_LIGADO)
class RecipientTests(BaileysBase):
    def test_the_customer_rule_goes_to_the_customer(self):
        regra = self.regra("appointment_requested", "customer")

        self.assertEqual(
            baileys_whatsapp.resolve_recipients(regra, self.marcacao()),
            ["+351910000000"],
        )

    def test_the_professional_rule_uses_its_own_setting(self):
        regra = self.regra("appointment_requested", "professional")

        self.assertEqual(
            baileys_whatsapp.resolve_recipients(regra, self.marcacao()),
            ["+351938594367"],
        )

    def test_custom_numbers_are_split_and_normalised(self):
        regra = self.regra(
            "appointment_requested",
            "custom",
            custom_recipients="+351 912 345 678, 351913333333",
        )

        self.assertEqual(
            baileys_whatsapp.resolve_recipients(regra, self.marcacao()),
            ["+351912345678", "+351913333333"],
        )

    def test_an_unusable_number_is_dropped_not_sent(self):
        regra = self.regra("appointment_requested", "custom", custom_recipients="123, ")

        self.assertEqual(
            baileys_whatsapp.resolve_recipients(regra, self.marcacao()),
            [],
        )


@override_settings(**BAILEYS_LIGADO)
class MessageBodyTests(BaileysBase):
    def test_the_variables_are_filled_in(self):
        self.regra("appointment_requested", "customer")

        whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertEqual(len(self.enviados), 1)
        self.assertIn("Maria Silva", self.enviados[0]["text"])

    def test_the_approved_template_of_twilio_is_ignored(self):
        # O Content SID é da Twilio. Pelo Baileys o que conta é o texto, e uma
        # regra que só tivesse o SID não teria nada para dizer.
        self.regra(
            "appointment_requested",
            "customer",
            content_sid="HX0000000000000000000000000000000",
        )

        whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertIn("Maria Silva", self.enviados[0]["text"])

    def test_an_empty_message_is_refused_instead_of_sending_nothing(self):
        regra = self.regra("appointment_requested", "customer", body_template="   ")

        resultado = baileys_whatsapp.send_for_setting(self.marcacao(), regra)

        self.assertFalse(resultado.success)
        self.assertEqual(self.enviados, [])


@override_settings(**BAILEYS_LIGADO)
class SendingTests(BaileysBase):
    def test_both_audiences_of_one_event_are_sent(self):
        self.regra("appointment_requested", "customer")
        self.regra("appointment_requested", "professional")

        whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertEqual(
            sorted(envio["to"] for envio in self.enviados),
            ["+351910000000", "+351938594367"],
        )

    def test_the_send_is_recorded_against_baileys(self):
        self.regra("appointment_requested", "customer")

        whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        registo = WhatsAppMessageLog.objects.get()

        self.assertEqual(registo.provider, WhatsAppMessageLog.PROVIDER_BAILEYS)
        self.assertEqual(registo.whatsapp_message_id, "BAE1")

    def test_the_same_message_is_not_sent_twice(self):
        self.regra("appointment_requested", "customer")
        marcacao = self.marcacao()

        whatsapp_dispatch.notify(marcacao, "appointment_requested")
        whatsapp_dispatch.notify(marcacao, "appointment_requested")

        self.assertEqual(len(self.enviados), 1)

    def test_an_inactive_rule_is_skipped(self):
        self.regra("appointment_requested", "customer", is_active=False)

        whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertEqual(self.enviados, [])

    @override_settings(BAILEYS_ENABLED=False)
    def test_nothing_is_sent_while_baileys_is_off(self):
        self.regra("appointment_requested", "customer")

        resultado = whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertEqual(self.enviados, [])
        self.assertTrue(resultado.skipped)

    @override_settings(BAILEYS_API_TOKEN="")
    def test_a_missing_token_is_reported_not_swallowed(self):
        # Desligado é uma decisão; mal configurado é um erro que ninguém veria
        # se ficasse calado.
        self.regra("appointment_requested", "customer")

        resultado = whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertFalse(resultado.success)
        self.assertIn("BAILEYS_API_TOKEN", resultado.message)


@override_settings(**BAILEYS_LIGADO)
class FailureTests(BaileysBase):
    def test_a_failure_is_recorded_and_does_not_raise(self):
        self.regra("appointment_requested", "customer")
        marcacao = self.marcacao()

        with patch.object(
            baileys_whatsapp,
            "send_text",
            side_effect=baileys_whatsapp.BaileysError("O WhatsApp não está ligado."),
        ):
            resultado = whatsapp_dispatch.notify(marcacao, "appointment_requested")

        self.assertFalse(resultado.success)
        self.assertTrue(
            WhatsAppMessageLog.objects.filter(
                appointment=marcacao,
                provider=WhatsAppMessageLog.PROVIDER_BAILEYS,
                status=WhatsAppMessageLog.STATUS_ERROR,
            ).exists()
        )

    def test_a_failed_send_is_tried_again_next_time(self):
        self.regra("appointment_requested", "customer")
        marcacao = self.marcacao()

        with patch.object(
            baileys_whatsapp,
            "send_text",
            side_effect=baileys_whatsapp.BaileysError("serviço em baixo"),
        ):
            whatsapp_dispatch.notify(marcacao, "appointment_requested")

        with patch.object(
            baileys_whatsapp, "send_text", return_value={"id": "BAE9"}
        ) as segundo:
            whatsapp_dispatch.notify(marcacao, "appointment_requested")

        self.assertEqual(segundo.call_count, 1)

    def test_an_unreachable_service_is_explained(self):
        # "URLError" não diria a ninguém que o container está em baixo.
        with patch("notifications.baileys_whatsapp.urlopen") as falso:
            from urllib.error import URLError

            falso.side_effect = URLError("Name or service not known")

            estado = baileys_whatsapp.get_status()

        self.assertEqual(estado["state"], "unreachable")
        self.assertIn("inacessível", estado["lastError"])


class ProviderRoutingTests(BaileysBase):
    """A escolha do caminho é por regra, e cada regra segue só o seu."""

    @override_settings(**{**BAILEYS_LIGADO, **TWILIO_LIGADA})
    def test_each_rule_uses_the_provider_it_chose(self):
        self.regra("appointment_requested", "customer", provider="baileys")
        self.regra("appointment_requested", "professional", provider="twilio")

        with patch(
            "notifications.twilio_whatsapp.post_message", return_value={"sid": "SM1"}
        ) as twilio:
            whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        # O cliente pelo Baileys, a profissional pela Twilio: uma mensagem por
        # cada caminho, e não a mesma pelos dois.
        self.assertEqual([envio["to"] for envio in self.enviados], ["+351910000000"])
        self.assertEqual(twilio.call_count, 1)
        self.assertEqual(twilio.call_args[0][0]["To"], "whatsapp:+351938594367")

    @override_settings(**{**BAILEYS_LIGADO, "TWILIO_ENABLED": False})
    def test_a_rule_waits_when_its_provider_is_off(self):
        self.regra("appointment_requested", "customer", provider="baileys")
        self.regra("appointment_requested", "professional", provider="twilio")

        with patch("notifications.twilio_whatsapp.post_message") as twilio:
            whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(twilio.call_count, 0)

    @override_settings(**{**BAILEYS_LIGADO, **TWILIO_LIGADA})
    def test_the_two_providers_do_not_collide_in_the_log(self):
        # Provider faz parte da restrição de unicidade: a mesma mensagem pelos
        # dois caminhos são dois envios, não um repetido.
        self.regra("appointment_requested", "customer", provider="baileys")
        marcacao = self.marcacao()

        whatsapp_dispatch.notify(marcacao, "appointment_requested")

        WhatsAppEventSetting.objects.filter(
            event_type="appointment_requested", audience="customer"
        ).update(provider="twilio", content_sid="HX123")

        with patch(
            "notifications.twilio_whatsapp.post_message", return_value={"sid": "SM1"}
        ):
            whatsapp_dispatch.notify(marcacao, "appointment_requested")

        self.assertEqual(
            WhatsAppMessageLog.objects.filter(
                appointment=marcacao,
                status=WhatsAppMessageLog.STATUS_SUCCESS,
            ).count(),
            2,
        )

    @override_settings(**BAILEYS_LIGADO)
    def test_a_booking_sends_through_the_rule_provider(self):
        # O caminho completo: a marcação dispara, o despachante encaminha.
        self.regra("appointment_requested", "customer", provider="baileys")

        with self.captureOnCommitCallbacks(execute=True):
            AppointmentService.create_appointment(
                customer=self.customer,
                service=self.service,
                date=self.date,
                start_time=time(11, 0),
                created_by=self.user,
            )

        self.assertEqual(len(self.enviados), 1)


@override_settings(**BAILEYS_LIGADO)
class ConnectionScreenTests(BaileysBase):
    ESTADO_LIGADO = {
        "state": "connected",
        "qr": "",
        "me": {"id": "351938594367:12@s.whatsapp.net", "name": "Priscila"},
        "lastError": "",
        "connectedAt": "2026-08-17T10:00:00.000Z",
    }

    def test_the_connection_tab_opens(self):
        with patch.object(
            baileys_whatsapp, "get_status", return_value=self.ESTADO_LIGADO
        ):
            resposta = self.client.get(reverse("notifications:whatsapp_connection"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Terminar sessão")

    def test_the_status_endpoint_answers_with_the_qr(self):
        estado = {
            "state": "waiting_qr",
            "qr": "data:image/png;base64,AAAA",
            "me": None,
            "lastError": "",
        }

        with patch.object(baileys_whatsapp, "get_status", return_value=estado):
            resposta = self.client.get(
                reverse("notifications:whatsapp_connection_status")
            )

        dados = resposta.json()

        self.assertEqual(dados["state"], "waiting_qr")
        self.assertEqual(dados["qr"], "data:image/png;base64,AAAA")
        self.assertIn("QR code", dados["label"])

    def test_the_status_endpoint_is_not_public(self):
        # O QR code é a chave da ligação: quem o lê fica com o WhatsApp da
        # clínica no telemóvel dele.
        self.client.logout()

        resposta = self.client.get(reverse("notifications:whatsapp_connection_status"))

        self.assertIn(resposta.status_code, (302, 403))

    def test_switching_every_rule_to_baileys(self):
        WhatsAppEventSetting.objects.update(provider="twilio")

        self.client.post(reverse("notifications:whatsapp_use_baileys_for_all"))

        self.assertFalse(
            WhatsAppEventSetting.objects.exclude(provider="baileys").exists()
        )

    def test_logging_out_reports_a_service_that_does_not_answer(self):
        with patch.object(
            baileys_whatsapp,
            "logout",
            side_effect=baileys_whatsapp.BaileysError("Serviço inacessível."),
        ):
            resposta = self.client.post(
                reverse("notifications:whatsapp_connection_logout"), follow=True
            )

        self.assertContains(resposta, "Serviço inacessível.")


@override_settings(**BAILEYS_LIGADO)
class RuleValidationTests(BaileysBase):
    def test_a_baileys_rule_without_text_is_refused(self):
        WhatsAppEventSetting.objects.all().delete()

        self.client.post(
            reverse("notifications:whatsapp_setting_create"),
            data={
                "event_type": "appointment_requested",
                "audience": "professional",
                "custom_recipients": "",
                "provider": "baileys",
                "body_template": "",
                "meta_template_body": "",
                "content_sid": "HX0000000000000000000000000000000",
                "content_variables": "",
                "is_active": "on",
            },
        )

        self.assertEqual(WhatsAppEventSetting.objects.count(), 0)

    def test_a_baileys_rule_with_text_is_accepted(self):
        WhatsAppEventSetting.objects.all().delete()

        self.client.post(
            reverse("notifications:whatsapp_setting_create"),
            data={
                "event_type": "appointment_requested",
                "audience": "professional",
                "custom_recipients": "",
                "provider": "baileys",
                "body_template": "Novo pedido de {{ customer_name }}.",
                "meta_template_body": "",
                "content_sid": "",
                "content_variables": "",
                "is_active": "on",
            },
        )

        self.assertEqual(WhatsAppEventSetting.objects.count(), 1)
