"""Telefones do mundo inteiro, e o seletor de indicativo que os torna possíveis.

O que estava escrito aceitava Portugal e o Brasil e recusava o resto com uma
mensagem que dizia exatamente isso. Quem chega de férias, quem vive fora e
volta, ou quem acompanha um familiar não tem de ter um número português para
poder marcar.
"""

from datetime import time, timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments import phone_countries
from appointments.customer_services import normalize_phone, validate_phone
from appointments.forms import AppointmentForm, CustomerForm, PublicAppointmentForm
from appointments.models import Customer
from appointments.phone_form_field import PhoneField
from appointments.tests.factories import create_test_service, ensure_test_business_hour


class FormularioDeTeste(forms.Form):
    phone = PhoneField(label="Telefone")


class WorldPhoneNormalizationTests(TestCase):
    """O número guardado é sempre E.164, venha ele como vier."""

    def test_a_number_from_anywhere_is_accepted(self):
        casos = {
            "+447700900123": "+447700900123",  # Reino Unido
            "+33612345678": "+33612345678",  # França
            "+12125550123": "+12125550123",  # Estados Unidos
            "+254712345678": "+254712345678",  # Quénia
            "+819012345678": "+819012345678",  # Japão
        }

        for escrito, esperado in casos.items():
            with self.subTest(numero=escrito):
                self.assertEqual(validate_phone(escrito), esperado)

    def test_the_two_countries_that_already_worked_still_do(self):
        self.assertEqual(validate_phone("+351912345678"), "+351912345678")
        self.assertEqual(validate_phone("+5511999998888"), "+5511999998888")

    def test_a_number_without_a_country_code_is_read_as_portuguese(self):
        # É onde a clínica está, e é assim que os números guardados antes disto
        # foram escritos.
        self.assertEqual(normalize_phone("912345678"), "+351912345678")

    def test_the_international_prefix_is_understood(self):
        # `00` é como se marca o internacional a partir de quase toda a Europa.
        self.assertEqual(normalize_phone("00447700900123"), "+447700900123")

    def test_spaces_and_punctuation_do_not_count(self):
        self.assertEqual(validate_phone("+44 7700 900 123"), "+447700900123")
        self.assertEqual(validate_phone("(11) 99999-9999"), "+5511999999999")

    def test_what_is_not_a_phone_number_is_refused(self):
        for escrito in ["", "12", "abc", "+1234567890123456"]:
            with self.subTest(numero=escrito):
                with self.assertRaises(ValidationError):
                    validate_phone(escrito)

    def test_the_message_no_longer_names_two_countries(self):
        with self.assertRaises(ValidationError) as erro:
            validate_phone("12")

        self.assertNotIn("Brasil", erro.exception.messages[0])
        self.assertNotIn("Portugal", erro.exception.messages[0])


class CountryListTests(TestCase):
    def test_the_usual_ones_come_first(self):
        # São os primeiros a aparecer antes de alguém escrever seja o que for.
        primeiros = [iso for iso, _nome, _indicativo in phone_countries.ordenados()[:3]]

        self.assertEqual(primeiros, ["PT", "BR", "ES"])

    def test_the_rest_is_alphabetical(self):
        nomes = [nome for _iso, nome, _ind in phone_countries.ordenados()[3:]]

        self.assertEqual(nomes, sorted(nomes))

    def test_a_number_is_split_by_the_longest_code_that_fits(self):
        # `+1268` é Antígua e `+1` são os Estados Unidos: o mais curto engolia
        # o outro.
        self.assertEqual(phone_countries.separar("+12685550123"), ("AG", "5550123"))
        self.assertEqual(phone_countries.separar("+12125550123"), ("US", "2125550123"))

    def test_a_number_without_a_plus_is_not_split(self):
        self.assertEqual(phone_countries.separar("912345678"), ("", "912345678"))


