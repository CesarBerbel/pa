from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.availability import AvailabilityService
from appointments.cancellation_services import AppointmentCancellationService
from appointments.models import (
    Appointment,
    AppointmentLog,
    BusinessHour,
    Customer,
    SchedulingSetting,
)
from appointments.tests.factories import create_test_service
from appointments.weekly_schedule import build_week


def definir(**regras):
    definicao = SchedulingSetting.load()

    for campo, valor in regras.items():
        setattr(definicao, campo, valor)

    definicao.save()

    return definicao


class SchedulingSettingModelTests(TestCase):
    def test_the_factory_values_hold_before_anyone_saves_anything(self):
        SchedulingSetting.objects.all().delete()

        self.assertEqual(SchedulingSetting.get_slot_minutes(), 30)
        self.assertEqual(SchedulingSetting.get_booking_min_advance_hours(), 3)

    def test_reading_a_rule_never_writes(self):
        # Estas leituras acontecem a desenhar páginas. Um GET que grava é um
        # GET que falha numa réplica de leitura, e que suja o histórico.
        SchedulingSetting.objects.all().delete()

        SchedulingSetting.get_slot_minutes()

        self.assertEqual(SchedulingSetting.objects.count(), 0)

    def test_only_one_row_ever_exists(self):
        SchedulingSetting.load()

        outra = SchedulingSetting(slot_minutes=15)
        outra.save()

        self.assertEqual(SchedulingSetting.objects.count(), 1)
        self.assertEqual(SchedulingSetting.get_slot_minutes(), 15)


class GridFollowsTheIntervalTests(TestCase):
    """A grelha desenha-se com o intervalo escolhido, e não com 30 fixos."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        for weekday in range(7):
            BusinessHour.objects.update_or_create(
                weekday=weekday,
                defaults={
                    "start_time": time(9, 0),
                    "end_time": time(12, 0),
                    # As horas semeadas trazem um segundo período à tarde. Sem
                    # o limpar, o dia deste teste não era o dia de três horas
                    # que ele diz ser.
                    "second_start_time": None,
                    "second_end_time": None,
                    "is_active": True,
                },
            )

        hoje = timezone.localdate()
        self.segunda = hoje - timedelta(days=hoje.weekday())

    def test_the_rows_follow_the_chosen_interval(self):
        # Três horas de expediente: 12 linhas de 15, 6 de 30, 3 de uma hora.
        for minutos, linhas in [(15, 12), (30, 6), (60, 3)]:
            with self.subTest(intervalo=minutos):
                definir(slot_minutes=minutos)

                self.assertEqual(build_week(self.segunda).rows, linhas)

    def test_the_public_slots_follow_it_too(self):
        # A agenda interna e o site têm de oferecer as mesmas horas: se
        # divergirem, alguém marca num horário que a outra não conhece.
        definir(slot_minutes=60)
        servico = create_test_service(duration_minutes=60)

        horarios = AvailabilityService.get_available_slots(servico, self.segunda)

        self.assertEqual(
            [slot["value"] for slot in horarios], ["09:00", "10:00", "11:00"]
        )

    def test_a_shorter_interval_offers_more_starting_times(self):
        definir(slot_minutes=30)
        servico = create_test_service(duration_minutes=60)

        horarios = AvailabilityService.get_available_slots(servico, self.segunda)

        self.assertIn("09:30", [slot["value"] for slot in horarios])


class FreeCellsInviteToBookTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva", phone="+351910000000"
        )
        self.service = create_test_service(duration_minutes=60)

        for weekday in range(7):
            BusinessHour.objects.update_or_create(
                weekday=weekday,
                defaults={
                    "start_time": time(9, 0),
                    "end_time": time(12, 0),
                    # As horas semeadas trazem um segundo período à tarde. Sem
                    # o limpar, o dia deste teste não era o dia de três horas
                    # que ele diz ser.
                    "second_start_time": None,
                    "second_end_time": None,
                    "is_active": True,
                },
            )

        hoje = timezone.localdate()
        self.segunda = hoje - timedelta(days=hoje.weekday())

        definir(slot_minutes=60)

        self.client.force_login(self.user)

    def horas_livres(self, dia_indice=0):
        semana = build_week(self.segunda)

        return [
            celula.time.strftime("%H:%M")
            for celula in semana.days[dia_indice].cells
            if celula.is_free
        ]

    def test_an_empty_day_is_free_end_to_end(self):
        self.assertEqual(self.horas_livres(), ["09:00", "10:00", "11:00"])

    def test_an_appointment_takes_its_hours_out(self):
        Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.segunda,
            start_time=time(10, 0),
            created_by=self.user,
        )

        self.assertEqual(self.horas_livres(), ["09:00", "11:00"])

    def test_hours_outside_the_working_day_are_not_free(self):
        # Fora do horário não é livre: é fechado. Convidar a marcar ali era
        # convidar para um encaixe sem o dizer.
        horas = self.horas_livres()

        self.assertNotIn("08:00", horas)
        self.assertNotIn("12:00", horas)

    def test_the_grid_links_each_free_hour_to_a_new_appointment(self):
        html = self.client.get(reverse("appointments:weekly_schedule")).content.decode()

        endereco = (
            f"{reverse('appointments:appointment_create')}"
            f"?date={self.segunda:%Y-%m-%d}&start_time=09:00"
        )

        self.assertIn(endereco, html)

    def test_the_new_appointment_form_opens_already_filled(self):
        resposta = self.client.get(
            reverse("appointments:appointment_create"),
            {"date": self.segunda.isoformat(), "start_time": "09:00"},
        )

        formulario = resposta.context["form"]

        self.assertEqual(formulario.initial["date"], self.segunda.isoformat())
        self.assertEqual(formulario.initial["start_time"], "09:00")


class CancellationDeadlineTests(TestCase):
    """O prazo para a cliente cancelar sozinha."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva", phone="+351910000000"
        )
        self.service = create_test_service(duration_minutes=60)

        for weekday in range(7):
            BusinessHour.objects.update_or_create(
                weekday=weekday,
                defaults={
                    "start_time": time(0, 0),
                    "end_time": time(23, 30),
                    "is_active": True,
                },
            )

    def marcar(self, daqui_a_horas):
        momento = timezone.localtime() + timedelta(hours=daqui_a_horas)

        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=momento.date(),
            start_time=time(momento.hour, 0),
            created_by=self.user,
            outside_schedule=True,
        )

    def cancelar_pelo_site(self, marcacao):
        return AppointmentCancellationService.cancel(
            appointment=marcacao,
            cancellation_reason="Não consigo comparecer nesta data.",
            source=AppointmentLog.SOURCE_PUBLIC,
        )

    def test_without_a_deadline_the_customer_can_always_cancel(self):
        definir(cancellation_min_advance_hours=0)

        self.assertTrue(self.cancelar_pelo_site(self.marcar(1)).success)

    def test_inside_the_deadline_the_customer_is_sent_to_the_phone(self):
        definir(cancellation_min_advance_hours=24)

        resultado = self.cancelar_pelo_site(self.marcar(2))

        self.assertFalse(resultado.success)
        self.assertIn("Ligue-nos", resultado.message)

    def test_outside_the_deadline_the_customer_still_cancels(self):
        definir(cancellation_min_advance_hours=24)

        self.assertTrue(self.cancelar_pelo_site(self.marcar(48)).success)

    def test_the_clinic_cancels_at_any_time(self):
        # O prazo protege a agenda de uma desmarcação em cima da hora. Quem
        # fica com o horário vazio é a clínica, e por isso ela decide sempre.
        definir(cancellation_min_advance_hours=24)

        resultado = AppointmentCancellationService.cancel(
            appointment=self.marcar(1),
            user=self.user,
            cancellation_reason="A profissional está doente.",
            source=AppointmentLog.SOURCE_INTERNAL,
        )

        self.assertTrue(resultado.success)


class SchedulingSettingViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.client.force_login(self.user)
        self.url = reverse("appointments:scheduling_setting")

    def test_it_is_closed_to_who_is_not_from_the_internal_area(self):
        self.client.logout()

        self.assertNotEqual(self.client.get(self.url).status_code, 200)

    def test_it_offers_the_three_interval_choices(self):
        html = self.client.get(self.url).content.decode()

        for rotulo in ["15 minutos", "30 minutos", "1 hora"]:
            with self.subTest(intervalo=rotulo):
                self.assertIn(rotulo, html)

    def test_saving_records_who_changed_it(self):
        self.client.post(
            self.url,
            {
                "slot_minutes": 15,
                "booking_min_advance_hours": 6,
                "booking_horizon_days": 30,
                "cancellation_min_advance_hours": 12,
            },
        )

        definicao = SchedulingSetting.load()

        self.assertEqual(definicao.slot_minutes, 15)
        self.assertEqual(definicao.booking_min_advance_hours, 6)
        self.assertEqual(definicao.updated_by, self.user)

    def test_a_horizon_of_zero_days_is_refused(self):
        # Fechava o site a marcações sem o dizer em lado nenhum.
        resposta = self.client.post(
            self.url,
            {
                "slot_minutes": 30,
                "booking_min_advance_hours": 3,
                "booking_horizon_days": 0,
                "cancellation_min_advance_hours": 0,
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["form"].errors)

    def test_it_is_reachable_from_the_settings_menu(self):
        html = self.client.get(reverse("dashboard")).content.decode()

        self.assertIn(self.url, html)
