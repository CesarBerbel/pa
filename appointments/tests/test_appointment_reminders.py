from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from appointments.models import Appointment, BusinessHour, Customer, Service


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
    SITE_URL="http://testserver",
)
class AppointmentReminderCommandTests(TestCase):
    # Tests appointment reminder command behavior and duplicate protection.

    def setUp(self):
        # Create base data used by all reminder tests.
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

        self.service = Service.objects.create(
            name="Podologia",
            description="Test service",
            duration_minutes=60,
            price=Decimal("50.00"),
            is_active=True,
        )

    def create_business_hour_for_date(self, appointment_date):
        # Ensure appointment validation passes for the selected date.
        BusinessHour.objects.get_or_create(
            weekday=appointment_date.weekday(),
            defaults={
                "start_time": "00:00",
                "end_time": "23:59",
                "is_active": True,
            },
        )

    def create_appointment(self, appointment_datetime, status=Appointment.STATUS_CONFIRMED):
        # Create an appointment at the desired date and time.
        appointment_date = appointment_datetime.date()
        appointment_time = appointment_datetime.time().replace(second=0, microsecond=0)

        self.create_business_hour_for_date(appointment_date)

        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=appointment_date,
            start_time=appointment_time,
            status=status,
            notes="Reminder test appointment",
        )

    def test_24h_reminder_is_sent_only_once(self):
        # Ensure the 24h reminder is sent once and not duplicated.
        appointment_datetime = timezone.localtime() + timedelta(hours=24)

        appointment = self.create_appointment(
            appointment_datetime=appointment_datetime,
            status=Appointment.STATUS_CONFIRMED,
        )

        call_command("send_appointment_reminders")

        appointment.refresh_from_db()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(appointment.reminder_24h_sent_at)
        self.assertIsNone(appointment.reminder_2h_sent_at)

        call_command("send_appointment_reminders")

        appointment.refresh_from_db()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(appointment.reminder_24h_sent_at)
        self.assertIsNone(appointment.reminder_2h_sent_at)

    def test_2h_reminder_is_sent_only_once(self):
        # Ensure the 2h reminder is sent once and not duplicated.
        appointment_datetime = timezone.localtime() + timedelta(hours=2)

        appointment = self.create_appointment(
            appointment_datetime=appointment_datetime,
            status=Appointment.STATUS_CONFIRMED,
        )

        call_command("send_appointment_reminders")

        appointment.refresh_from_db()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNone(appointment.reminder_24h_sent_at)
        self.assertIsNotNone(appointment.reminder_2h_sent_at)

        call_command("send_appointment_reminders")

        appointment.refresh_from_db()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNone(appointment.reminder_24h_sent_at)
        self.assertIsNotNone(appointment.reminder_2h_sent_at)

    def test_cancelled_appointment_does_not_receive_reminder(self):
        # Ensure cancelled appointments never receive reminder emails.
        appointment_datetime = timezone.localtime() + timedelta(hours=24)

        appointment = self.create_appointment(
            appointment_datetime=appointment_datetime,
            status=Appointment.STATUS_CANCELLED,
        )

        call_command("send_appointment_reminders")

        appointment.refresh_from_db()

        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(appointment.reminder_24h_sent_at)
        self.assertIsNone(appointment.reminder_2h_sent_at)

    def test_scheduled_unconfirmed_appointment_does_not_receive_reminder(self):
        # Ensure scheduled but not confirmed appointments do not receive reminders.
        appointment_datetime = timezone.localtime() + timedelta(hours=24)

        appointment = self.create_appointment(
            appointment_datetime=appointment_datetime,
            status=Appointment.STATUS_SCHEDULED,
        )

        call_command("send_appointment_reminders")

        appointment.refresh_from_db()

        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(appointment.reminder_24h_sent_at)
        self.assertIsNone(appointment.reminder_2h_sent_at)