"""O registo de auditoria: quem, quando, de onde e o que mudou.

O que se exige a um registo destes é que responda a perguntas feitas depois do
facto. Daí os testes seguirem sempre o mesmo par: a ação acontece e a linha
correspondente tem de trazer as quatro coisas, não uma frase a resumir.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.appointment_services import AppointmentService
from appointments.audit_services import AppointmentAuditService
from appointments.cancellation_services import AppointmentCancellationService
from appointments.models import Appointment, AppointmentLog, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from appointments.use_cases import (
    CompleteAppointmentUseCase,
    ConfirmAppointmentUseCase,
)


class AuditBase(TestCase):
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

    def marcacao(self, origin=Appointment.ORIGIN_INTERNAL, hora=time(10, 0), **extra):
        return Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=hora,
            created_by=self.user,
            origin=origin,
            **extra,
        )


class AppointmentOriginTests(AuditBase):
    def test_a_booking_made_on_the_site_is_marked_as_public(self):
        resultado = AppointmentService.create_appointment(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(11, 0),
            send_email=False,
            origin=Appointment.ORIGIN_PUBLIC,
        )

        self.assertTrue(resultado.success)
        self.assertEqual(resultado.appointment.origin, Appointment.ORIGIN_PUBLIC)

    def test_the_public_form_marks_the_booking_as_public(self):
        # O caminho que a cliente percorre no site, ponta a ponta. É o que
        # antes gravava a marcação em nome do administrador e a tornava
        # indistinguível de uma marcada pela equipa.
        resposta = self.client.post(
            reverse("appointments:public_appointment_create"),
            {
                "service": self.service.pk,
                "date": self.date.strftime("%Y-%m-%d"),
                "start_time": "11:00",
                "customer_name": "Ana Costa",
                "customer_phone": "+351910111222",
                "customer_email": "ana@example.com",
                "notes": "",
                "privacy_policy_accepted": "on",
            },
        )

        self.assertIn(resposta.status_code, (200, 302))

        marcacao = Appointment.objects.filter(customer__email="ana@example.com").first()

        self.assertIsNotNone(marcacao)
        self.assertEqual(marcacao.origin, Appointment.ORIGIN_PUBLIC)

    def test_a_booking_made_internally_is_marked_as_internal(self):
        self.client.force_login(self.user)

        self.client.post(
            reverse("appointments:appointment_create"),
            {
                "customer_mode": "existing",
                "customer": self.customer.pk,
                "service": self.service.pk,
                "date": self.date.strftime("%Y-%m-%d"),
                "start_time": "11:00",
                "status": Appointment.STATUS_SCHEDULED,
                "notes": "",
            },
        )

        marcacao = Appointment.objects.filter(start_time=time(11, 0)).first()

        self.assertIsNotNone(marcacao)
        self.assertEqual(marcacao.origin, Appointment.ORIGIN_INTERNAL)


class AuditTrailTests(AuditBase):
    def test_creating_internally_leaves_a_record(self):
        # Antes desta correção a criação pelo formulário interno não deixava
        # rasto: a história começava na primeira alteração.
        self.client.force_login(self.user)

        self.client.post(
            reverse("appointments:appointment_create"),
            {
                "customer_mode": "existing",
                "customer": self.customer.pk,
                "service": self.service.pk,
                "date": self.date.strftime("%Y-%m-%d"),
                "start_time": "11:00",
                "status": Appointment.STATUS_SCHEDULED,
                "notes": "",
            },
        )

        marcacao = Appointment.objects.filter(start_time=time(11, 0)).first()

        registo = AppointmentLog.objects.filter(
            appointment=marcacao,
            action=AppointmentLog.ACTION_CREATE,
        ).first()

        self.assertIsNotNone(registo)
        self.assertEqual(registo.performed_by, self.user)
        self.assertEqual(registo.source, AppointmentLog.SOURCE_INTERNAL)
        self.assertIsNotNone(registo.created_at)

    def test_an_edit_records_which_fields_changed(self):
        marcacao = self.marcacao(hora=time(10, 0))

        self.client.force_login(self.user)

        self.client.post(
            reverse("appointments:appointment_update", kwargs={"pk": marcacao.pk}),
            {
                "customer_mode": "existing",
                "customer": self.customer.pk,
                "service": self.service.pk,
                "date": self.date.strftime("%Y-%m-%d"),
                "start_time": "15:00",
                "status": Appointment.STATUS_SCHEDULED,
                "notes": "",
            },
        )

        registo = (
            AppointmentLog.objects.filter(
                appointment=marcacao,
                action=AppointmentLog.ACTION_UPDATE,
            )
            .order_by("-created_at")
            .first()
        )

        self.assertIsNotNone(registo)
        self.assertIn("start_time", registo.changes)
        self.assertEqual(registo.changes["start_time"]["de"], "10:00")
        self.assertEqual(registo.changes["start_time"]["para"], "15:00")

    def test_an_edit_that_changes_nothing_records_no_fields(self):
        marcacao = self.marcacao(hora=time(10, 0))

        self.client.force_login(self.user)

        self.client.post(
            reverse("appointments:appointment_update", kwargs={"pk": marcacao.pk}),
            {
                "customer_mode": "existing",
                "customer": self.customer.pk,
                "service": self.service.pk,
                "date": self.date.strftime("%Y-%m-%d"),
                "start_time": "10:00",
                "status": Appointment.STATUS_SCHEDULED,
                "notes": "",
            },
        )

        registo = (
            AppointmentLog.objects.filter(
                appointment=marcacao,
                action=AppointmentLog.ACTION_UPDATE,
            )
            .order_by("-created_at")
            .first()
        )

        self.assertEqual(registo.changes, {})

    def test_confirming_records_the_status_change(self):
        marcacao = self.marcacao()

        ConfirmAppointmentUseCase.execute(
            appointment=marcacao, user=self.user, send_email=False
        )

        registo = AppointmentLog.objects.filter(
            appointment=marcacao,
            action=AppointmentLog.ACTION_CONFIRM,
        ).first()

        self.assertEqual(registo.source, AppointmentLog.SOURCE_INTERNAL)
        self.assertIn("status", registo.changes)

    def test_completing_records_the_status_change(self):
        marcacao = self.marcacao(status=Appointment.STATUS_CONFIRMED)

        CompleteAppointmentUseCase.execute(appointment=marcacao, user=self.user)

        registo = AppointmentLog.objects.filter(
            appointment=marcacao,
            action=AppointmentLog.ACTION_COMPLETE,
        ).first()

        self.assertEqual(registo.performed_by, self.user)
        self.assertIn("status", registo.changes)

    def test_a_cancellation_from_the_site_is_not_credited_to_the_team(self):
        # O ponto todo da distinção: sem isto, a cliente a desmarcar-se pelo
        # site ficava registada como se tivesse sido a equipa a desmarcá-la.
        marcacao = self.marcacao(origin=Appointment.ORIGIN_PUBLIC)

        AppointmentCancellationService.cancel(
            appointment=marcacao,
            cancellation_reason="Não posso comparecer.",
            source=AppointmentLog.SOURCE_PUBLIC,
        )

        registo = AppointmentLog.objects.filter(
            appointment=marcacao,
            action=AppointmentLog.ACTION_CANCEL,
        ).first()

        self.assertEqual(registo.source, AppointmentLog.SOURCE_PUBLIC)
        self.assertIsNone(registo.performed_by)
        self.assertIn("status", registo.changes)

    def test_an_internal_cancellation_keeps_the_author(self):
        marcacao = self.marcacao()

        AppointmentCancellationService.cancel(
            appointment=marcacao,
            user=self.user,
            cancellation_reason="Agenda reorganizada.",
            source=AppointmentLog.SOURCE_INTERNAL,
        )

        registo = AppointmentLog.objects.filter(
            appointment=marcacao,
            action=AppointmentLog.ACTION_CANCEL,
        ).first()

        self.assertEqual(registo.source, AppointmentLog.SOURCE_INTERNAL)
        self.assertEqual(registo.performed_by, self.user)


class AuditDiffTests(AuditBase):
    def test_the_diff_reads_in_human_terms(self):
        marcacao = self.marcacao(hora=time(10, 0))

        antes = AppointmentAuditService.snapshot(marcacao)

        marcacao.start_time = time(16, 30)

        alteracoes = AppointmentAuditService.diff(
            antes, AppointmentAuditService.snapshot(marcacao)
        )

        # "10:00" e não "datetime.time(10, 0)": quem lê a auditoria não lê
        # objetos de Python.
        self.assertEqual(
            alteracoes["start_time"], {"de": "10:00", "para": "16:30"}
        )

    def test_the_changed_fields_carry_readable_labels(self):
        marcacao = self.marcacao()

        registo = AppointmentAuditService.log(
            appointment=marcacao,
            action=AppointmentLog.ACTION_UPDATE,
            user=self.user,
            changes={"start_time": {"de": "10:00", "para": "11:00"}},
        )

        campos = registo.changed_fields

        self.assertEqual(campos[0]["label"], "Hora")
        self.assertEqual(campos[0]["from"], "10:00")
        self.assertEqual(campos[0]["to"], "11:00")


class AuditPageTests(AuditBase):
    def setUp(self):
        super().setUp()

        self.url = reverse("appointments:appointment_audit")

    def test_the_page_is_closed_to_outsiders(self):
        resposta = self.client.get(self.url)

        self.assertNotEqual(resposta.status_code, 200)

    def test_the_page_lists_the_records(self):
        marcacao = self.marcacao()

        AppointmentAuditService.log(
            appointment=marcacao,
            action=AppointmentLog.ACTION_UPDATE,
            user=self.user,
            changes={"start_time": {"de": "10:00", "para": "11:00"}},
        )

        self.client.force_login(self.user)

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, marcacao.reference_code)
        self.assertContains(resposta, "Hora")

    def test_it_filters_by_source(self):
        publica = self.marcacao(origin=Appointment.ORIGIN_PUBLIC, hora=time(10, 0))
        interna = self.marcacao(origin=Appointment.ORIGIN_INTERNAL, hora=time(11, 0))

        AppointmentAuditService.log(
            appointment=publica,
            action=AppointmentLog.ACTION_CREATE,
            source=AppointmentLog.SOURCE_PUBLIC,
        )
        AppointmentAuditService.log(
            appointment=interna,
            action=AppointmentLog.ACTION_CREATE,
            source=AppointmentLog.SOURCE_INTERNAL,
        )

        self.client.force_login(self.user)

        resposta = self.client.get(self.url, {"source": AppointmentLog.SOURCE_PUBLIC})

        codigos = [
            registo.appointment.reference_code for registo in resposta.context["logs"]
        ]

        self.assertIn(publica.reference_code, codigos)
        self.assertNotIn(interna.reference_code, codigos)

    def test_it_filters_by_action(self):
        marcacao = self.marcacao()

        AppointmentAuditService.log(
            appointment=marcacao, action=AppointmentLog.ACTION_CREATE
        )
        AppointmentAuditService.log(
            appointment=marcacao, action=AppointmentLog.ACTION_UPDATE
        )

        self.client.force_login(self.user)

        resposta = self.client.get(self.url, {"action": AppointmentLog.ACTION_UPDATE})

        acoes = {registo.action for registo in resposta.context["logs"]}

        self.assertEqual(acoes, {AppointmentLog.ACTION_UPDATE})

    def test_it_searches_by_reference_code(self):
        marcacao = self.marcacao()

        AppointmentAuditService.log(
            appointment=marcacao, action=AppointmentLog.ACTION_CREATE
        )

        self.client.force_login(self.user)

        resposta = self.client.get(self.url, {"q": marcacao.reference_code})

        self.assertEqual(len(resposta.context["logs"]), 1)

    def test_the_records_come_newest_first(self):
        marcacao = self.marcacao()

        primeiro = AppointmentAuditService.log(
            appointment=marcacao, action=AppointmentLog.ACTION_CREATE
        )
        segundo = AppointmentAuditService.log(
            appointment=marcacao, action=AppointmentLog.ACTION_UPDATE
        )

        self.client.force_login(self.user)

        resposta = self.client.get(self.url)
        registos = list(resposta.context["logs"])

        self.assertEqual(registos[0].pk, segundo.pk)
        self.assertEqual(registos[1].pk, primeiro.pk)
