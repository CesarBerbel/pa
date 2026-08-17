"""O que a lista de marcações mostra sem ninguém lhe pedir nada.

O ecrã é uma ferramenta de trabalho: por omissão fica pelo que está para vir e
deixa as canceladas de fora. O que estes testes guardam é o outro lado — que
nenhuma marcação fica inalcançável por causa disso. Procurar por um código,
escolher datas ou filtrar pelo estado tem de trazer o que existe, mesmo que
seja passado e cancelado.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, Customer
from appointments.selectors import AppointmentFilters, AppointmentSelectors
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class ListScopeBase(TestCase):
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

        self.hoje = timezone.localdate()

        for dia in range(0, 7):
            ensure_test_business_hour(
                weekday=dia, start_time=time(8, 0), end_time=time(20, 0)
            )

        self.futura = self.marcar(self.hoje + timedelta(days=7), time(10, 0))
        self.hoje_cedo = self.marcar(self.hoje, time(9, 0))
        self.passada = self.marcar(self.hoje - timedelta(days=7), time(10, 0))
        self.cancelada = self.marcar(
            self.hoje + timedelta(days=8),
            time(11, 0),
            status=Appointment.STATUS_CANCELLED,
        )

        self.client.force_login(self.user)
        self.url = reverse("appointments:appointment_list")

    def marcar(self, data, hora, status=Appointment.STATUS_SCHEDULED):
        marcacao = Appointment(
            customer=self.customer,
            service=self.service,
            date=data,
            start_time=hora,
            status=status,
            created_by=self.user,
        )

        # Uma marcação no passado não passa na validação de agendamento, e é
        # justamente o que este ecrã tem de saber esconder.
        marcacao.reference_code = marcacao.generate_reference_code()
        super(Appointment, marcacao).save()

        return marcacao

    def listar(self, **params):
        resposta = self.client.get(self.url, params)

        return list(resposta.context["appointments"])


class DefaultScopeTests(ListScopeBase):
    def test_it_shows_what_is_still_to_come(self):
        marcacoes = self.listar()

        self.assertIn(self.futura, marcacoes)

    def test_it_keeps_todays_earlier_appointments(self):
        # Marcada para as 09:00 e já são 11:00: continua a fazer falta, é
        # nela que se vai carregar para concluir o atendimento.
        marcacoes = self.listar()

        self.assertIn(self.hoje_cedo, marcacoes)

    def test_it_leaves_out_the_past(self):
        marcacoes = self.listar()

        self.assertNotIn(self.passada, marcacoes)

    def test_it_leaves_out_the_cancelled(self):
        marcacoes = self.listar()

        self.assertNotIn(self.cancelada, marcacoes)


class AskingForMoreTests(ListScopeBase):
    def test_filtering_by_cancelled_brings_them_back(self):
        marcacoes = self.listar(status=Appointment.STATUS_CANCELLED)

        self.assertIn(self.cancelada, marcacoes)

    def test_filtering_by_cancelled_also_finds_past_ones(self):
        antiga = self.marcar(
            self.hoje - timedelta(days=20),
            time(15, 0),
            status=Appointment.STATUS_CANCELLED,
        )

        marcacoes = self.listar(status=Appointment.STATUS_CANCELLED)

        self.assertIn(antiga, marcacoes)

    def test_choosing_dates_reaches_the_past(self):
        marcacoes = self.listar(
            date_from=(self.hoje - timedelta(days=30)).strftime("%Y-%m-%d"),
            date_to=self.hoje.strftime("%Y-%m-%d"),
        )

        self.assertIn(self.passada, marcacoes)

    def test_searching_finds_a_past_appointment(self):
        # Procurar por um código é procurar por aquela marcação. Responder
        # "não encontrada" sobre uma que existe seria pior do que mostrar
        # histórico a mais.
        marcacoes = self.listar(q=self.passada.reference_code)

        self.assertIn(self.passada, marcacoes)

    def test_searching_finds_a_cancelled_appointment(self):
        marcacoes = self.listar(q=self.cancelada.reference_code)

        self.assertIn(self.cancelada, marcacoes)

    def test_show_all_brings_everything(self):
        marcacoes = self.listar(all="1")

        for marcacao in (self.futura, self.hoje_cedo, self.passada, self.cancelada):
            self.assertIn(marcacao, marcacoes)

    def test_show_all_survives_filtering_by_service(self):
        marcacoes = self.listar(all="1", service=self.service.pk)

        self.assertIn(self.passada, marcacoes)


class ScopeNoticeTests(ListScopeBase):
    def test_the_page_says_what_it_is_hiding(self):
        resposta = self.client.get(self.url)

        self.assertTrue(resposta.context["filters"]["limits_to_upcoming"])
        self.assertTrue(resposta.context["filters"]["hides_cancelled"])
        self.assertContains(resposta, "Ver todas")

    def test_the_notice_goes_away_when_showing_everything(self):
        resposta = self.client.get(self.url, {"all": "1"})

        self.assertFalse(resposta.context["filters"]["limits_to_upcoming"])
        self.assertFalse(resposta.context["filters"]["hides_cancelled"])
        self.assertContains(resposta, "Voltar às próximas marcações")


class FilterFlagTests(TestCase):
    def test_a_bare_filter_limits_and_hides(self):
        filtros = AppointmentFilters()

        self.assertTrue(filtros.limits_to_upcoming)
        self.assertTrue(filtros.hides_cancelled)

    def test_a_service_filter_does_not_widen_the_scope(self):
        # Filtrar por serviço é estreitar o que já se está a ver, não pedir
        # para olhar para o arquivo.
        filtros = AppointmentFilters(service="1")

        self.assertTrue(filtros.limits_to_upcoming)
        self.assertTrue(filtros.hides_cancelled)

    def test_a_search_widens_the_scope(self):
        filtros = AppointmentFilters(q="AGD-123456")

        self.assertFalse(filtros.limits_to_upcoming)
        self.assertFalse(filtros.hides_cancelled)

    def test_a_status_filter_stops_hiding_cancelled(self):
        filtros = AppointmentFilters(status=Appointment.STATUS_CANCELLED)

        self.assertFalse(filtros.hides_cancelled)

    def test_asking_for_cancelled_reaches_the_past(self):
        # A maior parte das canceladas está no passado: manter o limite do
        # futuro esvaziava o filtro e dava a entender que não havia nenhuma.
        filtros = AppointmentFilters(status=Appointment.STATUS_CANCELLED)

        self.assertFalse(filtros.limits_to_upcoming)

    def test_other_status_filters_still_limit_to_upcoming(self):
        # Filtrar por "Agendada" é olhar para o trabalho que aí vem, não para
        # tudo o que alguma vez esteve agendado.
        filtros = AppointmentFilters(status=Appointment.STATUS_SCHEDULED)

        self.assertTrue(filtros.limits_to_upcoming)

    def test_dates_widen_the_scope(self):
        filtros = AppointmentFilters(date_from="2020-01-01")

        self.assertFalse(filtros.limits_to_upcoming)
