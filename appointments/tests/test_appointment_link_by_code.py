"""O link que vai nas mensagens de WhatsApp abre a marcação sem escrever nada.

O ponto delicado é a durabilidade. Uma mensagem de WhatsApp fica na conversa e
é reaberta dias depois, quando a marcação já pode ter sido confirmada ou
mudada de hora. Um link que morre nessa altura não serve — e é por isso que
este não usa o token assinado dos emails, que leva o `updated_at` dentro.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from notifications.whatsapp_common import build_context, get_sample_context


class AppointmentLinkByCodeTests(TestCase):
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

        self.url = reverse(
            "appointments:public_appointment_by_code",
            kwargs={"reference_code": self.appointment.reference_code},
        )

    def test_the_link_opens_the_appointment(self):
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["appointment"], self.appointment)
        self.assertContains(resposta, self.appointment.reference_code)

    def test_the_link_needs_no_login(self):
        # A cliente não tem conta: o link tem de abrir tal como chega.
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)

    def test_the_link_still_works_after_the_appointment_changes(self):
        # É isto que o token assinado dos emails não aguenta: basta a
        # profissional confirmar o pedido para o link deixar de servir.
        self.appointment.status = Appointment.STATUS_CONFIRMED
        self.appointment.save(update_fields=["status"])

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["appointment"], self.appointment)

    def test_a_lowercase_code_still_finds_it(self):
        url = reverse(
            "appointments:public_appointment_by_code",
            kwargs={"reference_code": self.appointment.reference_code.lower()},
        )

        resposta = self.client.get(url)

        self.assertEqual(resposta.context["appointment"], self.appointment)

    def test_an_unknown_code_explains_itself_instead_of_404(self):
        url = reverse(
            "appointments:public_appointment_by_code",
            kwargs={"reference_code": "AGD-XXXXXX"},
        )

        resposta = self.client.get(url)

        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.context.get("appointment"))

    def test_the_lookup_form_gets_out_of_the_way(self):
        # Chegando aqui pelo link da mensagem, a marcação está no ecrã: pedir
        # o código outra vez era pedir o que já se vê.
        html = self.client.get(self.url).content.decode()

        self.assertNotIn("Consulte diretamente pelo código", html)
        self.assertIn(self.appointment.reference_code, html)

    def test_an_unknown_code_still_offers_the_form(self):
        # Aqui não há nada para mostrar, e o formulário é a saída: permite
        # tentar outro código em vez de deixar a pessoa num beco.
        url = reverse(
            "appointments:public_appointment_by_code",
            kwargs={"reference_code": "AGD-XXXXXX"},
        )

        html = self.client.get(url).content.decode()

        self.assertIn("Consulte diretamente pelo código", html)


class WhatsAppLinkContextTests(TestCase):
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

    def test_the_context_carries_the_link(self):
        contexto = build_context(self.appointment)

        self.assertIn("appointment_link", contexto)
        self.assertIn(self.appointment.reference_code, contexto["appointment_link"])

    def test_the_link_is_absolute(self):
        # Uma mensagem de WhatsApp não tem página de onde partir: um caminho
        # relativo não é clicável em lado nenhum.
        contexto = build_context(self.appointment)

        self.assertTrue(contexto["appointment_link"].startswith("http"))

    def test_the_link_points_at_the_public_page(self):
        contexto = build_context(self.appointment)

        esperado = reverse(
            "appointments:public_appointment_by_code",
            kwargs={"reference_code": self.appointment.reference_code},
        )

        self.assertTrue(contexto["appointment_link"].endswith(esperado))

    def test_the_sample_context_has_it_too(self):
        # O ecrã de configuração pré-visualiza com este contexto: sem a
        # variável, a pré-visualização mostrava um buraco onde vai o link.
        self.assertIn("appointment_link", get_sample_context())

    def test_the_rendered_message_contains_a_working_link(self):
        from notifications.whatsapp_common import render_text

        texto = render_text(
            "Veja aqui: {{ appointment_link }} — obrigada.",
            build_context(self.appointment),
        )

        endereco = texto.split("Veja aqui: ")[1].split(" —")[0]
        caminho = endereco.split("priarantes.com")[-1]

        resposta = self.client.get(caminho)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["appointment"], self.appointment)
