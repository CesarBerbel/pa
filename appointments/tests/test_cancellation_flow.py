from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.cancellation_services import AppointmentCancellationService
from appointments.models import Appointment, AppointmentLog, BusinessHour, Customer, Service


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
)
class AppointmentCancellationFlowTests(TestCase):
    # Tests the full appointment cancellation flow with required cancellation reason.

    def setUp(self):
        # Create a reusable superuser for internal staff actions.
        User = get_user_model()

        self.superuser = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        # Create a normal customer user.
        self.customer_user = User.objects.create_user(
            email="customer@example.com",
            password="StrongPassword123",
            full_name="Customer User",
        )

        # Create a customer with email to allow cancellation email assertions.
        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
            user=self.customer_user,
        )

        self.service = Service.objects.create(
            name="Podologia",
            description="Service for tests",
            duration_minutes=60,
            price=Decimal("50.00"),
            is_active=True,
        )

        self.appointment_date = timezone.localdate() + timedelta(days=7)

        BusinessHour.objects.create(
            weekday=self.appointment_date.weekday(),
            start_time="09:00",
            end_time="18:00",
            is_active=True,
        )

        self.appointment = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.superuser,
            date=self.appointment_date,
            start_time="10:00",
            status=Appointment.STATUS_SCHEDULED,
            notes="Test appointment",
        )

    def test_cancellation_service_requires_reason(self):
        # Ensure appointments cannot be cancelled without a reason.
        result = AppointmentCancellationService.cancel(
            appointment=self.appointment,
            user=self.superuser,
            cancellation_reason="",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Informe o motivo do cancelamento.")

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.status, Appointment.STATUS_SCHEDULED)
        self.assertEqual(self.appointment.cancellation_reason, "")
        self.assertIsNone(self.appointment.cancelled_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_cancellation_service_saves_reason_sets_cancelled_at_logs_and_sends_email(self):
        # Ensure centralized cancellation saves reason, timestamp, audit log, and email.
        reason = "Cliente não poderá comparecer no horário marcado."

        result = AppointmentCancellationService.cancel(
            appointment=self.appointment,
            user=self.superuser,
            cancellation_reason=reason,
        )

        self.assertTrue(result.success)

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.status, Appointment.STATUS_CANCELLED)
        self.assertEqual(self.appointment.cancellation_reason, reason)
        self.assertIsNotNone(self.appointment.cancelled_at)

        self.assertTrue(
            AppointmentLog.objects.filter(
                appointment=self.appointment,
                action=AppointmentLog.ACTION_CANCEL,
                description__icontains=reason,
            ).exists()
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Marcação cancelada", mail.outbox[0].subject)
        self.assertIn(reason, mail.outbox[0].body)
        self.assertIn(self.appointment.reference_code, mail.outbox[0].body)

    def test_internal_cancel_get_renders_form_without_instance_error(self):
        # Ensure the internal cancellation page opens correctly with regular Form.
        client = Client()
        client.force_login(self.superuser)

        url = reverse(
            "appointments:appointment_cancel",
            kwargs={"pk": self.appointment.pk},
        )

        response = client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Motivo do cancelamento")
        self.assertContains(response, self.appointment.reference_code)

    def test_internal_cancel_post_cancels_with_reason(self):
        # Ensure staff can cancel internally only when a reason is submitted.
        client = Client()
        client.force_login(self.superuser)

        reason = "Cancelamento feito pela equipa após contacto telefónico."

        url = reverse(
            "appointments:appointment_cancel",
            kwargs={"pk": self.appointment.pk},
        )

        response = client.post(
            url,
            data={
                "cancellation_reason": reason,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.status, Appointment.STATUS_CANCELLED)
        self.assertEqual(self.appointment.cancellation_reason, reason)
        self.assertIsNotNone(self.appointment.cancelled_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(reason, mail.outbox[0].body)

    def test_internal_cancel_post_rejects_short_reason(self):
        # Ensure staff cannot cancel with an invalid short reason.
        client = Client()
        client.force_login(self.superuser)

        url = reverse(
            "appointments:appointment_cancel",
            kwargs={"pk": self.appointment.pk},
        )

        response = client.post(
            url,
            data={
                "cancellation_reason": "abc",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe um motivo com pelo menos 5 caracteres.")

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.status, Appointment.STATUS_SCHEDULED)
        self.assertEqual(self.appointment.cancellation_reason, "")
        self.assertIsNone(self.appointment.cancelled_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_public_cancel_by_reference_code_requires_reason(self):
        # Ensure public cancellation by reference code requires a reason.
        client = Client()

        url = reverse("appointments:public_cancel")

        response = client.post(
            url,
            data={
                "reference_code": self.appointment.reference_code,
                "cancellation_reason": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo é obrigatório.")

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.status, Appointment.STATUS_SCHEDULED)
        self.assertEqual(len(mail.outbox), 0)

    def test_public_cancel_by_reference_code_saves_reason_and_sends_email(self):
        # Ensure public cancellation form saves the reason and sends it by email.
        client = Client()

        reason = "Surgiu um imprevisto familiar."

        url = reverse("appointments:public_cancel")

        response = client.post(
            url,
            data={
                "reference_code": self.appointment.reference_code,
                "cancellation_reason": reason,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.status, Appointment.STATUS_CANCELLED)
        self.assertEqual(self.appointment.cancellation_reason, reason)
        self.assertIsNotNone(self.appointment.cancelled_at)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(reason, mail.outbox[0].body)

    def test_public_cancel_by_direct_code_url_saves_reason_and_sends_email(self):
        # Ensure direct cancellation URL also requires and saves cancellation reason.
        client = Client()

        reason = "Não consigo comparecer nesta data."

        url = reverse(
            "appointments:public_cancel_by_code",
            kwargs={"reference_code": self.appointment.reference_code},
        )

        response = client.post(
            url,
            data={
                "cancellation_reason": reason,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        self.appointment.refresh_from_db()

        self.assertEqual(self.appointment.status, Appointment.STATUS_CANCELLED)
        self.assertEqual(self.appointment.cancellation_reason, reason)
        self.assertIsNotNone(self.appointment.cancelled_at)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(reason, mail.outbox[0].body)