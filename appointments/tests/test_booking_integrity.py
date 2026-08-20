from datetime import time, timedelta
from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from appointments.appointment_services import AppointmentService
from appointments.cancellation_services import AppointmentCancellationService
from appointments.models import Appointment, Customer, ScheduleBlock
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class BookingIntegrityTestMixin:
    def setUp(self):
        User = get_user_model()

        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.second_customer = Customer.objects.create(
            full_name="Ana Costa",
            email="ana@example.com",
            phone="+351920000000",
        )

        self.service = create_test_service()

        self.appointment_date = timezone.localdate() + timedelta(days=14)

        ensure_test_business_hour(weekday=self.appointment_date.weekday())

        ScheduleBlock.objects.filter(
            notes="Almoço",
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            is_recurring=True,
        ).delete()

    def create_appointment(self, **overrides):
        data = {
            "customer": self.customer,
            "service": self.service,
            "created_by": self.admin_user,
            "date": self.appointment_date,
            "start_time": time(10, 0),
            "status": Appointment.STATUS_SCHEDULED,
        }
        data.update(overrides)

        return Appointment.objects.create(**data)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
)
class EmailDeliveryDoesNotBreakOperationsTests(BookingIntegrityTestMixin, TestCase):
    # A failing mail server must never destroy or block a business operation.

    def test_smtp_failure_does_not_roll_back_appointment_creation(self):
        with patch(
            "appointments.appointment_services.send_appointment_confirmation_email",
            side_effect=SMTPException("SMTP unavailable"),
        ):
            with self.assertLogs("appointments.emails", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    result = AppointmentService.create_appointment(
                        customer=self.customer,
                        service=self.service,
                        date=self.appointment_date,
                        start_time=time(10, 0),
                        created_by=self.admin_user,
                        send_email=True,
                    )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.appointment)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_failure_does_not_break_cancellation(self):
        appointment = self.create_appointment()
        reason = "Cliente não poderá comparecer."

        with patch(
            "appointments.cancellation_services.send_appointment_cancelled_email",
            side_effect=SMTPException("SMTP unavailable"),
        ):
            with self.assertLogs("appointments.emails", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    result = AppointmentCancellationService.cancel(
                        appointment=appointment,
                        user=self.admin_user,
                        cancellation_reason=reason,
                    )

        self.assertTrue(result.success)

        appointment.refresh_from_db()

        self.assertEqual(appointment.status, Appointment.STATUS_CANCELLED)
        self.assertEqual(appointment.cancellation_reason, reason)

    def test_confirmation_email_is_not_sent_before_commit(self):
        # Without executing the callbacks the mail must stay unsent, proving the
        # delivery is tied to the commit and not to the creation itself.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=True,
        )

        self.assertTrue(result.success)
        self.assertEqual(len(mail.outbox), 0)


class DoubleBookingDatabaseConstraintTests(BookingIntegrityTestMixin, TestCase):
    # The unique slot constraint is the last defence when two concurrent
    # requests both pass availability validation before either one commits.

    def test_database_rejects_duplicated_active_slot(self):
        self.create_appointment(start_time=time(10, 0))

        duplicated = Appointment(
            customer=self.second_customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.appointment_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
            reference_code="AGD-DUPLIC",
        )

        # bulk_create skips save()/full_clean(), so only the database can reject it.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Appointment.objects.bulk_create([duplicated])

    def test_creation_returns_friendly_message_when_database_rejects_slot(self):
        self.create_appointment(start_time=time(10, 0))

        # Simulates the race: both requests pass validation before either
        # commits, so the constraint is what stops the second insert.
        with patch.object(Appointment, "full_clean", return_value=None):
            result = AppointmentService.create_appointment(
                customer=self.second_customer,
                service=self.service,
                date=self.appointment_date,
                start_time=time(10, 0),
                created_by=self.admin_user,
                send_email=False,
            )

        self.assertFalse(result.success)
        self.assertIn("já não está disponível", result.message)
        self.assertEqual(
            Appointment.objects.exclude(status=Appointment.STATUS_CANCELLED).count(),
            1,
        )

    def test_cancelled_appointment_frees_the_slot(self):
        appointment = self.create_appointment(start_time=time(10, 0))

        appointment.status = Appointment.STATUS_CANCELLED
        appointment.save(update_fields=["status", "updated_at"])

        result = AppointmentService.create_appointment(
            customer=self.second_customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        self.assertTrue(result.success)
        self.assertEqual(
            Appointment.objects.exclude(status=Appointment.STATUS_CANCELLED).count(),
            1,
        )

    def test_confirming_appointment_still_works_with_constraint(self):
        # The constraint condition must not block status transitions of an
        # appointment that is already the only active one in its slot.
        appointment = self.create_appointment(start_time=time(10, 0))

        appointment.status = Appointment.STATUS_CONFIRMED
        appointment.save(update_fields=["status", "updated_at"])

        appointment.refresh_from_db()

        self.assertEqual(appointment.status, Appointment.STATUS_CONFIRMED)
