from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time

from appointments.availability import AvailabilityService
from appointments.models import Appointment, Customer, ScheduleBlock
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class PublicSlotGridTests(TestCase):
    """A agenda pública mostra o dia inteiro a partir de agora.

    Horários ocupados aparecem marcados como reservados, em vez de sumirem: um
    dia cheio deve parecer cheio, e não vazio.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.admin_user = get_user_model().objects.create_superuser(
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

        # Uma segunda-feira futura, para não depender do dia em que os testes
        # correm nem do corte de antecedência.
        self.selected_date = timezone.localdate() + timedelta(days=14)
        while self.selected_date.weekday() != 0:
            self.selected_date += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.selected_date.weekday(),
            start_time=time(9, 0),
            end_time=time(13, 0),
        )

        ScheduleBlock.objects.all().delete()

    def grid(self):
        return AvailabilityService.build_public_slots(self.service, self.selected_date)

    def test_free_day_has_every_slot_available(self):
        grelha = self.grid()

        self.assertTrue(grelha)
        self.assertTrue(all(slot["is_available"] for slot in grelha))

    def test_slot_taken_by_an_appointment_is_kept_but_marked(self):
        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.selected_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        grelha = {slot["value"]: slot["is_available"] for slot in self.grid()}

        # Continua presente, ao contrário do que acontecia antes.
        self.assertIn("10:00", grelha)
        self.assertFalse(grelha["10:00"])
        self.assertTrue(grelha["09:00"])

    def test_blocked_slot_is_kept_but_marked(self):
        ScheduleBlock.objects.create(
            notes="Almoço",
            block_type=ScheduleBlock.BLOCK_TYPE_BREAK,
            date=self.selected_date,
            start_time=time(11, 0),
            end_time=time(12, 0),
            is_full_day=False,
            is_active=True,
        )

        grelha = {slot["value"]: slot["is_available"] for slot in self.grid()}

        self.assertIn("11:00", grelha)
        self.assertFalse(grelha["11:00"])

    def test_available_slots_helper_still_returns_only_free_ones(self):
        # A validação da submissão continua a usar este método: mostrar um
        # horário reservado não pode torná-lo reservável.
        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.selected_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        livres = AvailabilityService.get_public_available_slots(
            self.service, self.selected_date
        )

        self.assertNotIn("10:00", [slot["value"] for slot in livres])

    def test_past_slots_are_still_excluded_today(self):
        hoje = timezone.localdate()

        ensure_test_business_hour(
            weekday=hoje.weekday(),
            start_time=time(0, 0),
            end_time=time(23, 30),
        )

        with freeze_time(timezone.now().replace(hour=12, minute=0)):
            grelha = AvailabilityService.build_public_slots(self.service, hoje)

        # Nenhum horário anterior ao momento atual, mesmo estando livre.
        self.assertTrue(grelha)
        self.assertTrue(all(slot["value"] >= "12:00" for slot in grelha))

    def test_page_shows_the_reserved_label(self):
        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.selected_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        response = self.client.get(
            reverse("appointments:public_visual_schedule")
            + f"?service={self.service.pk}&date={self.selected_date.isoformat()}"
        )

        self.assertContains(response, "Reservado")
        self.assertContains(response, "is-reserved")

    def test_json_endpoint_marks_availability(self):
        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.selected_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        response = self.client.get(
            reverse("appointments:public_available_slots"),
            {"service": self.service.pk, "date": self.selected_date.isoformat()},
        )

        slots = {
            slot["value"]: slot["is_available"] for slot in response.json()["slots"]
        }

        self.assertFalse(slots["10:00"])
        self.assertTrue(slots["09:00"])

    def test_reserved_slot_cannot_be_booked(self):
        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.selected_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        response = self.client.post(
            reverse("appointments:public_appointment_create"),
            data={
                "service": self.service.pk,
                "date": self.selected_date.isoformat(),
                "start_time": "10:00",
                "customer_name": "Ana Costa",
                "customer_phone": "+351920000000",
                "customer_email": "ana@example.com",
                "notes": "",
                "privacy_policy_accepted": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Appointment.objects.count(), 1)
