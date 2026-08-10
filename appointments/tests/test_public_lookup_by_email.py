from datetime import time

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from appointments.appointment_services import AppointmentService
from appointments.models import Appointment
from appointments.tests.tests import AppointmentTestSetupMixin


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
    SITE_URL="https://testserver",
)
class PublicAppointmentLookupByEmailTests(AppointmentTestSetupMixin, TestCase):
    # Tests for public appointment lookup by reference code or email.

    def setUp(self):
        self.appointment_date = self.get_future_business_date(weekday=0)
        self.create_base_data(appointment_date=self.appointment_date)

        scheduled_result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )
        self.scheduled_appointment = scheduled_result.appointment

        confirmed_result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(11, 0),
            created_by=self.admin_user,
            status=Appointment.STATUS_CONFIRMED,
            send_email=False,
        )
        self.confirmed_appointment = confirmed_result.appointment

        completed_result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(12, 0),
            created_by=self.admin_user,
            status=Appointment.STATUS_COMPLETED,
            send_email=False,
        )
        self.completed_appointment = completed_result.appointment

        cancelled_result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(13, 0),
            created_by=self.admin_user,
            status=Appointment.STATUS_CANCELLED,
            send_email=False,
        )
        self.cancelled_appointment = cancelled_result.appointment

    def test_reference_code_lookup_still_shows_appointment(self):
        # Ensure the existing reference code lookup behavior remains available.
        response = self.client.post(
            reverse("appointments:public_appointment_lookup"),
            data={
                "reference_code": self.scheduled_appointment.reference_code,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["appointment"],
            self.scheduled_appointment,
        )
        self.assertContains(response, self.scheduled_appointment.reference_code)

    def test_email_lookup_sends_open_appointment_details_and_reference_codes(self):
        # Ensure email lookup sends only scheduled/confirmed appointments to the email owner.
        response = self.client.post(
            reverse("appointments:public_appointment_lookup"),
            data={
                "email": " Cliente@Test.COM ",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:public_appointment_lookup"),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["cliente@test.com"])
        self.assertIn(self.scheduled_appointment.reference_code, mail.outbox[0].body)
        self.assertIn(self.confirmed_appointment.reference_code, mail.outbox[0].body)
        self.assertNotIn(self.completed_appointment.reference_code, mail.outbox[0].body)
        self.assertNotIn(self.cancelled_appointment.reference_code, mail.outbox[0].body)
        self.assertIn("https://testserver", mail.outbox[0].body)

    def test_email_lookup_without_open_appointments_does_not_send_email(self):
        # Ensure the public page does not reveal whether an email exists and sends nothing when no open appointment exists.
        response = self.client.post(
            reverse("appointments:public_appointment_lookup"),
            data={
                "email": "sem-marcacao@test.com",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:public_appointment_lookup"),
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_lookup_requires_exactly_one_method(self):
        # Ensure users do not submit both lookup methods at the same time.
        response = self.client.post(
            reverse("appointments:public_appointment_lookup"),
            data={
                "reference_code": self.scheduled_appointment.reference_code,
                "email": "cliente@test.com",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Indique apenas uma das alternativas: código da marcação ou email.",
        )
        self.assertEqual(len(mail.outbox), 0)
