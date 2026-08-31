"""Marcações e bloqueios cuja hora não cai na grelha da agenda.

A grelha da agenda interna anda de `slot_minutes` em `slot_minutes` a partir da
hora de abertura. Um encaixe às 16:45 numa grelha de 30 minutos não coincide
com linha nenhuma — e a linha de início era escolhida por **igualdade**.

O resultado era o pior tipo de defeito de um ecrã de agenda: não dava erro.

* a marcação **desaparecia**, sem aparecer em linha nenhuma;
* a linha das 16:30 dizia "horário livre", com um botão de marcar por cima de
  alguém que já lá estava;
* as linhas das 17:00 e 17:30 diziam "ocupado pelo atendimento acima" — a
  apontar para um atendimento que não se via.

Estes testes fixam a regra: a linha de início é a que **contém** o começo.
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase

from appointments.availability import AvailabilityService
from appointments.models import Appointment, Customer, ScheduleBlock
from appointments.tests.factories import create_test_service, ensure_test_business_hour

# Uma quarta-feira, escolhida à mão. Relativa a hoje, a grelha mudava de
# feriado para fim de semana conforme o dia em que os testes corressem.
DIA = date(2027, 4, 14)


class OffGridBase(TestCase):
    def setUp(self):
        ensure_test_business_hour(
            weekday=DIA.weekday(), start_time=time(9, 0), end_time=time(18, 0)
        )

        self.utilizador = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.servico = create_test_service(duration_minutes=60)

        self.cliente = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@exemplo.pt",
            phone="+351910000000",
        )

    def grelha(self):
        _, slots = AvailabilityService.build_visual_slots(DIA, slot_minutes=30)

        return {slot["time"]: slot for slot in slots}

    def marcar(self, hora):
        return Appointment.objects.create(
            customer=self.cliente,
            service=self.servico,
            date=DIA,
            start_time=hora,
            status=Appointment.STATUS_CONFIRMED,
            created_by=self.utilizador,
        )


class AnAppointmentOffTheGridTests(OffGridBase):
    def test_it_shows_up_on_the_row_that_contains_it(self):
        # Às 16:45, numa grelha de meia hora: aparece na linha das 16:30.
        self.marcar(time(16, 45))

        grelha = self.grelha()

        self.assertTrue(grelha[time(16, 30)]["is_appointment_start"])

    def test_the_row_that_contains_it_is_not_offered_as_free(self):
        # Era o defeito com consequências: um botão "marcar" por cima de uma
        # pessoa que já lá estava.
        self.marcar(time(16, 45))

        self.assertTrue(self.grelha()[time(16, 30)]["is_inside_appointment"])

    def test_it_does_not_vanish_from_the_day(self):
        marcacao = self.marcar(time(16, 45))

        visiveis = [
            slot["appointment"]
            for slot in self.grelha().values()
            if slot["is_appointment_start"]
        ]

        self.assertIn(marcacao, visiveis)

    def test_no_row_claims_to_be_busy_without_something_visible_above_it(self):
        """A regra que descreve o ecrã inteiro.

        "Ocupado pelo atendimento acima" só se pode escrever se houver mesmo um
        atendimento acima. É esta a asserção que apanha o defeito em qualquer
        combinação de horas, e não só na que foi denunciada.
        """

        self.marcar(time(16, 45))

        visto = None

        for hora, slot in sorted(self.grelha().items()):
            if slot["is_appointment_start"]:
                visto = slot["appointment"]
            elif slot["is_inside_appointment"]:
                self.assertIsNotNone(
                    visto,
                    f"a linha das {hora:%H:%M} diz-se ocupada sem nada visível acima",
                )
            else:
                visto = None

    def test_the_card_is_tall_enough_for_the_rows_it_eats(self):
        # 16:45 mais uma hora acaba às 17:45: ocupa as linhas 16:30, 17:00 e
        # 17:30 — três, e não as duas que a duração sozinha sugeria.
        self.marcar(time(16, 45))

        self.assertEqual(self.grelha()[time(16, 30)]["block_slots"], 3)

    def test_a_later_row_inside_it_still_says_so(self):
        self.marcar(time(16, 45))

        grelha = self.grelha()

        self.assertTrue(grelha[time(17, 0)]["is_inside_appointment"])
        self.assertFalse(grelha[time(17, 0)]["is_appointment_start"])

    def test_the_row_before_it_stays_free(self):
        # Não basta deixar de mentir num sítio: as 16:00 estão mesmo livres.
        self.marcar(time(16, 45))

        self.assertFalse(self.grelha()[time(16, 0)]["is_inside_appointment"])


class AnAppointmentOnTheGridStillWorksTests(OffGridBase):
    """O caso normal não pode ter mudado."""

    def test_it_starts_on_its_own_row(self):
        self.marcar(time(16, 0))

        grelha = self.grelha()

        self.assertTrue(grelha[time(16, 0)]["is_appointment_start"])
        self.assertTrue(grelha[time(16, 30)]["is_inside_appointment"])
        self.assertFalse(grelha[time(16, 30)]["is_appointment_start"])

    def test_the_height_is_the_one_it_always_was(self):
        # Uma hora em linhas de meia hora: duas linhas.
        self.marcar(time(16, 0))

        self.assertEqual(self.grelha()[time(16, 0)]["block_slots"], 2)

    def test_the_row_after_it_ends_is_free_again(self):
        self.marcar(time(16, 0))

        self.assertFalse(self.grelha()[time(17, 0)]["is_inside_appointment"])


class ABlockOffTheGridTests(OffGridBase):
    """O mesmo defeito, do lado dos bloqueios."""

    def bloquear(self, inicio, fim):
        return ScheduleBlock.objects.create(
            date=DIA,
            start_time=inicio,
            end_time=fim,
            block_type=ScheduleBlock.BLOCK_TYPE_OTHER,
            is_active=True,
        )

    def test_it_shows_up_on_the_row_that_contains_it(self):
        self.bloquear(time(16, 45), time(17, 45))

        self.assertTrue(self.grelha()[time(16, 30)]["is_block_start"])

    def test_no_row_is_inside_a_block_nobody_can_see(self):
        self.bloquear(time(16, 45), time(17, 45))

        visto = False

        for hora, slot in sorted(self.grelha().items()):
            if slot["is_block_start"]:
                visto = True
            elif slot["is_inside_block"]:
                self.assertTrue(
                    visto,
                    f"a linha das {hora:%H:%M} diz-se bloqueada sem nada visível acima",
                )
            else:
                visto = False

    def test_a_block_on_the_grid_still_starts_on_its_own_row(self):
        self.bloquear(time(16, 0), time(17, 0))

        grelha = self.grelha()

        self.assertTrue(grelha[time(16, 0)]["is_block_start"])
        self.assertEqual(grelha[time(16, 0)]["block_slots"], 2)
