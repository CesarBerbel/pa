from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from appointments.models import Appointment, AppointmentLog, BusinessHour, Customer
from appointments.tests.factories import create_test_service


class InternalCreationStatusTests(TestCase):
    """O estado com que nasce uma marcação criada na área interna.

    Quem a cria já falou com a cliente: a marcação está combinada antes de
    chegar ao formulário. Nascer "Agendada" obrigava a confirmá-la a seguir,
    noutro ecrã, para registar o que já se sabia no momento em que se gravou.
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

        return self.client.post(self.url, data)

    def test_the_form_opens_already_on_confirmed(self):
        # É o valor que o formulário submete quando ninguém lhe toca.
        resposta = self.client.get(self.url)

        self.assertEqual(
            resposta.context["form"]["status"].value(),
            Appointment.STATUS_CONFIRMED,
        )

    def test_an_appointment_created_internally_is_born_confirmed(self):
        self.post_appointment()

        marcacao = Appointment.objects.get()

        self.assertEqual(marcacao.status, Appointment.STATUS_CONFIRMED)
        self.assertEqual(marcacao.origin, Appointment.ORIGIN_INTERNAL)
        self.assertEqual(marcacao.created_by, self.user)

    def test_the_audit_trail_records_the_state_it_was_born_in(self):
        self.post_appointment()

        registo = AppointmentLog.objects.get(action=AppointmentLog.ACTION_CREATE)

        self.assertEqual(registo.source, AppointmentLog.SOURCE_INTERNAL)
        self.assertIn("Confirmado", str(registo.changes))

    def test_a_different_state_chosen_on_purpose_is_kept(self):
        # Confirmado é o ponto de partida, não uma imposição: uma visita
        # registada depois de acontecer entra noutro estado.
        self.post_appointment(status=Appointment.STATUS_SCHEDULED)

        self.assertEqual(Appointment.objects.get().status, Appointment.STATUS_SCHEDULED)

    def test_public_bookings_are_untouched(self):
        # Uma marcação feita pelo site continua a precisar de confirmação: quem
        # a criou foi a cliente, e ninguém a viu ainda deste lado.
        from appointments.appointment_services import AppointmentService

        resultado = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(11, 0),
            created_by=self.user,
            origin=Appointment.ORIGIN_PUBLIC,
        )

        self.assertTrue(resultado.success)
        self.assertEqual(resultado.appointment.status, Appointment.STATUS_SCHEDULED)
