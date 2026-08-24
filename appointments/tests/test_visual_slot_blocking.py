from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from appointments.models import Appointment, BusinessHour, Customer, ScheduleBlock
from appointments.tests.factories import create_test_service


class VisualSlotBlockingTests(TestCase):
    # Bloquear horários escolhendo-os na agenda visual, para fechar buracos sem
    # ter de preencher o formulário de bloqueio campo a campo.

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

        self.service = create_test_service(duration_minutes=60)
        self.selected_date = date(2026, 5, 4)

        BusinessHour.objects.update_or_create(
            weekday=self.selected_date.weekday(),
            defaults={
                "start_time": time(9, 0),
                "end_time": time(18, 0),
                "is_active": True,
            },
        )

        ScheduleBlock.objects.all().delete()

        self.client.force_login(self.admin_user)
        self.url = reverse("appointments:visual_schedule_block")

    def block(self, slots, notas=""):
        return self.client.post(
            self.url,
            data={
                "date": self.selected_date.isoformat(),
                "slots": slots,
                "notes": notas,
            },
        )

    def test_contiguous_slots_become_a_single_block(self):
        self.block(["14:00", "14:30", "15:00"], notas="Almoço alargado")

        blocks = list(ScheduleBlock.objects.all())

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].notes, "Almoço alargado")
        self.assertEqual(blocks[0].label, "Almoço alargado")
        self.assertEqual(blocks[0].start_time, time(14, 0))
        self.assertEqual(blocks[0].end_time, time(15, 30))
        self.assertEqual(blocks[0].date, self.selected_date)

    def test_separate_slots_become_separate_blocks(self):
        self.block(["10:00", "16:00"])

        blocks = list(ScheduleBlock.objects.order_by("start_time"))

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].start_time, time(10, 0))
        self.assertEqual(blocks[0].end_time, time(10, 30))
        self.assertEqual(blocks[1].start_time, time(16, 0))

    def test_without_a_reason_the_block_shows_its_type(self):
        # O motivo é opcional. Sem ele, o que aparece nos ecrãs é o tipo do
        # bloqueio, que já diz o suficiente.
        self.block(["11:00"])

        bloqueio = ScheduleBlock.objects.get()

        self.assertEqual(bloqueio.notes, "")
        self.assertEqual(bloqueio.label, bloqueio.get_block_type_display())

    def test_blocked_slots_stop_appearing_as_available(self):
        from appointments.availability import AvailabilityService

        before = AvailabilityService.get_available_slots(
            self.service, self.selected_date
        )
        self.block(["14:00", "14:30"])
        after = AvailabilityService.get_available_slots(
            self.service, self.selected_date
        )

        self.assertIn({"value": "14:00", "label": "14:00"}, before)
        self.assertNotIn({"value": "14:00", "label": "14:00"}, after)

    def test_slot_taken_by_an_appointment_is_never_blocked(self):
        # Defesa contra um POST manipulado: o horário ocupado é ignorado.
        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.selected_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        self.block(["10:00", "10:30"])

        self.assertEqual(ScheduleBlock.objects.count(), 0)

    def test_submitting_without_slots_creates_nothing(self):
        response = self.block([])

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ScheduleBlock.objects.count(), 0)

    def test_invalid_date_redirects_without_creating(self):
        response = self.client.post(
            self.url,
            data={"date": "nao-e-data", "slots": ["10:00"]},
        )

        self.assertRedirects(response, reverse("appointments:visual_schedule"))
        self.assertEqual(ScheduleBlock.objects.count(), 0)

    def test_invalid_slot_values_are_ignored(self):
        self.block(["10:00", "vinte horas", "25:99"])

        blocks = list(ScheduleBlock.objects.all())

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].start_time, time(10, 0))

    def test_anonymous_user_cannot_block_slots(self):
        self.client.logout()

        response = self.block(["10:00"])

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ScheduleBlock.objects.count(), 0)

    def test_schedule_page_offers_the_checkboxes(self):
        response = self.client.get(
            reverse("appointments:visual_schedule")
            + f"?date={self.selected_date.isoformat()}"
        )

        self.assertContains(response, 'name="slots"')
        self.assertContains(response, "slot-blocking-form")
        # O botão diz só "Bloquear": a frase ao lado já diz quantos e quais.
        self.assertContains(response, "Bloquear")
        self.assertContains(response, "horários selecionados")