class PhoneFieldTests(TestCase):
    """As duas caixas: o país escolhido e o número escrito."""

    def campo(self, **dados):
        return FormularioDeTeste(data=dados)

    def test_the_country_and_the_number_become_one(self):
        formulario = self.campo(phone_0="GB", phone_1="7700 900123")

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data["phone"], "+447700900123")

    def test_the_trunk_zero_does_not_travel(self):
        # Dentro do Reino Unido marca-se 07700...; no estrangeiro, o zero cai.
        formulario = self.campo(phone_0="GB", phone_1="07700900123")

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data["phone"], "+447700900123")

    def test_writing_the_code_again_does_not_double_it(self):
        formulario = self.campo(phone_0="PT", phone_1="351912345678")

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data["phone"], "+351912345678")

    def test_a_full_international_number_wins_over_the_selector(self):
        # Quem colou o número inteiro escreveu o país que quer; recusá-lo seria
        # recusar o número certo.
        formulario = self.campo(phone_0="PT", phone_1="+447700900123")

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data["phone"], "+447700900123")

    def test_an_empty_number_says_which_box_is_missing(self):
        formulario = self.campo(phone_0="PT", phone_1="")

        self.assertFalse(formulario.is_valid())
        self.assertIn("Indique o número de telefone.", formulario.errors["phone"])

    def test_a_whole_number_in_a_single_field_still_works(self):
        # Um pedido escrito antes de o campo ter duas peças não pode passar a
        # ser recusado por isso.
        formulario = self.campo(phone="+447700900123")

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data["phone"], "+447700900123")

    def test_the_stored_number_goes_back_into_the_two_boxes(self):
        # É o que faz um número já guardado poder ser editado.
        html = str(FormularioDeTeste(initial={"phone": "+447700900123"})["phone"])

        self.assertIn('value="GB" selected', html)
        self.assertIn('value="7700900123"', html)

    def test_the_selector_carries_every_country(self):
        html = str(FormularioDeTeste()["phone"])

        for procurado in ["Portugal (+351)", "Quénia (+254)", "Japão (+81)"]:
            with self.subTest(pais=procurado):
                self.assertIn(procurado, html)


class PhoneOnEveryFormTests(TestCase):
    """Os quatro sítios onde se escreve um telefone."""

    def setUp(self):
        self.service = create_test_service(duration_minutes=60)

        self.date = timezone.localdate() + timedelta(days=14)
        while self.date.weekday() != 0:
            self.date += timedelta(days=1)

        ensure_test_business_hour(
            weekday=self.date.weekday(),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

    def test_the_customer_form_takes_a_foreign_number(self):
        formulario = CustomerForm(
            data={
                "full_name": "Jane Doe",
                "email": "jane@example.com",
                "phone_0": "GB",
                "phone_1": "7700900123",
            }
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data["phone"], "+447700900123")

    def test_the_public_booking_takes_a_foreign_number(self):
        formulario = PublicAppointmentForm(
            data={
                "service": self.service.pk,
                "date": self.date.strftime("%Y-%m-%d"),
                "start_time": "10:00",
                "customer_name": "Jane Doe",
                "customer_phone_0": "GB",
                "customer_phone_1": "7700900123",
                "privacy_policy_accepted": "on",
            }
        )

        formulario.is_valid()

        self.assertEqual(formulario.cleaned_data["customer_phone"], "+447700900123")

    def test_a_new_customer_inside_an_appointment_takes_one_too(self):
        formulario = AppointmentForm(
            data={
                "customer_mode": AppointmentForm.CUSTOMER_MODE_NEW,
                "new_customer_name": "Jane Doe",
                "new_customer_phone_0": "GB",
                "new_customer_phone_1": "7700900123",
                "service": self.service.pk,
                "date": self.date.strftime("%Y-%m-%d"),
                "start_time": "10:00",
                "status": "scheduled",
                "notes": "",
            }
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(
            Customer.objects.get(full_name="Jane Doe").phone, "+447700900123"
        )

    def test_the_signup_form_takes_one(self):
        from accounts.forms import CustomerSignupForm

        formulario = CustomerSignupForm(
            data={
                "full_name": "Jane Doe",
                "email": "jane@example.com",
                "phone_0": "GB",
                "phone_1": "7700900123",
                "password1": "StrongPassword123",
                "password2": "StrongPassword123",
            }
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data["phone"], "+447700900123")

    def test_the_search_script_is_on_the_public_booking_page(self):
        # Sem ele o <select> continua a funcionar; com ele ganha a procura.
        resposta = self.client.get(
            reverse("appointments:public_appointment_create"),
            {
                "service": self.service.pk,
                "date": self.date.strftime("%Y-%m-%d"),
                "start_time": "10:00",
            },
        )

        self.assertEqual(resposta.status_code, 200)

        html = resposta.content.decode()

        self.assertIn("phone_country_search.js", html)
        self.assertIn("data-phone-field", html)
