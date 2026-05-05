from datetime import date, timedelta, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from appointments.appointment_services import AppointmentService
from appointments.availability import AvailabilityService
from appointments.models import (
    Appointment,
    AppointmentLog,
    AppointmentReminderLog,
    BusinessHour,
    Customer,
    ScheduleBlock,
    Service,
)
from appointments.selectors import AppointmentFilters, AppointmentSelectors
from appointments.use_cases import ConfirmAppointmentUseCase, CompleteAppointmentUseCase


class CriticalArchitectureTestMixin:
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
        self.service = Service.objects.create(
            name="Podologia",
            description="Critical path service",
            duration_minutes=60,
            price=Decimal("50.00"),
            is_active=True,
        )
        self.short_service = Service.objects.create(
            name="Consulta curta",
            description="Short service",
            duration_minutes=30,
            price=Decimal("25.00"),
            is_active=True,
        )
        self.appointment_date = timezone.localdate() + timedelta(days=14)
        BusinessHour.objects.create(
            weekday=self.appointment_date.weekday(),
            start_time=time(9, 0),
            end_time=time(18, 0),
            is_active=True,
        )

    def create_appointment(self, **overrides):
        data = {
            "customer": self.customer,
            "service": self.service,
            "created_by": self.admin_user,
            "date": self.appointment_date,
            "start_time": time(10, 0),
            "status": Appointment.STATUS_SCHEDULED,
            "notes": "Critical regression appointment",
        }
        data.update(overrides)
        return Appointment.objects.create(**data)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
    SITE_URL="http://testserver",
)
class AvailabilityCriticalTests(CriticalArchitectureTestMixin, TestCase):
    def test_available_slots_exclude_existing_appointments_and_schedule_blocks(self):
        self.create_appointment(start_time=time(10, 0), service=self.service)
        ScheduleBlock.objects.create(
            title="Almoço",
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=self.appointment_date,
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_active=True,
        )

        slots = AvailabilityService.get_available_slots(self.service, self.appointment_date)
        slot_values = {slot["value"] for slot in slots}

        self.assertIn("09:00", slot_values)
        self.assertNotIn("09:30", slot_values, "09:30-10:30 overlaps the 10:00 appointment")
        self.assertNotIn("10:00", slot_values)
        self.assertNotIn("10:30", slot_values, "10:30-11:30 overlaps the 10:00 appointment")
        self.assertNotIn("11:30", slot_values, "11:30-12:30 overlaps the 12:00 block")
        self.assertNotIn("12:00", slot_values)
        self.assertNotIn("12:30", slot_values)
        self.assertIn("13:00", slot_values)

    def test_appointment_validation_rejects_business_hour_overflow(self):
        appointment = Appointment(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.appointment_date,
            start_time=time(17, 30),
            status=Appointment.STATUS_SCHEDULED,
        )

        with self.assertRaisesMessage(ValidationError, "A marcação está fora do horário"):
            appointment.full_clean()

    def test_appointment_validation_rejects_overlapping_appointment(self):
        self.create_appointment(start_time=time(10, 0), service=self.service)

        overlapping = Appointment(
            customer=self.second_customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.appointment_date,
            start_time=time(10, 30),
            status=Appointment.STATUS_SCHEDULED,
        )

        with self.assertRaisesMessage(ValidationError, "conflito com outra marcação"):
            overlapping.full_clean()

    def test_cancelled_appointments_do_not_block_availability(self):
        self.create_appointment(
            start_time=time(10, 0),
            service=self.service,
            status=Appointment.STATUS_CANCELLED,
            cancellation_reason="Cancelado para libertar horário.",
            cancelled_at=timezone.now(),
        )

        slots = AvailabilityService.get_available_slots(self.service, self.appointment_date)
        slot_values = {slot["value"] for slot in slots}

        self.assertIn("10:00", slot_values)

    def test_recurring_schedule_block_applies_to_matching_weekday_only(self):
        block = ScheduleBlock.objects.create(
            title="Pausa recorrente",
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=self.appointment_date - timedelta(days=7),
            start_time=time(15, 0),
            end_time=time(16, 0),
            is_recurring=True,
            recurring_weekdays=str(self.appointment_date.weekday()),
            is_active=True,
        )

        self.assertTrue(block.applies_to_date(self.appointment_date))
        self.assertFalse(block.applies_to_date(self.appointment_date + timedelta(days=1)))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
    SITE_URL="http://testserver",
)
class AppointmentCreationCriticalTests(CriticalArchitectureTestMixin, TestCase):
    def test_creation_service_creates_appointment_log_and_confirmation_email(self):
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(9, 0),
            created_by=self.admin_user,
            send_email=True,
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.appointment)
        self.assertTrue(
            AppointmentLog.objects.filter(
                appointment=result.appointment,
                action=AppointmentLog.ACTION_CREATE,
                performed_by=self.admin_user,
            ).exists()
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(result.appointment.reference_code, mail.outbox[0].body)

    def test_creation_service_returns_failure_for_double_booking(self):
        self.create_appointment(start_time=time(9, 0), service=self.service)

        result = AppointmentService.create_appointment(
            customer=self.second_customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(9, 30),
            created_by=self.admin_user,
            send_email=True,
        )

        self.assertFalse(result.success)
        self.assertIn("conflito", result.message)
        self.assertEqual(Appointment.objects.exclude(status=Appointment.STATUS_CANCELLED).count(), 1)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
)
class AppointmentUseCaseCriticalTests(CriticalArchitectureTestMixin, TestCase):
    def test_confirm_use_case_changes_status_logs_and_sends_email(self):
        appointment = self.create_appointment(status=Appointment.STATUS_SCHEDULED)

        result = ConfirmAppointmentUseCase.execute(
            appointment=appointment,
            user=self.admin_user,
            send_email=True,
        )

        appointment.refresh_from_db()

        self.assertTrue(result.success)
        self.assertEqual(appointment.status, Appointment.STATUS_CONFIRMED)
        self.assertTrue(
            AppointmentLog.objects.filter(
                appointment=appointment,
                action=AppointmentLog.ACTION_CONFIRM,
                performed_by=self.admin_user,
            ).exists()
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_complete_use_case_only_allows_confirmed_appointments(self):
        scheduled = self.create_appointment(status=Appointment.STATUS_SCHEDULED)

        rejected = CompleteAppointmentUseCase.execute(
            appointment=scheduled,
            user=self.admin_user,
        )

        scheduled.refresh_from_db()

        self.assertFalse(rejected.success)
        self.assertEqual(scheduled.status, Appointment.STATUS_SCHEDULED)

        scheduled.status = Appointment.STATUS_CONFIRMED
        scheduled.save(update_fields=["status", "updated_at"])

        accepted = CompleteAppointmentUseCase.execute(
            appointment=scheduled,
            user=self.admin_user,
        )

        scheduled.refresh_from_db()

        self.assertTrue(accepted.success)
        self.assertEqual(scheduled.status, Appointment.STATUS_COMPLETED)
        self.assertTrue(
            AppointmentLog.objects.filter(
                appointment=scheduled,
                action=AppointmentLog.ACTION_COMPLETE,
            ).exists()
        )


class AppointmentSelectorsCriticalTests(CriticalArchitectureTestMixin, TestCase):
    def test_list_appointments_filters_by_status_service_search_and_reminders(self):
        appointment = self.create_appointment(
            customer=self.customer,
            service=self.service,
            status=Appointment.STATUS_CONFIRMED,
            reminder_24h_sent_at=timezone.now(),
        )
        self.create_appointment(
            customer=self.second_customer,
            service=self.short_service,
            start_time=time(11, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        filters = AppointmentFilters(
            q="Maria",
            status=Appointment.STATUS_CONFIRMED,
            service=str(self.service.pk),
            reminder="24h_sent",
        )

        results = list(AppointmentSelectors.list_appointments(filters))

        self.assertEqual(results, [appointment])


class ReminderLogModelCriticalTests(CriticalArchitectureTestMixin, TestCase):
    def test_reminder_log_records_type_status_and_appointment(self):
        appointment = self.create_appointment(status=Appointment.STATUS_CONFIRMED)

        log = AppointmentReminderLog.objects.create(
            appointment=appointment,
            reminder_type=AppointmentReminderLog.REMINDER_TYPE_24H,
            status=AppointmentReminderLog.STATUS_SUCCESS,
        )

        self.assertEqual(log.appointment, appointment)
        self.assertEqual(log.reminder_type, AppointmentReminderLog.REMINDER_TYPE_24H)
        self.assertEqual(log.status, AppointmentReminderLog.STATUS_SUCCESS)
