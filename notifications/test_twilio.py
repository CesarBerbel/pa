import json
import re
from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.appointment_services import AppointmentService
from appointments.cancellation_services import AppointmentCancellationService
from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from appointments.use_cases import ConfirmAppointmentUseCase
from django.conf import settings

from notifications import twilio_callbacks, twilio_whatsapp, whatsapp_dispatch
from notifications.models import WhatsAppEventSetting, WhatsAppMessageLog

TWILIO_LIGADA = {
    "TWILIO_ENABLED": True,
    "TWILIO_ACCOUNT_SID": "ACtestesid",
    "TWILIO_AUTH_TOKEN": "token-de-teste",
    "TWILIO_WHATSAPP_FROM": "whatsapp:+14155238886",
    "TWILIO_PROFESSIONAL_WHATSAPP": "+351938594367",
}


class TwilioBase(TestCase):
    """Mensagens de WhatsApp pela Twilio.

    A API real não é chamada nos testes; o que se verifica é o que seria
    enviado, para quem, e o que fica registado.
    """

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

    def regra(self, event_type, audience, **extra):
        # A migração de dados já semeia estes pares, e (evento, destinatário) é
        # único: aqui reaproveita-se a linha e substitui-se o conteúdo.
        dados = {
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

    def desligar_semeadas(self):
        WhatsAppEventSetting.objects.update(is_active=False)

    def marcacao(self, status=Appointment.STATUS_SCHEDULED):
        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(10, 0),
            status=status,
            created_by=self.user,
        )


@override_settings(**TWILIO_LIGADA)
class RecipientTests(TwilioBase):
    def test_the_customer_rule_goes_to_the_customer(self):
        regra = self.regra("appointment_requested", "customer")

        self.assertEqual(
            twilio_whatsapp.resolve_recipients(regra, self.marcacao()),
            ["whatsapp:+351910000000"],
        )

    def test_the_professional_rule_goes_to_the_practice_number(self):
        regra = self.regra("appointment_requested", "professional")

        self.assertEqual(
            twilio_whatsapp.resolve_recipients(regra, self.marcacao()),
            ["whatsapp:+351938594367"],
        )

    def test_custom_numbers_are_split_and_normalised(self):
        regra = self.regra(
            "appointment_requested",
            "custom",
            custom_recipients=" +351911111111 , 351922222222 ",
        )

        self.assertEqual(
            twilio_whatsapp.resolve_recipients(regra, self.marcacao()),
            ["whatsapp:+351911111111", "whatsapp:+351922222222"],
        )

    def test_an_unusable_number_is_dropped_instead_of_sent(self):
        regra = self.regra(
            "appointment_requested", "custom", custom_recipients="+351911111111, ---"
        )

        self.assertEqual(
            twilio_whatsapp.resolve_recipients(regra, self.marcacao()),
            ["whatsapp:+351911111111"],
        )

    def test_numbers_already_prefixed_are_not_prefixed_twice(self):
        self.assertEqual(
            twilio_whatsapp.normalize_whatsapp_address("whatsapp:+351910000000"),
            "whatsapp:+351910000000",
        )


@override_settings(**TWILIO_LIGADA)
class PayloadTests(TwilioBase):
    def test_free_text_is_rendered_with_the_appointment(self):
        regra = self.regra("appointment_requested", "customer")

        payload = twilio_whatsapp.build_payload(
            regra,
            twilio_whatsapp.build_context(self.marcacao()),
            "whatsapp:+351910000000",
        )

        self.assertIn("Maria Silva", payload["Body"])
        self.assertNotIn("ContentSid", payload)

    def test_an_approved_template_replaces_the_free_text(self):
        # Fora da janela de 24 horas a Twilio só aceita o modelo aprovado, por
        # isso quando há Content SID é ele que manda.
        regra = self.regra(
            "appointment_requested",
            "customer",
            content_sid="HXabc123",
            content_variables='{"1": "{{ customer_name }}", "2": "{{ appointment_time }}"}',
        )

        payload = twilio_whatsapp.build_payload(
            regra,
            twilio_whatsapp.build_context(self.marcacao()),
            "whatsapp:+351910000000",
        )

        self.assertEqual(payload["ContentSid"], "HXabc123")
        self.assertNotIn("Body", payload)
        self.assertEqual(
            json.loads(payload["ContentVariables"]),
            {"1": "Maria Silva", "2": "10:00"},
        )

    def test_the_sender_comes_from_the_settings(self):
        regra = self.regra("appointment_requested", "customer")

        payload = twilio_whatsapp.build_payload(
            regra, twilio_whatsapp.build_context(self.marcacao()), "whatsapp:+351910"
        )

        self.assertEqual(payload["From"], "whatsapp:+14155238886")


