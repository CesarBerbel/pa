from datetime import date, time
from freezegun import freeze_time
from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from appointments.appointment_services import AppointmentService
from appointments.cancellation_services import AppointmentCancellationService
from appointments.models import (
    Appointment,
    AppointmentLog,
    BusinessHour,
    Customer,
    ScheduleBlock,
    Service,
)
from appointments.forms import ScheduleBlockForm


class AppointmentTestSetupMixin:
    # Shared test data for appointment tests.

    def create_base_data(self):
        User = get_user_model()

        self.admin_user = User.objects.create_superuser(
            email="admin@test.com",
            password="testpass123",
            full_name="Admin User",
        )

        self.normal_user = User.objects.create_user(
            email="cliente@test.com",
            password="testpass123",
            full_name="Cliente User",
        )

        self.customer = Customer.objects.create(
            full_name="Cliente Teste",
            email="cliente@test.com",
            phone="+351917777777",
            user=self.normal_user,
        )

        self.service = Service.objects.create(
            name="Podologia",
            duration_minutes=60,
            price="50.00",
            is_active=True,
        )

        BusinessHour.objects.create(
            weekday=0,
            start_time=time(9, 0),
            end_time=time(18, 0),
            is_active=True,
        )

        self.appointment_date = date(2026, 5, 4)


class AppointmentServiceTests(AppointmentTestSetupMixin, TestCase):
    # Tests for appointment creation business rules.

    def setUp(self):
        self.create_base_data()

    def test_create_valid_appointment(self):
        # Ensure a valid appointment can be created.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.appointment)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_prevent_conflicting_appointment(self):
        # Ensure overlapping appointments are blocked.
        first_result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        self.assertTrue(first_result.success)

        second_customer = Customer.objects.create(
            full_name="Segundo Cliente",
            email="segundo@test.com",
            phone="+351918888888",
        )

        second_result = AppointmentService.create_appointment(
            customer=second_customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 30),
            created_by=self.admin_user,
            send_email=False,
        )

        self.assertFalse(second_result.success)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_prevent_appointment_outside_business_hours(self):
        # Ensure appointments outside business hours are blocked.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(18, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        self.assertFalse(result.success)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_prevent_appointment_inside_schedule_block(self):
        # Ensure appointments inside blocked periods are blocked.
        ScheduleBlock.objects.create(
            title="Lunch break",
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=self.appointment_date,
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_full_day=False,
            is_active=True,
        )

        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(12, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        self.assertFalse(result.success)
        self.assertEqual(Appointment.objects.count(), 0)


class AppointmentCancellationServiceTests(AppointmentTestSetupMixin, TestCase):
    # Tests for appointment cancellation business rules.

    def setUp(self):
        self.create_base_data()

    def create_appointment_with_status(self, status):
        # Helper to create an appointment with a specific status.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            status=status,
            send_email=False,
        )

        return result.appointment

    def test_cancel_scheduled_appointment(self):
        # Ensure scheduled appointments can be cancelled.
        appointment = self.create_appointment_with_status(
            Appointment.STATUS_SCHEDULED,
        )

        result = AppointmentCancellationService.cancel(
            appointment=appointment,
            user=self.normal_user,
            cancellation_reason="Cliente solicitou o cancelamento.",
        )

        appointment.refresh_from_db()

        self.assertTrue(result.success)
        self.assertEqual(appointment.status, Appointment.STATUS_CANCELLED)

    def test_prevent_normal_user_from_cancelling_confirmed_appointment(self):
        # Ensure normal users cannot cancel confirmed appointments.
        appointment = self.create_appointment_with_status(
            Appointment.STATUS_CONFIRMED,
        )

        result = AppointmentCancellationService.cancel(
            appointment=appointment,
            user=self.normal_user,
            cancellation_reason="Cliente solicitou o cancelamento.",
        )

        appointment.refresh_from_db()

        self.assertFalse(result.success)
        self.assertEqual(appointment.status, Appointment.STATUS_CONFIRMED)

    def test_allow_admin_to_cancel_confirmed_appointment(self):
        # Ensure admin users can cancel confirmed appointments.
        appointment = self.create_appointment_with_status(
            Appointment.STATUS_CONFIRMED,
        )

        result = AppointmentCancellationService.cancel(
            appointment=appointment,
            user=self.admin_user,
            cancellation_reason="Cancelamento autorizado pela equipa.",
        )

        appointment.refresh_from_db()

        self.assertTrue(result.success)
        self.assertEqual(appointment.status, Appointment.STATUS_CANCELLED)

    def test_prevent_cancelling_completed_appointment(self):
        # Ensure completed appointments cannot be cancelled.
        appointment = self.create_appointment_with_status(
            Appointment.STATUS_COMPLETED,
        )

        result = AppointmentCancellationService.cancel(
            appointment=appointment,
            user=self.admin_user,
        )

        appointment.refresh_from_db()

        self.assertFalse(result.success)
        self.assertEqual(appointment.status, Appointment.STATUS_COMPLETED)


