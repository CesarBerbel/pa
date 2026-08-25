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

        # A ficha deixou de nascer ao abrir a página: quem a quer, cria-a.
        PatientRecord.objects.create(customer=self.customer)

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
            # O select de risco é sempre submetido pelo browser.
            "diabetic_foot_risk": "na",
        }
        data.update(overrides)
        return data

    def test_opening_does_not_create_a_record(self):
        # Criava, e o resultado era que toda a gente tinha ficha: bastava um
        # clique no ícone para ficar um registo clínico vazio, indistinguível
        # de uma ficha por preencher. Quem a quer, cria-a no botão.
        PatientRecord.objects.all().delete()

        outra = Customer.objects.create(
            full_name="Ana Ferreira",
            email="ana@example.com",
            phone="+351911111111",
        )

        resposta = self.client.get(
            reverse("appointments:patient_record", kwargs={"pk": outra.pk})
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(PatientRecord.objects.count(), 0)
        self.assertContains(resposta, "Criar ficha de anamnese")

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


class PodiatryAnamnesisTests(TestCase):
    """A ficha segue a estrutura de uma anamnese podológica.

    Além dos antecedentes, guarda o exame do pé, a avaliação vascular e
    neurológica e o plano — que é o que a legislação espera de um registo
    clínico claro e adequado.
    """

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

        PatientRecord.objects.create(customer=self.customer)

        self.client.force_login(self.admin_user)
        self.url = reverse(
            "appointments:patient_record",
            kwargs={"pk": self.customer.pk},
        )

    def payload(self, **overrides):
        data = {
            "birth_date": "",
            "profession": "",
            "main_complaint": "",
            "allergies": "",
            "medical_history": "",
            "current_medication": "",
            "previous_surgeries": "",
            "skin_assessment": "",
            "nail_assessment": "",
            "foot_deformities": "",
            "gait_assessment": "",
            "footwear_notes": "",
            "vascular_assessment": "",
            "neurological_assessment": "",
            "diabetic_foot_risk": "na",
            "treatment_plan": "",
            "notes": "",
        }
        data.update(overrides)
        return data

    def test_every_model_field_is_reachable_in_a_section(self):
        # Um campo fora das secções ficaria invisível no ecrã sem ninguém dar
        # por isso. A rede de segurança do formulário tem de estar vazia.
        response = self.client.get(self.url)
        form = response.context["form"]

        self.assertEqual([campo.name for campo in form.missing_fields()], [])

    def test_sections_cover_the_expected_areas(self):
        response = self.client.get(self.url)
        titulos = [seccao["title"] for seccao in response.context["form"].sections()]

        self.assertEqual(
            titulos,
            [
                "Identificação",
                "Motivo da consulta",
                "Antecedentes",
                "Exame podológico",
                "Vascular e neurológico",
                "Plano e observações",
            ],
        )

    def test_examination_fields_are_stored(self):
        self.client.post(
            self.url,
            data=self.payload(
                skin_assessment="Hiperqueratose no antepé.",
                nail_assessment="Onicomicose no hálux direito.",
                foot_deformities="Hallux valgus bilateral.",
                vascular_assessment="Pulsos presentes e simétricos.",
                neurological_assessment="Monofilamento sem alterações.",
                treatment_plan="Desbaste e reavaliação em 4 semanas.",
            ),
        )

        record = PatientRecord.objects.get()

        self.assertIn("Hiperqueratose", record.skin_assessment)
        self.assertIn("Onicomicose", record.nail_assessment)
        self.assertIn("Hallux valgus", record.foot_deformities)
        self.assertIn("Pulsos", record.vascular_assessment)
        self.assertIn("Monofilamento", record.neurological_assessment)
        self.assertIn("Desbaste", record.treatment_plan)

    def test_neuropathy_is_a_risk_alert(self):
        # Sem sensibilidade protetora, a cliente pode não sentir dor durante o
        # tratamento: é dos avisos que mais muda a conduta.
        self.client.post(self.url, data=self.payload(has_neuropathy="on"))

        self.assertIn("Neuropatia", PatientRecord.objects.get().risk_alerts)

    def test_high_diabetic_risk_is_a_risk_alert(self):
        self.client.post(self.url, data=self.payload(diabetic_foot_risk="high"))

        self.assertIn(
            "Pé diabético: risco alto",
            PatientRecord.objects.get().risk_alerts,
        )

    def test_low_diabetic_risk_is_not_an_alert(self):
        self.client.post(self.url, data=self.payload(diabetic_foot_risk="low"))

        self.assertEqual(PatientRecord.objects.get().risk_alerts, [])

    def test_age_is_calculated_from_the_birth_date(self):
        self.client.post(self.url, data=self.payload(birth_date="1980-01-01"))

        record = PatientRecord.objects.get()

        self.assertIsNotNone(record.age)
        self.assertGreater(record.age, 40)

    def test_age_is_none_without_a_birth_date(self):
        self.client.post(self.url, data=self.payload())

        self.assertIsNone(PatientRecord.objects.get().age)

    def test_examination_text_alone_counts_as_filled(self):
        self.client.post(self.url, data=self.payload(nail_assessment="Sem alterações."))

        self.assertTrue(PatientRecord.objects.get().is_filled)

    def test_page_renders_the_touch_friendly_layout(self):
        response = self.client.get(self.url)

        self.assertContains(response, "anamnesis-accordion")
        self.assertContains(response, "anamnesis-flags")
        self.assertContains(response, "anamnesis-actions")
