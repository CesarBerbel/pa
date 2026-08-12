from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from appointments.models import (
    Appointment,
    BusinessHour,
    ClinicalNote,
    Customer,
    PatientRecord,
    PatientRecordLog,
)
from appointments.tests.factories import create_test_service


class ClinicalAccessLevelTests(TestCase):
    """A informação clínica é um nível de acesso separado da área interna.

    Quem trabalha na receção precisa de gerir marcações e clientes, mas não
    deve ver a anamnese nem as notas de evolução.
    """

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.reception = User.objects.create_user(
            email="rececao@example.com",
            password="StrongPassword123",
            full_name="Receção",
            is_internal_staff=True,
        )

        self.client_user = User.objects.create_user(
            email="cliente@example.com",
            password="StrongPassword123",
            full_name="Cliente",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.service = create_test_service()
        self.appointment_date = date(2026, 5, 4)

        BusinessHour.objects.update_or_create(
            weekday=self.appointment_date.weekday(),
            defaults={
                "start_time": time(9, 0),
                "end_time": time(18, 0),
                "is_active": True,
            },
        )

        self.appointment = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.owner,
            date=self.appointment_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        self.record_url = reverse(
            "appointments:patient_record", kwargs={"pk": self.customer.pk}
        )
        self.note_url = reverse(
            "appointments:clinical_note", kwargs={"pk": self.appointment.pk}
        )

    def test_reception_reaches_the_internal_area(self):
        self.client.force_login(self.reception)

        self.assertEqual(
            self.client.get(reverse("appointments:appointment_list")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("appointments:customer_list")).status_code, 200
        )

    def test_reception_cannot_open_the_anamnesis(self):
        self.client.force_login(self.reception)

        response = self.client.get(self.record_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("home"))
        self.assertEqual(PatientRecord.objects.count(), 0)

    def test_reception_cannot_open_a_clinical_note(self):
        self.client.force_login(self.reception)

        response = self.client.get(self.note_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ClinicalNote.objects.count(), 0)

    def test_reception_does_not_see_clinical_alerts_in_the_customer_list(self):
        PatientRecord.objects.create(customer=self.customer, has_diabetes=True)

        self.client.force_login(self.reception)
        response = self.client.get(reverse("appointments:customer_list"))

        self.assertNotContains(response, "Diabetes")
        self.assertNotContains(response, "Ficha de anamnese de Maria Silva")

    def test_owner_sees_clinical_alerts_in_the_customer_list(self):
        PatientRecord.objects.create(customer=self.customer, has_diabetes=True)

        self.client.force_login(self.owner)
        response = self.client.get(reverse("appointments:customer_list"))

        self.assertContains(response, "Diabetes")

    def test_staff_with_clinical_flag_reaches_the_anamnesis(self):
        clinical = get_user_model().objects.create_user(
            email="clinica@example.com",
            password="StrongPassword123",
            full_name="Profissional",
            is_internal_staff=True,
            can_access_clinical_data=True,
        )

        self.client.force_login(clinical)

        self.assertEqual(self.client.get(self.record_url).status_code, 200)

    def test_plain_customer_reaches_nothing(self):
        self.client.force_login(self.client_user)

        self.assertEqual(
            self.client.get(reverse("appointments:appointment_list")).status_code, 302
        )
        self.assertEqual(self.client.get(self.record_url).status_code, 302)


class PatientRecordHistoryTests(TestCase):
    # A conservação digital exige garantir integridade: é preciso saber o que
    # mudou, quando e por quem.

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.client.force_login(self.owner)
        self.url = reverse(
            "appointments:patient_record", kwargs={"pk": self.customer.pk}
        )

    def payload(self, **overrides):
        data = {
            "main_complaint": "",
            "allergies": "",
            "medical_history": "",
            "current_medication": "",
            "previous_surgeries": "",
            "footwear_notes": "",
            "notes": "",
        }
        data.update(overrides)
        return data

    def test_first_save_records_what_changed(self):
        self.client.post(self.url, data=self.payload(main_complaint="Dor no pé."))

        log = PatientRecordLog.objects.get()

        self.assertEqual(log.performed_by, self.owner)
        self.assertIn("Motivo da consulta", log.description)
        self.assertIn("Dor no pé.", log.description)

    def test_history_keeps_the_previous_value(self):
        self.client.post(
            self.url, data=self.payload(has_allergies="on", allergies="Iodo.")
        )
        self.client.post(
            self.url, data=self.payload(has_allergies="on", allergies="Nenhuma.")
        )

        ultimo = PatientRecordLog.objects.first()

        # Sem o valor anterior seria impossível perceber que a alergia foi
        # substituída por engano.
        self.assertIn("Iodo.", ultimo.description)
        self.assertIn("Nenhuma.", ultimo.description)

    def test_saving_without_changes_adds_nothing(self):
        self.client.post(self.url, data=self.payload(main_complaint="Dor no pé."))
        self.client.post(self.url, data=self.payload(main_complaint="Dor no pé."))

        self.assertEqual(PatientRecordLog.objects.count(), 1)

    def test_history_is_shown_on_the_record_page(self):
        self.client.post(self.url, data=self.payload(main_complaint="Dor no pé."))

        response = self.client.get(self.url)

        self.assertContains(response, "Histórico de alterações")
        self.assertContains(response, "Motivo da consulta")


class ClinicalNoteTests(TestCase):
    # As notas de evolução guardam os atos praticados em cada consulta.

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.service = create_test_service()
        self.appointment_date = date(2026, 5, 4)

        BusinessHour.objects.update_or_create(
            weekday=self.appointment_date.weekday(),
            defaults={
                "start_time": time(9, 0),
                "end_time": time(18, 0),
                "is_active": True,
            },
        )

        self.appointment = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.owner,
            date=self.appointment_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_SCHEDULED,
        )

        self.client.force_login(self.owner)
        self.url = reverse(
            "appointments:clinical_note", kwargs={"pk": self.appointment.pk}
        )

    def test_opening_creates_an_empty_note(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ClinicalNote.objects.count(), 1)

    def test_page_is_not_indexable(self):
        self.assertContains(self.client.get(self.url), "noindex,nofollow")

    def test_procedures_are_required(self):
        response = self.client.post(
            self.url,
            data={"procedures": "   ", "observations": "", "recommendations": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("procedures", response.context["form"].errors)

    def test_saving_stores_the_note(self):
        self.client.post(
            self.url,
            data={
                "procedures": "Desbaste de calo no antepé direito.",
                "observations": "Pele seca.",
                "recommendations": "Hidratar diariamente.",
            },
        )

        note = ClinicalNote.objects.get()

        self.assertEqual(note.appointment, self.appointment)
        self.assertEqual(note.created_by, self.owner)
        self.assertIn("Desbaste de calo", note.procedures)

    def test_note_appears_in_the_patient_history(self):
        self.client.post(
            self.url,
            data={
                "procedures": "Desbaste de calo no antepé direito.",
                "observations": "",
                "recommendations": "",
            },
        )

        response = self.client.get(
            reverse("appointments:patient_record", kwargs={"pk": self.customer.pk})
        )

        self.assertContains(response, "Consultas anteriores")
        self.assertContains(response, "Desbaste de calo")

    def test_note_is_removed_with_the_appointment(self):
        self.client.post(
            self.url,
            data={"procedures": "Feito.", "observations": "", "recommendations": ""},
        )

        self.appointment.delete()

        self.assertEqual(ClinicalNote.objects.count(), 0)