class PublicAppointmentFlowTests(AppointmentTestSetupMixin, TestCase):
    # Tests for public appointment HTTP flows.

    def setUp(self):
        self.create_base_data()

    def test_public_booking_valid_slot_redirects_to_success(self):
        # Ensure public booking creates an appointment and redirects to success.
        response = self.client.post(
            reverse("appointments:public_appointment_create"),
            data={
                "service": self.service.id,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
                "start_time": "10:00",
                "customer_name": "Novo Cliente",
                "customer_phone": "+351918888888",
                "customer_email": "novo@test.com",
                "notes": "",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:public_appointment_success"),
        )
        self.assertEqual(Appointment.objects.count(), 1)

    def test_public_booking_invalid_phone_does_not_create_appointment(self):
        # Ensure invalid phone blocks public booking.
        response = self.client.post(
            reverse("appointments:public_appointment_create"),
            data={
                "service": self.service.id,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
                "start_time": "10:00",
                "customer_name": "Cliente Telefone Inválido",
                "customer_phone": "123",
                "customer_email": "telefoneinvalido@test.com",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_public_booking_conflict_redirects_to_public_schedule(self):
        # Ensure conflicting public booking redirects back to the public schedule.
        AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        response = self.client.post(
            reverse("appointments:public_appointment_create"),
            data={
                "service": self.service.id,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
                "start_time": "10:00",
                "customer_name": "Outro Cliente",
                "customer_phone": "+351918888888",
                "customer_email": "outro@test.com",
                "notes": "",
            },
        )

        expected_url = (
            reverse("appointments:public_visual_schedule")
            + f"?service={self.service.id}&date={self.appointment_date.strftime('%Y-%m-%d')}"
        )

        self.assertRedirects(response, expected_url)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_public_schedule_does_not_show_occupied_slot(self):
        # Ensure occupied slots are not shown in the public schedule context.
        AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        response = self.client.get(
            reverse("appointments:public_visual_schedule"),
            data={
                "service": self.service.id,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        slot_values = [slot["value"] for slot in response.context["slots"]]

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("10:00", slot_values)

    def test_public_cancel_scheduled_appointment_by_code(self):
        # Ensure scheduled public appointments can be cancelled by reference code.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        appointment = result.appointment

        response = self.client.post(
            reverse("appointments:public_cancel"),
            data={
                "reference_code": appointment.reference_code,
                "cancellation_reason": "Cliente não poderá comparecer.",
            },
        )

        appointment.refresh_from_db()

        expected_url = reverse(
            "appointments:public_cancel_success_with_code",
            kwargs={"reference_code": appointment.reference_code},
        )

        self.assertRedirects(response, expected_url)
        self.assertEqual(appointment.status, Appointment.STATUS_CANCELLED)

    def test_public_cancel_confirmed_appointment_as_anonymous_is_blocked(self):
        # Ensure anonymous users cannot cancel confirmed appointments.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            status=Appointment.STATUS_CONFIRMED,
            send_email=False,
        )

        appointment = result.appointment

        response = self.client.post(
            reverse("appointments:public_cancel"),
            data={
                "reference_code": appointment.reference_code,
                "cancellation_reason": "Cliente não poderá comparecer.",
            },
        )

        appointment.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(appointment.status, Appointment.STATUS_CONFIRMED)


class PublicAppointmentMagicLinkTests(AppointmentTestSetupMixin, TestCase):
    # Tests for public appointment magic link access.

    def setUp(self):
        self.create_base_data()

        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        self.appointment = result.appointment

    def build_token(self, appointment):
        # Build a valid magic link token for tests.
        payload = {
            "reference_code": appointment.reference_code,
            "updated_at": appointment.updated_at.isoformat(),
        }

        return signing.dumps(
            payload,
            salt="appointment-magic-link",
        )

    def test_valid_magic_link_shows_appointment(self):
        # Ensure valid magic link opens appointment lookup page with appointment.
        token = self.build_token(self.appointment)

        response = self.client.get(
            reverse(
                "appointments:public_appointment_magic",
                kwargs={"token": token},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["appointment"], self.appointment)

    def test_invalid_magic_link_redirects_to_lookup(self):
        # Ensure invalid magic link redirects to lookup page.
        response = self.client.get(
            reverse(
                "appointments:public_appointment_magic",
                kwargs={"token": "invalid-token"},
            )
        )

        self.assertRedirects(
            response,
            reverse("appointments:public_appointment_lookup"),
        )

    def test_old_magic_link_after_update_is_invalid(self):
        # Ensure token becomes invalid after appointment update.
        token = self.build_token(self.appointment)

        self.appointment.notes = "Updated notes"
        self.appointment.save(update_fields=["notes", "updated_at"])

        response = self.client.get(
            reverse(
                "appointments:public_appointment_magic",
                kwargs={"token": token},
            )
        )

        self.assertRedirects(
            response,
            reverse("appointments:public_appointment_lookup"),
        )


class CustomerSignupWithAppointmentTests(AppointmentTestSetupMixin, TestCase):
    # Tests for customer signup with appointment creation.

    def setUp(self):
        self.create_base_data()

    def test_customer_signup_with_appointment_creates_user_customer_and_appointment(
        self,
    ):
        # Ensure signup flow creates user, links customer, and creates appointment.
        response = self.client.post(
            reverse("accounts:customer_signup")
            + f"?service={self.service.id}&date={self.appointment_date.strftime('%Y-%m-%d')}&start_time=10:00",
            data={
                "full_name": "Cliente Cadastro",
                "phone": "+351916666666",
                "email": "cadastro@test.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:public_appointment_success"),
        )

        User = get_user_model()

        user = User.objects.get(email="cadastro@test.com")
        customer = Customer.objects.get(user=user)

        self.assertEqual(customer.email, "cadastro@test.com")
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Appointment.objects.first().customer, customer)

    def test_customer_signup_with_phone_already_linked_to_another_user_is_blocked(self):
        # Ensure same phone with another linked user is blocked safely.
        response = self.client.post(
            reverse("accounts:customer_signup"),
            data={
                "full_name": "Outro Cliente",
                "phone": self.customer.phone,
                "email": "outro-email@test.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        User = get_user_model()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="outro-email@test.com").exists())
        self.assertEqual(Customer.objects.count(), 1)


class BusinessHourModelTests(TestCase):
    # Tests for business hour validation.

    def test_business_hour_with_valid_time_range_is_valid(self):
        # Ensure business hours with end time after start time are valid.
        business_hour = BusinessHour(
            weekday=0,
            start_time=time(9, 0),
            end_time=time(18, 0),
            is_active=True,
        )

        try:
            business_hour.full_clean()
        except ValidationError:
            self.fail("Valid business hour raised ValidationError unexpectedly.")

    def test_business_hour_with_end_time_before_start_time_is_invalid(self):
        # Ensure business hours with invalid time range are blocked.
        business_hour = BusinessHour(
            weekday=0,
            start_time=time(18, 0),
            end_time=time(9, 0),
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            business_hour.full_clean()

    def test_business_hour_with_same_start_and_end_time_is_invalid(self):
        # Ensure business hours cannot start and end at the same time.
        business_hour = BusinessHour(
            weekday=0,
            start_time=time(9, 0),
            end_time=time(9, 0),
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            business_hour.full_clean()


class ScheduleBlockModelTests(TestCase):
    # Tests for schedule block validation and recurrence.

    def test_schedule_block_without_time_and_not_full_day_is_invalid(self):
        # Ensure partial blocks require start and end time.
        block = ScheduleBlock(
            title="Invalid block",
            block_type=ScheduleBlock.BLOCK_TYPE_OTHER,
            date=date(2026, 5, 4),
            is_full_day=False,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            block.full_clean()

    def test_schedule_block_with_end_time_before_start_time_is_invalid(self):
        # Ensure block end time must be after start time.
        block = ScheduleBlock(
            title="Invalid time block",
            block_type=ScheduleBlock.BLOCK_TYPE_OTHER,
            date=date(2026, 5, 4),
            start_time=time(14, 0),
            end_time=time(13, 0),
            is_full_day=False,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            block.full_clean()

    def test_recurring_schedule_block_without_weekdays_is_invalid(self):
        # Ensure recurring blocks require selected weekdays.
        block = ScheduleBlock(
            title="Recurring without weekdays",
            block_type=ScheduleBlock.BLOCK_TYPE_OTHER,
            date=date(2026, 5, 4),
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_full_day=False,
            is_recurring=True,
            recurring_weekdays="",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            block.full_clean()

    def test_recurring_schedule_block_applies_to_correct_weekday(self):
        # Ensure recurring blocks apply only to selected weekdays.
        block = ScheduleBlock.objects.create(
            title="Monday recurring block",
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=date(2026, 5, 4),
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_full_day=False,
            is_recurring=True,
            recurring_weekdays="0",
            is_active=True,
        )

        monday = date(2026, 5, 11)
        tuesday = date(2026, 5, 12)

        self.assertTrue(block.applies_to_date(monday))
        self.assertFalse(block.applies_to_date(tuesday))

    def test_recurring_schedule_block_does_not_apply_after_end_date(self):
        # Ensure recurring blocks stop after recurrence end date.
        block = ScheduleBlock.objects.create(
            title="Temporary recurring block",
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=date(2026, 5, 4),
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_full_day=False,
            is_recurring=True,
            recurring_weekdays="0",
            recurrence_end_date=date(2026, 5, 11),
            is_active=True,
        )

        valid_monday = date(2026, 5, 11)
        expired_monday = date(2026, 5, 18)

        self.assertTrue(block.applies_to_date(valid_monday))
        self.assertFalse(block.applies_to_date(expired_monday))


class PublicAvailableSlotsViewTests(AppointmentTestSetupMixin, TestCase):
    # Tests for the public available slots AJAX endpoint.

    def setUp(self):
        self.create_base_data()

    def test_available_slots_endpoint_returns_available_slots(self):
        # Ensure AJAX endpoint returns available slots for service and date.
        response = self.client.get(
            reverse("appointments:public_available_slots"),
            data={
                "service": self.service.id,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        slot_values = [slot["value"] for slot in data["slots"]]

        self.assertIn("09:00", slot_values)
        self.assertIn("10:00", slot_values)

    def test_available_slots_endpoint_hides_occupied_slot(self):
        # Ensure AJAX endpoint does not return occupied slots.
        AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        response = self.client.get(
            reverse("appointments:public_available_slots"),
            data={
                "service": self.service.id,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        slot_values = [slot["value"] for slot in data["slots"]]

        self.assertNotIn("10:00", slot_values)
        self.assertNotIn("10:30", slot_values)
        self.assertIn("11:00", slot_values)

    def test_available_slots_endpoint_hides_blocked_slot(self):
        # Ensure AJAX endpoint does not return slots that conflict with schedule blocks.
        ScheduleBlock.objects.create(
            title="Lunch break",
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=self.appointment_date,
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_full_day=False,
            is_active=True,
        )

        response = self.client.get(
            reverse("appointments:public_available_slots"),
            data={
                "service": self.service.id,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        slot_values = [slot["value"] for slot in data["slots"]]

        self.assertNotIn("12:00", slot_values)
        self.assertNotIn("12:30", slot_values)

    def test_available_slots_endpoint_returns_empty_list_for_invalid_service(self):
        # Ensure invalid service returns empty slot list.
        response = self.client.get(
            reverse("appointments:public_available_slots"),
            data={
                "service": 9999,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slots"], [])

    def test_available_slots_endpoint_returns_empty_list_for_invalid_date(self):
        # Ensure invalid date returns empty slot list.
        response = self.client.get(
            reverse("appointments:public_available_slots"),
            data={
                "service": self.service.id,
                "date": "invalid-date",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slots"], [])

    def test_available_slots_endpoint_returns_empty_list_without_required_params(self):
        # Ensure missing query params return empty slot list.
        response = self.client.get(
            reverse("appointments:public_available_slots"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slots"], [])


class InternalPermissionTests(AppointmentTestSetupMixin, TestCase):
    # Tests for internal page permissions.

    def setUp(self):
        self.create_base_data()

    def assert_normal_user_redirected_from_internal_url(self, url_name):
        # Ensure normal users cannot access internal admin pages.
        self.client.login(
            email="cliente@test.com",
            password="testpass123",
        )

        response = self.client.get(reverse(url_name))

        self.assertEqual(response.status_code, 302)

    def assert_admin_user_can_access_internal_url(self, url_name):
        # Ensure superusers can access internal admin pages.
        self.client.login(
            email="admin@test.com",
            password="testpass123",
        )

        response = self.client.get(reverse(url_name))

        self.assertEqual(response.status_code, 200)

    def test_normal_user_cannot_access_appointment_list(self):
        self.assert_normal_user_redirected_from_internal_url(
            "appointments:appointment_list"
        )

    def test_normal_user_cannot_access_customer_list(self):
        self.assert_normal_user_redirected_from_internal_url(
            "appointments:customer_list"
        )

    def test_normal_user_cannot_access_service_list(self):
        self.assert_normal_user_redirected_from_internal_url(
            "appointments:service_list"
        )

    def test_normal_user_cannot_access_schedule_block_list(self):
        self.assert_normal_user_redirected_from_internal_url(
            "appointments:schedule_block_list"
        )

    def test_normal_user_cannot_access_daily_agenda(self):
        self.assert_normal_user_redirected_from_internal_url(
            "appointments:daily_agenda"
        )

    def test_admin_user_can_access_appointment_list(self):
        self.assert_admin_user_can_access_internal_url("appointments:appointment_list")

    def test_admin_user_can_access_customer_list(self):
        self.assert_admin_user_can_access_internal_url("appointments:customer_list")

    def test_admin_user_can_access_service_list(self):
        self.assert_admin_user_can_access_internal_url("appointments:service_list")

    def test_admin_user_can_access_schedule_block_list(self):
        self.assert_admin_user_can_access_internal_url(
            "appointments:schedule_block_list"
        )

    def test_admin_user_can_access_daily_agenda(self):
        self.assert_admin_user_can_access_internal_url("appointments:daily_agenda")


class AppointmentAdminActionTests(AppointmentTestSetupMixin, TestCase):
    # Tests for internal appointment status actions.

    def setUp(self):
        self.create_base_data()

        self.client.login(
            email="admin@test.com",
            password="testpass123",
        )

    def create_appointment_with_status(self, status):
        # Helper to create an appointment with a specific status.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            status=status,
            send_email=False,
        )

        return result.appointment

    def test_admin_can_confirm_scheduled_appointment(self):
        # Ensure admin can confirm a scheduled appointment.
        appointment = self.create_appointment_with_status(
            Appointment.STATUS_SCHEDULED,
        )

        response = self.client.post(
            reverse(
                "appointments:appointment_confirm",
                kwargs={"pk": appointment.pk},
            )
        )

        appointment.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("appointments:appointment_list"),
        )
        self.assertEqual(appointment.status, Appointment.STATUS_CONFIRMED)

    def test_admin_can_complete_confirmed_appointment(self):
        # Ensure admin can complete a confirmed appointment.
        appointment = self.create_appointment_with_status(
            Appointment.STATUS_CONFIRMED,
        )

        response = self.client.post(
            reverse(
                "appointments:appointment_complete",
                kwargs={"pk": appointment.pk},
            )
        )

        appointment.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("appointments:appointment_list"),
        )
        self.assertEqual(appointment.status, Appointment.STATUS_COMPLETED)

    def test_admin_cannot_complete_scheduled_appointment(self):
        # Ensure scheduled appointments cannot be completed directly.
        appointment = self.create_appointment_with_status(
            Appointment.STATUS_SCHEDULED,
        )

        response = self.client.post(
            reverse(
                "appointments:appointment_complete",
                kwargs={"pk": appointment.pk},
            )
        )

        appointment.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("appointments:appointment_list"),
        )
        self.assertEqual(appointment.status, Appointment.STATUS_SCHEDULED)

    def test_admin_can_cancel_scheduled_appointment(self):
        # Ensure admin can cancel a scheduled appointment.
        appointment = self.create_appointment_with_status(
            Appointment.STATUS_SCHEDULED,
        )

        response = self.client.post(
            reverse(
                "appointments:appointment_cancel",
                kwargs={"pk": appointment.pk},
            ),
            data={
                "cancellation_reason": "Cancelamento feito pela equipa.",
            },
        )

        appointment.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("appointments:appointment_list"),
        )
        self.assertEqual(appointment.status, Appointment.STATUS_CANCELLED)

    def test_normal_user_cannot_confirm_appointment(self):
        # Ensure normal users cannot confirm appointments.
        appointment = self.create_appointment_with_status(
            Appointment.STATUS_SCHEDULED,
        )

        self.client.logout()
        self.client.login(
            email="cliente@test.com",
            password="testpass123",
        )

        response = self.client.post(
            reverse(
                "appointments:appointment_confirm",
                kwargs={"pk": appointment.pk},
            )
        )

        appointment.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(appointment.status, Appointment.STATUS_SCHEDULED)


@freeze_time("2026-05-04 10:00:00")
class DashboardMetricsTests(AppointmentTestSetupMixin, TestCase):
    # Tests for dashboard appointment and revenue metrics.

    def setUp(self):
        self.create_base_data()

        self.client.login(
            email="admin@test.com",
            password="testpass123",
        )

    def create_appointment_for_dashboard(self, start_time, status, service=None):
        # Helper to create dashboard appointments with custom status.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=service or self.service,
            date=self.appointment_date,
            start_time=start_time,
            created_by=self.admin_user,
            status=status,
            send_email=False,
        )

        return result.appointment

    def test_dashboard_shows_today_appointment_metrics(self):
        # Ensure dashboard counts today's scheduled and confirmed appointments.
        today = self.appointment_date

        with self.settings(USE_TZ=True):
            Appointment.objects.create(
                customer=self.customer,
                service=self.service,
                date=today,
                start_time=time(9, 0),
                status=Appointment.STATUS_SCHEDULED,
                created_by=self.admin_user,
            )

            Appointment.objects.create(
                customer=self.customer,
                service=self.service,
                date=today,
                start_time=time(10, 0),
                status=Appointment.STATUS_CONFIRMED,
                created_by=self.admin_user,
            )

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["metrics"]["today_total"], 2)
        self.assertEqual(response.context["metrics"]["today_scheduled"], 1)
        self.assertEqual(response.context["metrics"]["today_confirmed"], 1)

    def test_dashboard_shows_month_status_metrics(self):
        # Ensure dashboard counts monthly completed and cancelled appointments.
        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(9, 0),
            status=Appointment.STATUS_COMPLETED,
            created_by=self.admin_user,
        )

        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(11, 0),
            status=Appointment.STATUS_CANCELLED,
            created_by=self.admin_user,
        )

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["metrics"]["month_total"], 2)
        self.assertEqual(response.context["metrics"]["month_completed"], 1)
        self.assertEqual(response.context["metrics"]["month_cancelled"], 1)

    def test_dashboard_calculates_month_revenue_only_from_completed_appointments(self):
        # Ensure monthly revenue includes only completed appointments.
        second_service = Service.objects.create(
            name="Tratamento Especial",
            duration_minutes=60,
            price="75.00",
            is_active=True,
        )

        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(9, 0),
            status=Appointment.STATUS_COMPLETED,
            created_by=self.admin_user,
        )

        Appointment.objects.create(
            customer=self.customer,
            service=second_service,
            date=self.appointment_date,
            start_time=time(11, 0),
            status=Appointment.STATUS_COMPLETED,
            created_by=self.admin_user,
        )

        Appointment.objects.create(
            customer=self.customer,
            service=second_service,
            date=self.appointment_date,
            start_time=time(13, 0),
            status=Appointment.STATUS_CANCELLED,
            created_by=self.admin_user,
        )

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["metrics"]["month_revenue"], 125)


class CustomerIdentityAndAccessTests(AppointmentTestSetupMixin, TestCase):
    # Tests for customer identity linking and customer appointment access.

    def setUp(self):
        self.create_base_data()

    def test_signup_links_existing_customer_without_user_and_does_not_duplicate(self):
        # Ensure signup links an existing customer without user instead of duplicating it.
        User = get_user_model()

        Customer.objects.all().delete()
        User.objects.filter(email="cliente@test.com").delete()

        existing_customer = Customer.objects.create(
            full_name="Cliente Existente",
            email="existente@test.com",
            phone="+351916666666",
            user=None,
        )

        response = self.client.post(
            reverse("accounts:customer_signup"),
            data={
                "full_name": "Cliente Existente Atualizado",
                "phone": "+351916666666",
                "email": "existente@test.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:public_visual_schedule"),
        )

        existing_customer.refresh_from_db()

        self.assertEqual(Customer.objects.count(), 1)
        self.assertIsNotNone(existing_customer.user)
        self.assertEqual(existing_customer.user.email, "existente@test.com")
        self.assertEqual(existing_customer.full_name, "Cliente Existente Atualizado")

    def test_customer_appointments_page_shows_only_logged_customer_appointments(self):
        # Ensure a customer sees only their own appointments.
        other_user = get_user_model().objects.create_user(
            email="outrocliente@test.com",
            password="testpass123",
            full_name="Outro Cliente",
        )

        other_customer = Customer.objects.create(
            full_name="Outro Cliente",
            email="outrocliente@test.com",
            phone="+351918888888",
            user=other_user,
        )

        own_result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        other_result = AppointmentService.create_appointment(
            customer=other_customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(11, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        self.client.login(
            email="cliente@test.com",
            password="testpass123",
        )

        response = self.client.get(
            reverse("appointments:customer_appointments"),
        )

        appointments = list(response.context["appointments"])

        self.assertEqual(response.status_code, 200)
        self.assertIn(own_result.appointment, appointments)
        self.assertNotIn(other_result.appointment, appointments)

    def test_customer_appointment_detail_shows_own_appointment(self):
        # Ensure customer can access their own appointment detail.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        appointment = result.appointment

        self.client.login(
            email="cliente@test.com",
            password="testpass123",
        )

        response = self.client.get(
            reverse(
                "appointments:customer_appointment_detail",
                kwargs={"reference_code": appointment.reference_code},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["appointment"], appointment)

    def test_customer_appointment_detail_does_not_show_other_customer_appointment(self):
        # Ensure customer cannot access another customer's appointment detail.
        other_user = get_user_model().objects.create_user(
            email="outrocliente@test.com",
            password="testpass123",
            full_name="Outro Cliente",
        )

        other_customer = Customer.objects.create(
            full_name="Outro Cliente",
            email="outrocliente@test.com",
            phone="+351918888888",
            user=other_user,
        )

        other_result = AppointmentService.create_appointment(
            customer=other_customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        self.client.login(
            email="cliente@test.com",
            password="testpass123",
        )

        response = self.client.get(
            reverse(
                "appointments:customer_appointment_detail",
                kwargs={"reference_code": other_result.appointment.reference_code},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["appointment"])


class AppointmentUpdateProtectionTests(AppointmentTestSetupMixin, TestCase):
    # Tests for appointment update protection rules.

    def setUp(self):
        self.create_base_data()
        self.client.login(
            email="admin@test.com",
            password="testpass123",
        )

    def test_admin_cannot_edit_completed_appointment(self):
        # Ensure completed appointments cannot be edited by direct URL access.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            status=Appointment.STATUS_COMPLETED,
            send_email=False,
        )

        appointment = result.appointment

        response = self.client.get(
            reverse(
                "appointments:appointment_update",
                kwargs={"pk": appointment.pk},
            )
        )

        self.assertRedirects(
            response,
            reverse("appointments:appointment_list"),
        )


class ScheduleBlockFormTests(TestCase):
    # Tests for schedule block form recurrence handling.

    def test_schedule_block_form_saves_recurring_weekdays_from_checkboxes(self):
        # Ensure recurring weekday checkboxes are saved as comma-separated values.
        form = ScheduleBlockForm(
            data={
                "title": "Recurring break",
                "block_type": ScheduleBlock.BLOCK_TYPE_BREAK,
                "date": "2026-05-04",
                "start_time": "12:00",
                "end_time": "13:00",
                "is_full_day": "",
                "is_recurring": "on",
                "recurring_weekdays_checkboxes": ["0", "2", "4"],
                "recurrence_end_date": "2026-06-30",
                "is_active": "on",
                "notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

        block = form.save()

        self.assertEqual(block.recurring_weekdays, "0,2,4")

    def test_schedule_block_form_requires_weekdays_when_recurring(self):
        # Ensure recurring blocks require at least one weekday.
        form = ScheduleBlockForm(
            data={
                "title": "Invalid recurring break",
                "block_type": ScheduleBlock.BLOCK_TYPE_BREAK,
                "date": "2026-05-04",
                "start_time": "12:00",
                "end_time": "13:00",
                "is_full_day": "",
                "is_recurring": "on",
                "recurring_weekdays_checkboxes": [],
                "recurrence_end_date": "2026-06-30",
                "is_active": "on",
                "notes": "",
            }
        )

        self.assertFalse(form.is_valid())


class CustomerInternalFormViewTests(AppointmentTestSetupMixin, TestCase):
    # Tests for internal customer create and update views.

    def setUp(self):
        self.create_base_data()
        self.client.login(
            email="admin@test.com",
            password="testpass123",
        )

    def test_admin_can_create_customer_with_valid_brazil_phone(self):
        # Ensure admin can create a customer with a valid Brazilian phone.
        response = self.client.post(
            reverse("appointments:customer_create"),
            data={
                "full_name": "Cliente Brasil",
                "email": "brasil@test.com",
                "phone": "(11) 99999-9999",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:customer_list"),
        )

        customer = Customer.objects.get(email="brasil@test.com")

        self.assertEqual(customer.phone, "+5511999999999")

    def test_admin_can_create_customer_with_valid_portugal_phone(self):
        # Ensure admin can create a customer with a valid Portuguese phone.
        response = self.client.post(
            reverse("appointments:customer_create"),
            data={
                "full_name": "Cliente Portugal",
                "email": "portugal@test.com",
                "phone": "919999999",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:customer_list"),
        )

        customer = Customer.objects.get(email="portugal@test.com")

        self.assertEqual(customer.phone, "+351919999999")

    def test_admin_cannot_create_customer_with_invalid_phone(self):
        # Ensure invalid phone blocks customer creation.
        response = self.client.post(
            reverse("appointments:customer_create"),
            data={
                "full_name": "Cliente Inválido",
                "email": "invalido@test.com",
                "phone": "123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.filter(email="invalido@test.com").exists())

    def test_admin_can_update_customer_phone_and_normalize_it(self):
        # Ensure customer update normalizes phone numbers.
        response = self.client.post(
            reverse(
                "appointments:customer_update",
                kwargs={"pk": self.customer.pk},
            ),
            data={
                "full_name": self.customer.full_name,
                "email": self.customer.email,
                "phone": "(21) 98888-7777",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:customer_list"),
        )

        self.customer.refresh_from_db()

        self.assertEqual(self.customer.phone, "+5521988887777")

    def test_admin_cannot_update_customer_with_invalid_phone(self):
        # Ensure invalid phone blocks customer update.
        old_phone = self.customer.phone

        response = self.client.post(
            reverse(
                "appointments:customer_update",
                kwargs={"pk": self.customer.pk},
            ),
            data={
                "full_name": self.customer.full_name,
                "email": self.customer.email,
                "phone": "123",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.customer.refresh_from_db()

        self.assertEqual(self.customer.phone, old_phone)


class ServiceInternalViewTests(AppointmentTestSetupMixin, TestCase):
    # Tests for internal service create view.

    def setUp(self):
        self.create_base_data()

    def test_admin_can_create_service_with_valid_data(self):
        # Ensure admin users can create services.
        self.client.login(
            email="admin@test.com",
            password="testpass123",
        )

        response = self.client.post(
            reverse("appointments:service_create"),
            data={
                "name": "Tratamento de Unha",
                "description": "Tratamento profissional.",
                "duration_minutes": 45,
                "price": "35.00",
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:service_list"),
        )

        self.assertTrue(Service.objects.filter(name="Tratamento de Unha").exists())

    def test_normal_user_cannot_create_service(self):
        # Ensure normal users cannot access service creation.
        self.client.login(
            email="cliente@test.com",
            password="testpass123",
        )

        response = self.client.post(
            reverse("appointments:service_create"),
            data={
                "name": "Serviço Indevido",
                "description": "Não deve ser criado.",
                "duration_minutes": 30,
                "price": "20.00",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Service.objects.filter(name="Serviço Indevido").exists())


class ServiceValidationTests(TestCase):
    # Tests for service model/form validation.

    def test_service_with_valid_data_is_valid(self):
        # Ensure a service with valid duration and price passes validation.
        service = Service(
            name="Podologia Completa",
            description="Serviço completo.",
            duration_minutes=60,
            price="50.00",
            is_active=True,
        )

        try:
            service.full_clean()
        except ValidationError:
            self.fail("Valid service raised ValidationError unexpectedly.")

    def test_service_with_zero_duration_is_invalid(self):
        # Ensure services cannot have zero duration.
        service = Service(
            name="Serviço sem duração",
            description="Inválido.",
            duration_minutes=0,
            price="50.00",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            service.full_clean()

    def test_service_with_negative_duration_is_invalid(self):
        # Ensure services cannot have negative duration.
        service = Service(
            name="Serviço com duração negativa",
            description="Inválido.",
            duration_minutes=-30,
            price="50.00",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            service.full_clean()

    def test_service_with_negative_price_is_invalid(self):
        # Ensure services cannot have negative prices.
        service = Service(
            name="Serviço com preço negativo",
            description="Inválido.",
            duration_minutes=60,
            price="-10.00",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            service.full_clean()


class AppointmentAuditLogTests(AppointmentTestSetupMixin, TestCase):
    # Tests for appointment audit log creation.

    def setUp(self):
        self.create_base_data()

    def test_create_appointment_generates_create_log(self):
        # Ensure creating an appointment generates a create audit log.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        appointment = result.appointment

        self.assertTrue(result.success)
        self.assertEqual(appointment.logs.count(), 1)

        log = appointment.logs.first()

        self.assertEqual(log.action, AppointmentLog.ACTION_CREATE)
        self.assertEqual(log.performed_by, self.admin_user)

    def test_cancel_appointment_generates_cancel_log(self):
        # Ensure cancelling an appointment generates a cancel audit log.
        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        appointment = result.appointment

        cancel_result = AppointmentCancellationService.cancel(
            appointment=appointment,
            user=self.admin_user,
            cancellation_reason="Cancelamento para teste de auditoria.",
        )

        self.assertTrue(cancel_result.success)

        self.assertTrue(
            appointment.logs.filter(
                action=AppointmentLog.ACTION_CANCEL,
                performed_by=self.admin_user,
            ).exists()
        )

    def test_confirm_appointment_generates_confirm_log(self):
        # Ensure confirming an appointment generates a confirm audit log.
        self.client.login(
            email="admin@test.com",
            password="testpass123",
        )

        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        appointment = result.appointment

        response = self.client.post(
            reverse(
                "appointments:appointment_confirm",
                kwargs={"pk": appointment.pk},
            )
        )

        self.assertRedirects(
            response,
            reverse("appointments:appointment_list"),
        )

        self.assertTrue(
            appointment.logs.filter(
                action=AppointmentLog.ACTION_CONFIRM,
                performed_by=self.admin_user,
            ).exists()
        )

    def test_complete_appointment_generates_complete_log(self):
        # Ensure completing an appointment generates a complete audit log.
        self.client.login(
            email="admin@test.com",
            password="testpass123",
        )

        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            status=Appointment.STATUS_CONFIRMED,
            send_email=False,
        )

        appointment = result.appointment

        response = self.client.post(
            reverse(
                "appointments:appointment_complete",
                kwargs={"pk": appointment.pk},
            )
        )

        self.assertRedirects(
            response,
            reverse("appointments:appointment_list"),
        )

        self.assertTrue(
            appointment.logs.filter(
                action=AppointmentLog.ACTION_COMPLETE,
                performed_by=self.admin_user,
            ).exists()
        )

    def test_update_appointment_generates_update_log(self):
        # Ensure updating an appointment generates an update audit log.
        self.client.login(
            email="admin@test.com",
            password="testpass123",
        )

        result = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        appointment = result.appointment

        response = self.client.post(
            reverse(
                "appointments:appointment_update",
                kwargs={"pk": appointment.pk},
            ),
            data={
                "customer": self.customer.pk,
                "service": self.service.pk,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
                "start_time": "11:00",
                "status": Appointment.STATUS_SCHEDULED,
                "notes": "Updated appointment notes.",
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments:appointment_list"),
        )

        self.assertTrue(
            appointment.logs.filter(
                action=AppointmentLog.ACTION_UPDATE,
                performed_by=self.admin_user,
            ).exists()
        )


class PublicVisualScheduleAjaxTests(AppointmentTestSetupMixin, TestCase):
    # Tests for AJAX data used by the public visual schedule.

    def setUp(self):
        self.create_base_data()

    def test_ajax_slots_endpoint_returns_json_with_slots_key(self):
        # Ensure AJAX endpoint returns JSON with the expected structure.
        response = self.client.get(
            reverse("appointments:public_available_slots"),
            data={
                "service": self.service.pk,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        data = response.json()

        self.assertIn("slots", data)
        self.assertIsInstance(data["slots"], list)

    def test_ajax_slots_endpoint_returns_slot_value_and_label(self):
        # Ensure each returned slot contains value and label for frontend rendering.
        response = self.client.get(
            reverse("appointments:public_available_slots"),
            data={
                "service": self.service.pk,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        data = response.json()

        self.assertGreater(len(data["slots"]), 0)
        self.assertIn("value", data["slots"][0])
        self.assertIn("label", data["slots"][0])

    def test_ajax_slots_endpoint_does_not_return_occupied_slot(self):
        # Ensure AJAX endpoint hides slots occupied by existing appointments.
        AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.appointment_date,
            start_time=time(10, 0),
            created_by=self.admin_user,
            send_email=False,
        )

        response = self.client.get(
            reverse("appointments:public_available_slots"),
            data={
                "service": self.service.pk,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        slot_values = [slot["value"] for slot in response.json()["slots"]]

        self.assertNotIn("10:00", slot_values)
        self.assertNotIn("10:30", slot_values)

    def test_ajax_slots_endpoint_does_not_return_blocked_slot(self):
        # Ensure AJAX endpoint hides slots blocked by schedule blocks.
        ScheduleBlock.objects.create(
            title="Blocked period",
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=self.appointment_date,
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_full_day=False,
            is_active=True,
        )

        response = self.client.get(
            reverse("appointments:public_available_slots"),
            data={
                "service": self.service.pk,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        slot_values = [slot["value"] for slot in response.json()["slots"]]

        self.assertNotIn("12:00", slot_values)
        self.assertNotIn("12:30", slot_values)

    def test_public_visual_schedule_page_contains_ajax_container(self):
        # Ensure visual schedule template exposes the AJAX container expected by JavaScript.
        response = self.client.get(
            reverse("appointments:public_visual_schedule"),
            data={
                "service": self.service.pk,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="agenda-slots-container"')
        self.assertContains(response, "data-slots-url=")
        self.assertContains(response, "data-booking-url=")

    def test_public_visual_schedule_page_loads_jquery_ajax_script(self):
        # Ensure the public visual schedule loads the jQuery AJAX script.
        response = self.client.get(
            reverse("appointments:public_visual_schedule"),
            data={
                "service": self.service.pk,
                "date": self.appointment_date.strftime("%Y-%m-%d"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "jquery-3.7.1.min.js")
        self.assertContains(response, "js/public_visual_schedule.js")