@override_settings(**TWILIO_LIGADA)
class SendingTests(TwilioBase):
    def setUp(self):
        super().setUp()

        self.enviados = []

        def falso_post(payload):
            self.enviados.append(payload)
            return {"sid": f"SM{len(self.enviados)}"}

        self.patcher = patch.object(
            twilio_whatsapp, "post_message", side_effect=falso_post
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.desligar_semeadas()

    def test_both_audiences_of_one_event_are_sent(self):
        # O caso pedido: o pedido de marcação avisa a profissional e o cliente.
        self.regra("appointment_requested", "customer")
        self.regra("appointment_requested", "professional")

        whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        destinos = sorted(p["To"] for p in self.enviados)

        self.assertEqual(destinos, ["whatsapp:+351910000000", "whatsapp:+351938594367"])

    def test_two_audiences_do_not_collide_in_the_log(self):
        # Sem o campo de destinatário no registo, o segundo envio bateria na
        # restrição de unicidade e passaria por repetido.
        self.regra("appointment_requested", "customer")
        self.regra("appointment_requested", "professional")

        marcacao = self.marcacao()
        whatsapp_dispatch.notify(marcacao, "appointment_requested")

        self.assertEqual(
            WhatsAppMessageLog.objects.filter(
                appointment=marcacao,
                status=WhatsAppMessageLog.STATUS_SUCCESS,
            ).count(),
            2,
        )

    def test_an_inactive_rule_is_skipped(self):
        self.regra("appointment_requested", "customer", is_active=False)

        whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertEqual(self.enviados, [])

    def test_another_event_is_not_triggered(self):
        self.regra("appointment_confirmed", "customer")

        whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertEqual(self.enviados, [])

    def test_the_same_message_is_not_sent_twice(self):
        self.regra("appointment_requested", "customer")
        marcacao = self.marcacao()

        whatsapp_dispatch.notify(marcacao, "appointment_requested")
        whatsapp_dispatch.notify(marcacao, "appointment_requested")

        self.assertEqual(len(self.enviados), 1)

    def test_the_send_is_recorded_with_the_provider(self):
        self.regra("appointment_requested", "customer")

        whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        registo = WhatsAppMessageLog.objects.get()

        self.assertEqual(registo.provider, WhatsAppMessageLog.PROVIDER_TWILIO)
        self.assertEqual(registo.whatsapp_message_id, "SM1")

    @override_settings(TWILIO_ENABLED=False)
    def test_nothing_is_sent_while_twilio_is_off(self):
        self.regra("appointment_requested", "customer")

        resultado = whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertEqual(self.enviados, [])
        self.assertTrue(resultado.skipped)

    @override_settings(TWILIO_ACCOUNT_SID="")
    def test_missing_credentials_are_reported_not_swallowed(self):
        self.regra("appointment_requested", "customer")

        resultado = whatsapp_dispatch.notify(self.marcacao(), "appointment_requested")

        self.assertFalse(resultado.success)
        self.assertIn("TWILIO_ACCOUNT_SID", resultado.message)


@override_settings(**TWILIO_LIGADA)
class FailureTests(TwilioBase):
    def setUp(self):
        super().setUp()
        self.desligar_semeadas()

    def test_a_failure_is_recorded_and_does_not_raise(self):
        # Uma falha da Twilio não pode desfazer uma marcação já gravada.
        self.regra("appointment_requested", "customer")
        marcacao = self.marcacao()

        with patch.object(
            twilio_whatsapp, "post_message", side_effect=RuntimeError("rede em baixo")
        ):
            resultado = whatsapp_dispatch.notify(marcacao, "appointment_requested")

        self.assertFalse(resultado.success)
        self.assertTrue(
            WhatsAppMessageLog.objects.filter(
                appointment=marcacao,
                status=WhatsAppMessageLog.STATUS_ERROR,
            ).exists()
        )

    def test_a_failed_send_is_tried_again_next_time(self):
        self.regra("appointment_requested", "customer")
        marcacao = self.marcacao()

        with patch.object(
            twilio_whatsapp, "post_message", side_effect=RuntimeError("rede em baixo")
        ):
            whatsapp_dispatch.notify(marcacao, "appointment_requested")

        with patch.object(
            twilio_whatsapp, "post_message", return_value={"sid": "SM9"}
        ) as segundo:
            whatsapp_dispatch.notify(marcacao, "appointment_requested")

        self.assertEqual(segundo.call_count, 1)

    def test_the_24_hour_error_is_explained(self):
        # "HTTP Error 400" não diria a ninguém que falta aprovar um modelo.
        from urllib.error import HTTPError
        from io import BytesIO

        erro = HTTPError(
            url="https://api.twilio.com",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=BytesIO(
                json.dumps(
                    {"code": 63016, "message": "Failed to send freeform message"}
                ).encode()
            ),
        )

        explicacao = twilio_whatsapp.format_error(erro)

        self.assertIn("63016", explicacao)
        self.assertIn("modelo aprovado", explicacao)


@override_settings(**TWILIO_LIGADA)
class EventWiringTests(TwilioBase):
    """As regras têm de ser disparadas pelos acontecimentos reais."""

    def setUp(self):
        super().setUp()

        self.chamadas = []

        self.patcher = patch.object(
            twilio_whatsapp,
            "post_message",
            side_effect=lambda payload: self.chamadas.append(payload) or {"sid": "SM1"},
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_creating_an_appointment_notifies(self):
        self.regra("appointment_requested", "professional")

        with self.captureOnCommitCallbacks(execute=True):
            AppointmentService.create_appointment(
                customer=self.customer,
                service=self.service,
                date=self.date,
                start_time=time(11, 0),
                created_by=self.user,
            )

        self.assertEqual(len(self.chamadas), 1)

    def test_confirming_notifies_the_customer(self):
        self.regra("appointment_confirmed", "customer")
        marcacao = self.marcacao()
        marcacao.origin = Appointment.ORIGIN_PUBLIC
        marcacao.save(update_fields=["origin"])

        with self.captureOnCommitCallbacks(execute=True):
            ConfirmAppointmentUseCase.execute(
                appointment=marcacao, user=self.user, send_whatsapp=False
            )

        self.assertEqual(len(self.chamadas), 1)
        self.assertEqual(self.chamadas[0]["To"], "whatsapp:+351910000000")

    def test_an_appointment_arranged_at_the_clinic_uses_the_other_text(self):
        # As duas regras ligadas ao mesmo tempo: quem escolhe é a origem da
        # marcação, e não a ordem por que foram configuradas.
        self.regra(
            "appointment_confirmed",
            "customer",
            body_template="Resposta ao pedido feito no site.",
        )
        self.regra(
            "appointment_confirmed_internal",
            "customer",
            body_template="Registo do que ficou combinado ao balcão.",
        )

        marcacao = self.marcacao()
        marcacao.origin = Appointment.ORIGIN_INTERNAL
        marcacao.save(update_fields=["origin"])

        with self.captureOnCommitCallbacks(execute=True):
            ConfirmAppointmentUseCase.execute(
                appointment=marcacao, user=self.user, send_whatsapp=False
            )

        self.assertEqual(len(self.chamadas), 1)
        self.assertIn("ficou combinado", self.chamadas[0]["Body"])

    def test_confirming_in_silence_sends_nothing(self):
        # A janela do ecrã de detalhe pergunta antes de avisar a cliente.
        self.regra("appointment_confirmed", "customer")
        self.regra("appointment_confirmed_internal", "customer")

        with self.captureOnCommitCallbacks(execute=True):
            ConfirmAppointmentUseCase.execute(
                appointment=self.marcacao(),
                user=self.user,
                send_message=False,
            )

        self.assertEqual(self.chamadas, [])

    def test_confirming_does_not_notify_the_professional_unless_configured(self):
        # O pedido era explícito: ao confirmar, só o cliente.
        self.regra("appointment_confirmed", "customer")
        self.regra("appointment_requested", "professional")

        with self.captureOnCommitCallbacks(execute=True):
            ConfirmAppointmentUseCase.execute(
                appointment=self.marcacao(), user=self.user, send_whatsapp=False
            )

        destinos = [c["To"] for c in self.chamadas]

        self.assertNotIn("whatsapp:+351938594367", destinos)

    def test_cancelling_notifies(self):
        self.regra("appointment_cancelled", "customer")

        with self.captureOnCommitCallbacks(execute=True):
            AppointmentCancellationService.cancel(
                appointment=self.marcacao(),
                cancellation_reason="Cliente não pode comparecer.",
                user=self.user,
            )

        self.assertEqual(len(self.chamadas), 1)


class WhatsAppSettingScreenTests(TwilioBase):
    @override_settings(TWILIO_ENABLED=False, BAILEYS_ENABLED=False)
    def test_the_list_warns_when_no_provider_is_on(self):
        resposta = self.client.get(reverse("notifications:whatsapp_setting_list"))

        self.assertContains(resposta, "Não há nenhum caminho de envio ligado")

    @override_settings(**TWILIO_LIGADA)
    def test_the_list_does_not_warn_when_twilio_is_on(self):
        resposta = self.client.get(reverse("notifications:whatsapp_setting_list"))

        self.assertNotContains(resposta, "Não há nenhum caminho de envio ligado")

    @override_settings(TWILIO_ENABLED=False, BAILEYS_ENABLED=True)
    def test_the_list_does_not_warn_when_only_baileys_is_on(self):
        # Basta um caminho de pé. As regras que apontam para o outro aparecem
        # marcadas como bloqueadas, linha a linha.
        resposta = self.client.get(reverse("notifications:whatsapp_setting_list"))

        self.assertNotContains(resposta, "Não há nenhum caminho de envio ligado")

    def test_a_rule_can_be_created(self):
        WhatsAppEventSetting.objects.all().delete()

        self.client.post(
            reverse("notifications:whatsapp_setting_create"),
            data={
                "event_type": "appointment_requested",
                "audience": "professional",
                "custom_recipients": "",
                "provider": "twilio",
                "body_template": "Novo pedido de {{ customer_name }}.",
                "content_sid": "",
                "content_variables": "",
                "is_active": "on",
            },
        )

        self.assertTrue(
            WhatsAppEventSetting.objects.filter(audience="professional").exists()
        )

    def test_an_empty_rule_is_refused(self):
        # Sem mensagem nem modelo não há nada para enviar.
        antes = WhatsAppEventSetting.objects.count()

        self.client.post(
            reverse("notifications:whatsapp_setting_create"),
            data={
                "event_type": "appointment_confirmed",
                "audience": "professional",
                "custom_recipients": "",
                "body_template": "",
                "content_sid": "",
                "content_variables": "",
                "is_active": "on",
            },
        )

        self.assertEqual(WhatsAppEventSetting.objects.count(), antes)

    def test_a_content_sid_that_is_not_one_is_refused(self):
        antes = WhatsAppEventSetting.objects.count()

        resposta = self.client.post(
            reverse("notifications:whatsapp_setting_create"),
            data={
                "event_type": "appointment_confirmed",
                "audience": "professional",
                "custom_recipients": "",
                "body_template": "olá",
                "content_sid": "MG123456",
                "content_variables": "",
                "is_active": "on",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(WhatsAppEventSetting.objects.count(), antes)

    def test_broken_variables_json_is_refused(self):
        antes = WhatsAppEventSetting.objects.count()

        self.client.post(
            reverse("notifications:whatsapp_setting_create"),
            data={
                "event_type": "appointment_confirmed",
                "audience": "professional",
                "custom_recipients": "",
                "body_template": "olá",
                "content_sid": "HX123",
                "content_variables": "{isto não é json}",
                "is_active": "on",
            },
        )

        self.assertEqual(WhatsAppEventSetting.objects.count(), antes)

    def test_custom_audience_without_numbers_is_refused(self):
        antes = WhatsAppEventSetting.objects.count()

        self.client.post(
            reverse("notifications:whatsapp_setting_create"),
            data={
                "event_type": "appointment_requested",
                "audience": "custom",
                "custom_recipients": "",
                "body_template": "olá",
                "content_sid": "",
                "content_variables": "",
                "is_active": "on",
            },
        )

        self.assertEqual(WhatsAppEventSetting.objects.count(), antes)

    @override_settings(**TWILIO_LIGADA)
    def test_the_test_send_does_not_touch_the_history(self):
        regra = self.regra("appointment_requested", "customer")

        with patch.object(twilio_whatsapp, "post_message", return_value={"sid": "SM1"}):
            self.client.post(
                reverse("notifications:whatsapp_setting_test", args=[regra.pk]),
                data={"recipient": "+351911111111"},
            )

        self.assertEqual(WhatsAppMessageLog.objects.count(), 0)

    @override_settings(TWILIO_ENABLED=False)
    def test_the_test_send_is_refused_while_twilio_is_off(self):
        regra = self.regra("appointment_requested", "customer")

        resposta = self.client.post(
            reverse("notifications:whatsapp_setting_test", args=[regra.pk]),
            data={"recipient": "+351911111111"},
            follow=True,
        )

        avisos = [str(m) for m in resposta.context["messages"]]

        self.assertTrue(any("desativada" in a for a in avisos), avisos)


class WhatsAppAccessTests(TestCase):
    def test_customers_cannot_reach_the_settings(self):
        cliente = get_user_model().objects.create_user(
            email="cliente@example.com",
            password="StrongPassword123",
            full_name="Cliente",
        )

        self.client.force_login(cliente)

        self.assertEqual(
            self.client.get(reverse("notifications:whatsapp_setting_list")).status_code,
            302,
        )


class DefaultMessagesTests(TestCase):
    """As mensagens que o sistema traz configuradas de origem.

    Vêm desligadas de propósito: o texto está pronto, mas nada sai antes de
    alguém o rever, submeter o modelo à Meta e colar o Content SID.
    """

    def catalogo(self):
        from notifications.default_messages import DEFAULT_MESSAGES

        return DEFAULT_MESSAGES

    def test_the_seed_created_every_message(self):
        for entrada in self.catalogo():
            with self.subTest(evento=entrada["event_type"], quem=entrada["audience"]):
                self.assertTrue(
                    WhatsAppEventSetting.objects.filter(
                        event_type=entrada["event_type"],
                        audience=entrada["audience"],
                    ).exists()
                )

    def test_the_requested_event_reaches_both_sides(self):
        # O que foi pedido: aviso à podóloga e ao cliente.
        destinatarios = set(
            WhatsAppEventSetting.objects.filter(
                event_type="appointment_requested"
            ).values_list("audience", flat=True)
        )

        self.assertEqual(destinatarios, {"customer", "professional"})

    def test_the_confirmation_only_goes_to_the_customer(self):
        destinatarios = set(
            WhatsAppEventSetting.objects.filter(
                event_type="appointment_confirmed"
            ).values_list("audience", flat=True)
        )

        self.assertEqual(destinatarios, {"customer"})

    def test_there_is_a_thank_you_after_the_visit(self):
        regra = WhatsAppEventSetting.objects.get(
            event_type="appointment_completed", audience="customer"
        )

        self.assertIn("obrigada", regra.body_template.lower())
        self.assertIn("dúvida", regra.body_template.lower())

    def test_they_all_arrive_switched_off(self):
        # Criá-las ativas seria decidir por quem gere a clínica o que os
        # clientes recebem.
        self.assertFalse(WhatsAppEventSetting.objects.filter(is_active=True).exists())

    def test_they_all_carry_the_text_to_submit_to_meta(self):
        for regra in WhatsAppEventSetting.objects.all():
            with self.subTest(regra=str(regra)):
                self.assertTrue(regra.meta_template_body.strip())
                self.assertTrue(regra.content_variables.strip())

    def test_the_positions_match_the_variables(self):
        # Uma posição a mais no modelo aprovado sai vazia na mensagem; uma a
        # menos é rejeitada pela Twilio no envio.
        for regra in WhatsAppEventSetting.objects.all():
            with self.subTest(regra=str(regra)):
                no_texto = set(
                    re.findall(r"\{\{\s*(\d+)\s*\}\}", regra.meta_template_body)
                )
                mapeadas = set(json.loads(regra.content_variables).keys())

                self.assertEqual(no_texto, mapeadas)

    def test_the_mapped_variables_are_ones_the_system_provides(self):
        conhecidas = set(twilio_whatsapp.get_sample_context())

        for regra in WhatsAppEventSetting.objects.all():
            for valor in json.loads(regra.content_variables).values():
                nome = valor.strip().strip("{} ").strip()

                with self.subTest(regra=str(regra), variavel=nome):
                    self.assertIn(nome, conhecidas)

    def test_no_body_starts_or_ends_with_a_position(self):
        # As duas causas de rejeição mais comuns na revisão da Meta.
        for regra in WhatsAppEventSetting.objects.all():
            corpo = regra.meta_template_body.strip()

            with self.subTest(regra=str(regra)):
                self.assertIsNone(re.match(r"^\{\{\s*\d+\s*\}\}", corpo))
                self.assertIsNone(re.search(r"\{\{\s*\d+\s*\}\}$", corpo))
                self.assertIsNone(re.search(r"\}\}\s*\{\{", corpo))

    def test_the_two_texts_say_the_same_thing(self):
        # O texto de envio e o submetido à Meta têm de coincidir, senão o
        # cliente recebe uma coisa diferente da que foi aprovada.
        for regra in WhatsAppEventSetting.objects.all():
            posicoes = json.loads(regra.content_variables)

            reconstruido = regra.meta_template_body
            for numero, variavel in posicoes.items():
                reconstruido = re.sub(
                    r"\{\{\s*%s\s*\}\}" % numero, variavel, reconstruido
                )

            def normalizar(texto):
                return " ".join(texto.split())

            with self.subTest(regra=str(regra)):
                self.assertEqual(
                    normalizar(reconstruido), normalizar(regra.body_template)
                )


@override_settings(**TWILIO_LIGADA)
class CompletedEventTests(TwilioBase):
    def test_completing_an_appointment_sends_the_thank_you(self):
        from appointments.use_cases import CompleteAppointmentUseCase

        WhatsAppEventSetting.objects.filter(event_type="appointment_completed").update(
            is_active=True
        )

        marcacao = self.marcacao(status=Appointment.STATUS_CONFIRMED)

        with patch.object(
            twilio_whatsapp, "post_message", return_value={"sid": "SM1"}
        ) as envio:
            with self.captureOnCommitCallbacks(execute=True):
                CompleteAppointmentUseCase.execute(appointment=marcacao, user=self.user)

        self.assertEqual(envio.call_count, 1)
        self.assertIn("obrigada", envio.call_args[0][0]["Body"].lower())


class MetaRuleValidationTests(TwilioBase):
    """Regras da Meta apanhadas aqui em vez de num email de recusa."""

    def submeter(self, meta_body):
        return self.client.post(
            reverse("notifications:whatsapp_setting_create"),
            data={
                "event_type": "appointment_completed",
                "audience": "professional",
                "custom_recipients": "",
                "provider": "twilio",
                "body_template": "Olá.",
                "meta_template_body": meta_body,
                "content_sid": "",
                "content_variables": "",
                "is_active": "",
            },
        )

    def contagem(self):
        return WhatsAppEventSetting.objects.filter(audience="professional").count()

    def test_a_body_starting_with_a_position_is_refused(self):
        antes = self.contagem()
        self.submeter("{{1}}, a sua marcação está pronta.")

        self.assertEqual(self.contagem(), antes)

    def test_a_body_ending_with_a_position_is_refused(self):
        antes = self.contagem()
        self.submeter("A sua marcação é dia {{1}}")

        self.assertEqual(self.contagem(), antes)

    def test_two_positions_in_a_row_are_refused(self):
        antes = self.contagem()
        self.submeter("Olá {{1}}{{2}}, tudo bem.")

        self.assertEqual(self.contagem(), antes)

    def test_a_gap_in_the_numbering_is_refused(self):
        antes = self.contagem()
        self.submeter("Olá {{1}}, a sua marcação de {{3}} está pronta.")

        self.assertEqual(self.contagem(), antes)

    def test_a_correct_body_is_accepted(self):
        antes = self.contagem()
        self.submeter("Olá {{1}}, a sua marcação de {{2}} está pronta.")

        self.assertEqual(self.contagem(), antes + 1)


@override_settings(**TWILIO_LIGADA)
class ManualWhatsAppSendTests(TwilioBase):
    """Disparo à mão, a partir da marcação."""

    def setUp(self):
        super().setUp()

        self.appointment = self.marcacao()
        self.setting = self.regra("appointment_confirmed", "customer")

        self.enviados = []

        self.patcher = patch.object(
            twilio_whatsapp,
            "post_message",
            side_effect=lambda p: self.enviados.append(p) or {"sid": "SM1"},
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def url(self, setting=None):
        return reverse(
            "notifications:appointment_whatsapp_send",
            args=[self.appointment.pk, (setting or self.setting).pk],
        )

    def test_the_page_lists_the_configured_messages(self):
        resposta = self.client.get(
            reverse("notifications:appointment_followups", args=[self.appointment.pk])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["whatsapp_rows"])

    def test_it_sends(self):
        self.client.post(self.url())

        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.enviados[0]["To"], "whatsapp:+351910000000")

    def test_it_can_be_sent_again(self):
        # Quem carrega no botão já decidiu; o automático é que não repete.
        self.client.post(self.url())
        self.client.post(self.url())

        self.assertEqual(len(self.enviados), 2)

    def test_a_message_whose_automation_is_off_can_still_be_sent(self):
        self.setting.is_active = False
        self.setting.save()

        self.client.post(self.url())

        self.assertEqual(len(self.enviados), 1)

    def test_the_event_does_not_have_to_match_the_appointment(self):
        # Reenviar a confirmação de uma marcação que ainda está por confirmar
        # é uma decisão de quem atende, não do sistema.
        outra = self.regra("appointment_completed", "customer")

        self.client.post(self.url(outra))

        self.assertEqual(len(self.enviados), 1)

    def test_the_send_is_recorded(self):
        self.client.post(self.url())

        self.assertTrue(
            WhatsAppMessageLog.objects.filter(
                appointment=self.appointment,
                provider=WhatsAppMessageLog.PROVIDER_TWILIO,
                status=WhatsAppMessageLog.STATUS_SUCCESS,
            ).exists()
        )

    def test_a_manual_send_stops_the_automatic_one(self):
        self.client.post(self.url())

        whatsapp_dispatch.notify(self.appointment, "appointment_confirmed")

        self.assertEqual(len(self.enviados), 1)

    @override_settings(TWILIO_ENABLED=False)
    def test_it_is_refused_while_twilio_is_off(self):
        resposta = self.client.post(self.url(), follow=True)
        avisos = [str(m) for m in resposta.context["messages"]]

        self.assertEqual(self.enviados, [])
        self.assertTrue(any("desativada" in a for a in avisos), avisos)

    def test_a_customer_without_a_phone_is_reported(self):
        self.customer.phone = ""
        self.customer.save()

        resposta = self.client.post(self.url(), follow=True)
        avisos = [str(m) for m in resposta.context["messages"]]

        self.assertEqual(self.enviados, [])
        self.assertTrue(any("nenhum número" in a for a in avisos), avisos)

    def test_a_failure_is_reported_and_does_not_raise(self):
        with patch.object(
            twilio_whatsapp, "post_message", side_effect=RuntimeError("rede em baixo")
        ):
            resposta = self.client.post(self.url(), follow=True)

        avisos = [str(m) for m in resposta.context["messages"]]

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(any("rede em baixo" in a for a in avisos), avisos)

    def test_customers_cannot_fire_messages(self):
        cliente = get_user_model().objects.create_user(
            email="cliente@example.com",
            password="StrongPassword123",
            full_name="Cliente",
        )

        self.client.force_login(cliente)
        self.client.post(self.url())

        self.assertEqual(self.enviados, [])


@override_settings(**TWILIO_LIGADA, SITE_URL="https://priarantes.com")
class DeliveryStatusTests(TwilioBase):
    """ "Aceite pela Twilio" não é o mesmo que "chegou ao telemóvel".

    A resposta ao envio só diz que a Twilio recebeu a mensagem. A entrega
    acontece depois e pode falhar; sem o webhook de estado, isso ficava
    invisível e o sistema mostrava "enviada" para sempre.
    """

    def setUp(self):
        super().setUp()

        self.appointment = self.marcacao()
        self.setting = self.regra("appointment_confirmed", "customer")

        self.enviados = []

        self.patcher = patch.object(
            twilio_whatsapp,
            "post_message",
            side_effect=lambda p: self.enviados.append(p) or {"sid": "SMabc"},
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def enviar(self):
        self.client.post(
            reverse(
                "notifications:appointment_whatsapp_send",
                args=[self.appointment.pk, self.setting.pk],
            )
        )

        return WhatsAppMessageLog.objects.get(whatsapp_message_id="SMabc")

    def test_the_callback_url_is_sent_to_twilio(self):
        self.enviar()

        self.assertIn("StatusCallback", self.enviados[0])
        self.assertTrue(
            self.enviados[0]["StatusCallback"].startswith("https://priarantes.com")
        )

    @override_settings(SITE_URL="http://localhost:8000")
    def test_no_callback_is_requested_from_an_unreachable_address(self):
        # A Twilio não alcança localhost; pedir-lhe que tente só enche os
        # registos dela de erros.
        self.enviar()

        self.assertNotIn("StatusCallback", self.enviados[0])

    def test_before_the_callback_the_state_is_only_accepted(self):
        registo = self.enviar()

        self.assertEqual(registo.status, WhatsAppMessageLog.STATUS_SUCCESS)
        self.assertEqual(registo.delivery_status, "")
        self.assertEqual(registo.get_delivery_label(), "Aceite pela Twilio")

    def test_a_delivery_confirmation_is_recorded(self):
        registo = self.enviar()

        twilio_callbacks.record_status("SMabc", "delivered")
        registo.refresh_from_db()

        self.assertEqual(registo.get_delivery_label(), "Entregue")
        self.assertFalse(registo.delivery_failed())
        self.assertIsNotNone(registo.delivery_updated_at)

    def test_a_delivery_failure_is_recorded_with_its_code(self):
        # O caso que motivou isto: a Twilio aceita, e a mensagem nunca chega.
        registo = self.enviar()

        twilio_callbacks.record_status("SMabc", "undelivered", error_code="63016")
        registo.refresh_from_db()

        self.assertTrue(registo.delivery_failed())
        self.assertEqual(registo.delivery_error_code, "63016")
        self.assertEqual(registo.get_delivery_label(), "Não entregue")

    def test_an_unknown_sid_is_ignored_without_breaking(self):
        # A conta Twilio pode ser partilhada com outro ambiente.
        self.assertIsNone(twilio_callbacks.record_status("SMdesconhecido", "delivered"))

    def test_an_empty_sid_is_ignored(self):
        self.assertIsNone(twilio_callbacks.record_status("", "delivered"))

    def test_the_failure_shows_up_on_the_appointment_page(self):
        self.enviar()
        twilio_callbacks.record_status("SMabc", "failed", error_code="63003")

        resposta = self.client.get(
            reverse("notifications:appointment_followups", args=[self.appointment.pk])
        )

        self.assertContains(resposta, "Falhou")
        self.assertContains(resposta, "63003")


# `testserver` é o único host que o runner de testes aceita sem mexer em
# ALLOWED_HOSTS, e a assinatura da Twilio cobre o URL completo.
@override_settings(**TWILIO_LIGADA, SITE_URL="https://testserver")
class TwilioWebhookTests(TwilioBase):
    """O endereço é público: só a Twilio o pode usar."""

    HOST = "https://testserver"

    def setUp(self):
        super().setUp()

        self.url = reverse("notifications:twilio_status")
        self.registo = WhatsAppMessageLog.objects.create(
            appointment=self.marcacao(),
            provider=WhatsAppMessageLog.PROVIDER_TWILIO,
            event_type="appointment_confirmed",
            status=WhatsAppMessageLog.STATUS_SUCCESS,
            template_name="texto-livre",
            recipient_phone="whatsapp:+351910000000",
            whatsapp_message_id="SMxyz",
        )

    def assinar(self, url, dados):
        import base64
        import hmac
        from hashlib import sha1

        corpo = "".join(f"{k}{dados[k]}" for k in sorted(dados))

        return base64.b64encode(
            hmac.new(
                settings.TWILIO_AUTH_TOKEN.encode(),
                (url + corpo).encode(),
                sha1,
            ).digest()
        ).decode()

    def test_a_signed_request_updates_the_record(self):
        dados = {"MessageSid": "SMxyz", "MessageStatus": "delivered"}
        url = f"{self.HOST}{self.url}"

        resposta = self.client.post(
            self.url,
            data=dados,
            HTTP_X_TWILIO_SIGNATURE=self.assinar(url, dados),
            secure=True,
        )

        self.registo.refresh_from_db()

        self.assertEqual(resposta.status_code, 204)
        self.assertEqual(self.registo.delivery_status, "delivered")

    def test_an_unsigned_request_is_refused(self):
        # Sem isto, qualquer pessoa podia marcar mensagens como entregues.
        resposta = self.client.post(
            self.url, data={"MessageSid": "SMxyz", "MessageStatus": "delivered"}
        )

        self.registo.refresh_from_db()

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(self.registo.delivery_status, "")

    def test_a_wrongly_signed_request_is_refused(self):
        resposta = self.client.post(
            self.url,
            data={"MessageSid": "SMxyz", "MessageStatus": "delivered"},
            HTTP_X_TWILIO_SIGNATURE="assinatura-inventada",
            secure=True,
        )

        self.assertEqual(resposta.status_code, 403)

    def test_tampering_with_the_body_invalidates_the_signature(self):
        dados = {"MessageSid": "SMxyz", "MessageStatus": "delivered"}
        url = f"{self.HOST}{self.url}"
        assinatura = self.assinar(url, dados)

        resposta = self.client.post(
            self.url,
            data={"MessageSid": "SMxyz", "MessageStatus": "failed"},
            HTTP_X_TWILIO_SIGNATURE=assinatura,
            secure=True,
        )

        self.assertEqual(resposta.status_code, 403)

    def test_the_webhook_does_not_require_a_login(self):
        # Quem chama é a Twilio, não um browser com sessão.
        self.client.logout()

        dados = {"MessageSid": "SMxyz", "MessageStatus": "read"}
        url = f"{self.HOST}{self.url}"

        resposta = self.client.post(
            self.url,
            data=dados,
            HTTP_X_TWILIO_SIGNATURE=self.assinar(url, dados),
            secure=True,
        )

        self.assertEqual(resposta.status_code, 204)
