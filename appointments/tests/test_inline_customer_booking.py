import re
from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from appointments.models import Appointment, BusinessHour, Customer
from appointments.tests.factories import create_test_service


class InlineCustomerBookingTests(TestCase):
    # A marcação interna deve permitir registar o cliente na mesma submissão,
    # sem obrigar a sair para a página de clientes.

    def setUp(self):
        User = get_user_model()

        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.existing_customer = Customer.objects.create(
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

        self.client.force_login(self.admin_user)
        self.url = reverse("appointments:appointment_create")

    def post_appointment(self, **overrides):
        data = {
            "customer_mode": "existing",
            "customer": self.existing_customer.pk,
            "service": self.service.pk,
            "date": self.appointment_date.isoformat(),
            "start_time": "10:00",
            "status": Appointment.STATUS_SCHEDULED,
            "notes": "",
            "new_customer_name": "",
            "new_customer_phone": "",
            "new_customer_email": "",
        }
        data.update(overrides)

        return self.client.post(self.url, data=data)

    def test_customer_mode_is_the_first_thing_on_the_form(self):
        html = self.client.get(self.url).content.decode()

        posicao_radio = html.find('name="customer_mode"')
        posicao_select = html.find('id="id_customer"')
        posicao_servico = html.find('id="id_service"')

        self.assertLess(posicao_radio, posicao_select)
        self.assertLess(posicao_radio, posicao_servico)

    def test_new_customer_fields_start_hidden_and_have_stable_hooks(self):
        # O JS alterna estes contentores. Se os atributos desaparecerem, o
        # select de clientes deixa de ser escondido ao escolher "novo".
        html = self.client.get(self.url).content.decode()

        self.assertIn("data-customer-existing", html)
        self.assertIn("data-customer-new hidden", html)

    def test_new_customer_block_stays_visible_after_a_validation_error(self):
        response = self.post_appointment(customer_mode="new", customer="")

        self.assertEqual(response.status_code, 200)

        # O radio tem de voltar marcado em "new", senão o JS repõe o modo
        # "existente" e os campos preenchidos desaparecem do ecrã.
        radio_novo = re.search(
            r'<input[^>]*value="new"[^>]*>',
            response.content.decode(),
        )

        self.assertIsNotNone(radio_novo)
        self.assertIn("checked", radio_novo.group(0))

    def test_missing_service_shows_a_field_error_instead_of_crashing(self):
        # Appointment.clean() delega em AvailabilityService, que acedia a
        # appointment.service sem verificar service_id e rebentava com 500.
        response = self.post_appointment(service="")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)
        # Compara a chave do erro e não o texto: a mensagem é traduzida e o
        # idioma ativo depende da ordem dos testes.
        self.assertIn("service", response.context["form"].errors)

    def test_existing_customer_flow_still_works(self):
        response = self.post_appointment()

        self.assertRedirects(response, reverse("appointments:appointment_list"))
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Appointment.objects.first().customer, self.existing_customer)
        self.assertEqual(Customer.objects.count(), 1)

    def test_new_customer_is_created_with_the_appointment(self):
        response = self.post_appointment(
            customer_mode="new",
            customer="",
            new_customer_name="Ana Costa",
            new_customer_phone="+351920000000",
            new_customer_email="ana@example.com",
        )

        self.assertRedirects(response, reverse("appointments:appointment_list"))
        self.assertEqual(Customer.objects.count(), 2)

        appointment = Appointment.objects.get()
        self.assertEqual(appointment.customer.full_name, "Ana Costa")
        self.assertEqual(appointment.customer.phone, "+351920000000")
        self.assertEqual(appointment.customer.email, "ana@example.com")

    def test_new_customer_without_email_is_accepted(self):
        self.post_appointment(
            customer_mode="new",
            customer="",
            new_customer_name="Sem Email",
            new_customer_phone="+351921111111",
        )

        appointment = Appointment.objects.get()
        self.assertEqual(appointment.customer.email, "")

    def test_known_phone_reuses_the_existing_customer(self):
        # find_or_create_customer deduplica, por isso registar "novo" com um
        # telefone já conhecido não cria um segundo registo.
        self.post_appointment(
            customer_mode="new",
            customer="",
            new_customer_name="Maria Silva",
            new_customer_phone="+351910000000",
        )

        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Appointment.objects.get().customer, self.existing_customer)

    def test_new_customer_requires_name_and_phone(self):
        response = self.post_appointment(customer_mode="new", customer="")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Indique o nome do cliente novo.")
        self.assertContains(response, "Indique o telefone do cliente novo.")
        self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 1)

    def test_new_customer_rejects_invalid_phone(self):
        response = self.post_appointment(
            customer_mode="new",
            customer="",
            new_customer_name="Telefone Mau",
            new_customer_phone="123",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 1)

    def test_existing_mode_requires_choosing_a_customer(self):
        response = self.post_appointment(customer="")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selecione o cliente ou registe um novo.")
        self.assertEqual(Appointment.objects.count(), 0)

    def test_conflicting_slot_does_not_leave_a_duplicate_customer(self):
        # Primeira marcação ocupa o horário.
        self.post_appointment()

        # A segunda, com cliente novo, colide e é rejeitada. Reenviar depois
        # noutro horário tem de reaproveitar o cliente já criado.
        self.post_appointment(
            customer_mode="new",
            customer="",
            new_customer_name="Ana Costa",
            new_customer_phone="+351920000000",
        )
        self.post_appointment(
            customer_mode="new",
            customer="",
            new_customer_name="Ana Costa",
            new_customer_phone="+351920000000",
            start_time="14:00",
        )

        self.assertEqual(Customer.objects.filter(full_name="Ana Costa").count(), 1)
        self.assertEqual(Appointment.objects.count(), 2)
