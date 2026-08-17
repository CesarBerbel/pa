"""Transições de estado em marcações que o horário de hoje já não aceitaria.

Uma marcação é criada dentro do horário de funcionamento em vigor nesse dia. O
horário pode mudar depois — a clínica encurta a tarde, um serviço passa a durar
mais — e a marcação, que já foi feita e já aconteceu, deixa de caber nas regras
atuais. Concluí-la ou confirmá-la não pode falhar por causa disso: o que está a
ser gravado é o estado, não o horário.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment, AppointmentLog, BusinessHour, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from appointments.use_cases import (
    CompleteAppointmentUseCase,
    ConfirmAppointmentUseCase,
)


class StateChangeAfterScheduleChangeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
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

        self.date = timezone.localdate() + timedelta(days=14)
        while self.date.weekday() != 0:
            self.date += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.date.weekday(),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        # Marcada às 17:00, quando a clínica ainda fechava às 18:00.
        self.appointment = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(17, 0),
            status=Appointment.STATUS_CONFIRMED,
            created_by=self.user,
        )

        # A clínica passa a fechar às 16:00, e a marcação fica fora do horário.
        BusinessHour.objects.filter(weekday=self.date.weekday()).update(
            end_time=time(16, 0),
            second_start_time=None,
            second_end_time=None,
        )

    def test_completing_still_works_after_business_hours_shrink(self):
        resultado = CompleteAppointmentUseCase.execute(
            appointment=self.appointment, user=self.user
        )

        self.assertTrue(resultado.success)

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.STATUS_COMPLETED)

    def test_completing_records_the_audit_log(self):
        CompleteAppointmentUseCase.execute(
            appointment=self.appointment, user=self.user
        )

        self.assertTrue(
            AppointmentLog.objects.filter(
                appointment=self.appointment,
                action=AppointmentLog.ACTION_COMPLETE,
            ).exists()
        )

    def test_confirming_still_works_after_business_hours_shrink(self):
        self.appointment.status = Appointment.STATUS_SCHEDULED
        self.appointment.save(update_fields=["status"])

        resultado = ConfirmAppointmentUseCase.execute(
            appointment=self.appointment, user=self.user
        )

        self.assertTrue(resultado.success)

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.STATUS_CONFIRMED)

    def test_moving_the_appointment_is_still_validated(self):
        # O que a correção dispensa é revalidar uma marcação que não se mexeu.
        # Mudar-lhe a hora volta a ser medido contra o horário atual.
        self.appointment.start_time = time(17, 30)

        with self.assertRaises(ValidationError):
            self.appointment.save(update_fields=["start_time"])

    def test_a_full_save_is_still_validated(self):
        self.appointment.start_time = time(17, 30)

        with self.assertRaises(ValidationError):
            self.appointment.save()

    def test_creating_outside_business_hours_is_still_rejected(self):
        with self.assertRaises(ValidationError):
            Appointment.objects.create(
                customer=self.customer,
                service=self.service,
                date=self.date,
                start_time=time(17, 0),
                created_by=self.user,
            )
