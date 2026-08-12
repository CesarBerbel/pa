from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from appointments.models import Customer, PatientRecord


class PatientRecordAccessTests(TestCase):
    # A ficha contém dados de saúde: só a área interna lhe pode chegar.

    def setUp(self):
        User = get_user_model()

        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.normal_user = User.objects.create_user(
            email="cliente@example.com",
            password="StrongPassword123",
            full_name="Cliente User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@example.com",
            phone="+351910000000",
        )

        self.url = reverse(
            "appointments:patient_record",
            kwargs={"pk": self.customer.pk},
        )

    def test_anonymous_is_redirected_home(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("home"))
        self.assertEqual(PatientRecord.objects.count(), 0)

    def test_logged_in_customer_cannot_open_it(self):
        self.client.force_login(self.normal_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("home"))
        self.assertEqual(PatientRecord.objects.count(), 0)


class PatientRecordFlowTests(TestCase):
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

        self.client.force_login(self.admin_user)
        self.url = reverse(
            "appointments:patient_record",
            kwargs={"pk": self.customer.pk},
        )

    def payload(self, **overrides):
        data = {
            "main_complaint": "Dor ao caminhar há duas semanas.",
            "allergies": "",
            "medical_history": "",
            "current_medication": "",
            "previous_surgeries": "",
            "footwear_notes": "",
            "notes": "",
        }
        data.update(overrides)
        return data

    def test_opening_creates_an_empty_record(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PatientRecord.objects.count(), 1)
        self.assertFalse(PatientRecord.objects.get().is_filled)

    def test_page_is_not_indexable(self):
        response = self.client.get(self.url)

        self.assertContains(response, "noindex,nofollow")

    def test_saving_stores_the_record_and_who_changed_it(self):
        response = self.client.post(self.url, data=self.payload())

        self.assertRedirects(response, self.url)

        record = PatientRecord.objects.get()

        self.assertEqual(record.customer, self.customer)
        self.assertIn("Dor ao caminhar", record.main_complaint)
        self.assertEqual(record.updated_by, self.admin_user)
        self.assertTrue(record.is_filled)

    def test_second_save_updates_instead_of_duplicating(self):
        self.client.post(self.url, data=self.payload())
        self.client.post(self.url, data=self.payload(main_complaint="Revisto."))

        self.assertEqual(PatientRecord.objects.count(), 1)
        self.assertEqual(PatientRecord.objects.get().main_complaint, "Revisto.")

    def test_allergies_require_detail(self):
        response = self.client.post(
            self.url,
            data=self.payload(has_allergies="on", allergies=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("allergies", response.context["form"].errors)
        self.assertFalse(PatientRecord.objects.get().has_allergies)

    def test_allergies_are_accepted_with_detail(self):
        self.client.post(
            self.url,
            data=self.payload(has_allergies="on", allergies="Iodo."),
        )

        record = PatientRecord.objects.get()

        self.assertTrue(record.has_allergies)
        self.assertEqual(record.allergies, "Iodo.")

    def test_risk_alerts_list_the_relevant_flags(self):
        self.client.post(
            self.url,
            data=self.payload(has_diabetes="on", has_circulatory_issues="on"),
        )

        record = PatientRecord.objects.get()

        self.assertEqual(record.risk_alerts, ["Diabetes", "Circulação"])

    def test_smoking_alone_is_not_a_risk_alert(self):
        # É relevante para o histórico, mas não muda o atendimento imediato.
        self.client.post(self.url, data=self.payload(is_smoker="on"))

        self.assertEqual(PatientRecord.objects.get().risk_alerts, [])

    def test_customer_list_shows_the_alerts(self):
        self.client.post(self.url, data=self.payload(has_diabetes="on"))

        response = self.client.get(reverse("appointments:customer_list"))

        self.assertContains(response, "Diabetes")
        self.assertContains(response, "Ficha de anamnese de Maria Silva")

    def test_record_is_removed_with_the_customer(self):
        self.client.post(self.url, data=self.payload())

        self.customer.delete()

        self.assertEqual(PatientRecord.objects.count(), 0)

    def test_model_validation_rejects_allergies_without_detail(self):
        record = PatientRecord(
            customer=self.customer,
            has_allergies=True,
            allergies="   ",
        )

        with self.assertRaises(ValidationError):
            record.full_clean()
