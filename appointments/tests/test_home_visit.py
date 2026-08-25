"""Atendimento em casa da cliente: onde se marca, e o que a mensagem diz."""

import json
from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments import address_lookup
from appointments.forms import AppointmentForm
from appointments.message_preview import build_preview
from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour

MORADA = {
    "home_street": "Rua das Flores",
    "home_number": "12",
    "home_floor": "3.º Dto",
    "home_postal_code": "3000-100",
    "home_locality": "Coimbra",
    "home_municipality": "Coimbra",
    "home_district": "Coimbra",
    "home_country": "Portugal",
}


class HomeVisitBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@exemplo.pt",
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

        self.client.force_login(self.user)

    def dados(self, **campos):
        valores = {
            "customer_mode": AppointmentForm.CUSTOMER_MODE_EXISTING,
            "customer": self.customer.pk,
            "service": self.service.pk,
            "date": self.date.strftime("%Y-%m-%d"),
            "start_time": "10:00",
            "status": Appointment.STATUS_SCHEDULED,
            "notes": "",
            "home_directions": "",
        }
        valores.update({campo: "" for campo in MORADA})
        valores.update(campos)

        return valores

    def marcacao(self, **campos):
        valores = {
            "customer": self.customer,
            "service": self.service,
            "date": self.date,
            "start_time": time(10, 0),
            "created_by": self.user,
        }
        valores.update(campos)

        return Appointment.objects.create(**valores)

    def em_casa(self, **campos):
        valores = {"is_home_visit": True}
        valores.update(MORADA)
        valores.update(campos)

        return self.marcacao(**valores)


class HomeVisitFieldsTests(HomeVisitBase):
    """A marcação sabe onde é o atendimento."""

    def test_an_appointment_is_at_the_clinic_by_default(self):
        marcacao = self.marcacao()

        self.assertFalse(marcacao.is_home_visit)
        self.assertEqual(marcacao.home_street, "")
        self.assertEqual(marcacao.home_address, "")

    def test_a_home_visit_keeps_every_part_of_the_address(self):
        marcacao = self.em_casa(home_directions="Campainha B.")
        marcacao.refresh_from_db()

        for campo, valor in MORADA.items():
            with self.subTest(campo=campo):
                self.assertEqual(getattr(marcacao, campo), valor)

        self.assertIn("Campainha B", marcacao.home_directions)

    def test_the_address_reads_as_one_line(self):
        # É assim que a mensagem e os ecrãs a mostram: ninguém quer ler oito
        # campos, e montá-la num sítio só evita que cada um a escreva à sua
        # maneira.
        marcacao = self.em_casa()

        self.assertEqual(
            marcacao.home_address,
            "Rua das Flores 12, 3.º Dto, 3000-100 Coimbra",
        )

    def test_the_municipality_is_not_repeated_when_it_is_the_locality(self):
        # Em Portugal é o caso mais comum, e "Coimbra, Coimbra" só faz duvidar
        # de quem escreveu.
        self.assertNotIn("Coimbra, Coimbra", self.em_casa().home_address)

    def test_a_different_municipality_shows_up(self):
        marcacao = self.em_casa(home_locality="Eiras", home_municipality="Coimbra")

        self.assertTrue(marcacao.home_address.endswith("Eiras, Coimbra"))

    def test_an_address_with_holes_leaves_no_stray_commas(self):
        marcacao = self.em_casa(
            home_number="",
            home_floor="",
            home_postal_code="",
            home_municipality="",
        )

        self.assertEqual(marcacao.home_address, "Rua das Flores, Coimbra")

    def test_a_home_visit_without_a_street_is_refused(self):
        # Uma deslocação para lado nenhum, e uma mensagem a dizer à cliente que
        # vamos ter com ela a um sítio que ninguém escreveu.
        marcacao = Appointment(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(11, 0),
            created_by=self.user,
            is_home_visit=True,
        )

        with self.assertRaises(ValidationError) as erro:
            marcacao.full_clean()

        self.assertIn("home_street", erro.exception.error_dict)

    def test_the_address_may_be_empty_at_the_clinic(self):
        Appointment(
            customer=self.customer,
            service=self.service,
            date=self.date,
            start_time=time(11, 0),
            created_by=self.user,
        ).full_clean()


class HomeVisitFormTests(HomeVisitBase):
    """O formulário da área interna, que é onde a escolha se faz."""

    def formulario(self):
        return self.client.get(
            reverse("appointments:appointment_create")
        ).content.decode()

    def test_the_form_offers_every_field_of_the_address(self):
        html = self.formulario()

        self.assertIn('name="is_home_visit"', html)
        self.assertIn('name="home_directions"', html)

        for campo in MORADA:
            with self.subTest(campo=campo):
                self.assertIn(f'name="{campo}"', html)

    def test_marking_a_home_visit_requires_the_street(self):
        formulario = AppointmentForm(data=self.dados(is_home_visit="on"))

        self.assertFalse(formulario.is_valid())
        self.assertIn("home_street", formulario.errors)

    def test_the_rest_of_the_address_is_optional(self):
        # Uma morada de aldeia pode não ter número nem código postal conhecido,
        # e exigi-los impedia de marcar um atendimento que existe.
        formulario = AppointmentForm(
            data=self.dados(is_home_visit="on", home_street="Quinta da Serra")
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)

    def test_unticking_the_box_clears_what_was_typed(self):
        # Senão a morada ficava guardada numa marcação que passou a ser na
        # clínica, e aparecia no ecrã do dia a mandar a profissional sair.
        formulario = AppointmentForm(
            data=self.dados(home_directions="Campainha B", **MORADA)
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)

        for campo in list(MORADA) + ["home_directions"]:
            with self.subTest(campo=campo):
                self.assertEqual(formulario.cleaned_data[campo], "")

    def test_the_address_survives_the_round_trip(self):
        self.client.post(
            reverse("appointments:appointment_create"),
            data=self.dados(
                is_home_visit="on", home_directions="Campainha B", **MORADA
            ),
        )

        marcacao = Appointment.objects.get(customer=self.customer)

        self.assertTrue(marcacao.is_home_visit)
        self.assertEqual(marcacao.home_postal_code, "3000-100")
        self.assertEqual(marcacao.home_floor, "3.º Dto")


class HomeVisitOnTheScreenTests(HomeVisitBase):
    def test_the_detail_screen_shows_where_to_go(self):
        marcacao = self.em_casa(home_directions="Campainha B")

        html = self.client.get(
            reverse("appointments:appointment_detail", args=[marcacao.pk])
        ).content.decode()

        self.assertIn("Atendimento em domicílio", html)
        self.assertIn("Rua das Flores 12", html)
        self.assertIn("Campainha B", html)

    def test_a_clinic_appointment_says_nothing_about_addresses(self):
        marcacao = self.marcacao()

        html = self.client.get(
            reverse("appointments:appointment_detail", args=[marcacao.pk])
        ).content.decode()

        self.assertNotIn("Atendimento em domicílio", html)


class HomeVisitConfirmationMessageTests(HomeVisitBase):
    """A confirmação deixa de mandar a cliente à clínica.

    Dizer "esperamos por si na Av. Sá da Bandeira" a quem vai ser atendida em
    casa é o contrário do que vai acontecer: ou sai de casa para nada, ou fica
    a duvidar do que combinou.
    """

    def texto(self, marcacao):
        previa = build_preview(marcacao, action="confirm")

        return "\n".join(
            f"{email['subject']} {email['body']}" for email in previa.emails
        )

    def test_the_clinic_confirmation_still_names_the_clinic(self):
        # O caso comum não pode mudar por causa desta funcionalidade.
        texto = self.texto(self.marcacao())

        self.assertIn("Sá da Bandeira", texto)
        self.assertNotIn("somos nós a ir ter consigo", texto)

    def test_the_home_confirmation_says_we_are_going_there(self):
        texto = self.texto(self.em_casa())

        self.assertIn("somos nós a ir ter consigo", texto)
        self.assertIn("Rua das Flores 12, 3.º Dto, 3000-100 Coimbra", texto)

    def test_the_home_confirmation_does_not_name_the_clinic(self):
        self.assertNotIn("Sá da Bandeira", self.texto(self.em_casa()))

    def test_the_directions_stay_out_of_the_customer_message(self):
        # São para a profissional chegar lá. A cliente já sabe onde mora.
        marcacao = self.em_casa(home_directions="Campainha B, o cão ladra")

        self.assertNotIn("Campainha B", self.texto(marcacao))

    def test_the_whatsapp_confirmation_says_it_too(self):
        # O texto livre é o que o número da clínica envia. O modelo aprovado
        # pela Meta não sabe escolher entre duas frases e continua a dizer a
        # morada da clínica — está dito na migração 0027.
        from notifications.models import WhatsAppEventSetting
        from notifications.whatsapp_common import build_context, render_text

        regra = WhatsAppEventSetting.objects.get(
            event_type="appointment_confirmed",
            audience=WhatsAppEventSetting.AUDIENCE_CUSTOMER,
        )

        texto = render_text(regra.body_template, build_context(self.em_casa()))

        self.assertIn("somos nós a ir ter consigo", texto)
        self.assertIn("Rua das Flores 12", texto)
        self.assertNotIn("Sá da Bandeira", texto)


class RespostaFalsa:
    """O que `urlopen` devolve, com o mínimo para servir de gestor de contexto."""

    def __init__(self, conteudo):
        self.conteudo = json.dumps(conteudo).encode("utf-8")

    def read(self):
        return self.conteudo

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        return False


SUGESTOES = {
    "suggestions": [
        {
            "placePrediction": {
                "placeId": "ChIJ-morada",
                "structuredFormat": {
                    "mainText": {"text": "Rua das Flores 12"},
                    "secondaryText": {"text": "Coimbra, Portugal"},
                },
            }
        },
        {"queryPrediction": {"text": {"text": "flores"}}},
    ]
}

DETALHES = {
    "formattedAddress": "R. das Flores 12, 3000-100 Coimbra, Portugal",
    "addressComponents": [
        {"longText": "12", "shortText": "12", "types": ["street_number"]},
        {"longText": "Rua das Flores", "types": ["route"]},
        {"longText": "3000-100", "types": ["postal_code"]},
        {"longText": "Coimbra", "types": ["locality", "political"]},
        {"longText": "Coimbra", "types": ["administrative_area_level_2"]},
        {"longText": "Coimbra", "types": ["administrative_area_level_1"]},
        {"longText": "Portugal", "types": ["country"]},
    ],
}


@override_settings(GOOGLE_PLACES_API_KEY="chave-de-mentira")
class AddressLookupTests(TestCase):
    """As moradas que a Google sugere, sem falar com a Google."""

    def test_it_does_nothing_without_a_key(self):
        # Sem chave configurada não se faz pedido nenhum: o formulário
        # preenche-se à mão, como antes de haver sugestões.
        with patch("appointments.address_lookup.urlopen") as urlopen:
            with override_settings(GOOGLE_PLACES_API_KEY=""):
                self.assertEqual(address_lookup.suggest("Rua das Flores"), [])
                self.assertEqual(address_lookup.details("ChIJ-morada"), {})

            urlopen.assert_not_called()

    def test_two_letters_are_not_worth_a_paid_call(self):
        with patch("appointments.address_lookup.urlopen") as urlopen:
            self.assertEqual(address_lookup.suggest("Ru"), [])

            urlopen.assert_not_called()

    def test_it_returns_the_addresses_it_was_given(self):
        with patch(
            "appointments.address_lookup.urlopen",
            return_value=RespostaFalsa(SUGESTOES),
        ):
            sugestoes = address_lookup.suggest("Rua das Flores")

        # A previsão de pesquisa não é uma morada e fica de fora.
        self.assertEqual(len(sugestoes), 1)
        self.assertEqual(sugestoes[0]["place_id"], "ChIJ-morada")
        self.assertEqual(sugestoes[0]["main"], "Rua das Flores 12")
        self.assertEqual(sugestoes[0]["secondary"], "Coimbra, Portugal")

    def test_the_search_is_kept_to_the_region_and_to_addresses(self):
        with patch(
            "appointments.address_lookup.urlopen",
            return_value=RespostaFalsa(SUGESTOES),
        ) as urlopen:
            address_lookup.suggest("Rua das Flores", session_token="sessao-1")

        pedido = urlopen.call_args[0][0]
        corpo = json.loads(pedido.data.decode("utf-8"))

        self.assertEqual(corpo["includedRegionCodes"], ["PT"])
        self.assertIn("street_address", corpo["includedPrimaryTypes"])
        self.assertEqual(corpo["sessionToken"], "sessao-1")
        self.assertEqual(pedido.get_header("X-goog-api-key"), "chave-de-mentira")

    def test_the_details_come_split_into_the_form_fields(self):
        with patch(
            "appointments.address_lookup.urlopen",
            return_value=RespostaFalsa(DETALHES),
        ):
            morada = address_lookup.details("ChIJ-morada")

        self.assertEqual(morada["home_street"], "Rua das Flores")
        self.assertEqual(morada["home_number"], "12")
        self.assertEqual(morada["home_postal_code"], "3000-100")
        self.assertEqual(morada["home_locality"], "Coimbra")
        self.assertEqual(morada["home_country"], "Portugal")
        self.assertIn("3000-100", morada["formatted"])

    def test_a_missing_component_comes_back_empty(self):
        # A Google não sabe o andar de quase nenhuma morada.
        with patch(
            "appointments.address_lookup.urlopen",
            return_value=RespostaFalsa(DETALHES),
        ):
            morada = address_lookup.details("ChIJ-morada")

        self.assertEqual(morada["home_floor"], "")

    def test_google_falling_over_is_not_an_error_here(self):
        # A marcação tem de continuar a poder ser feita à mão.
        with patch(
            "appointments.address_lookup.urlopen",
            side_effect=OSError("rede em baixo"),
        ):
            self.assertEqual(address_lookup.suggest("Rua das Flores"), [])
            self.assertEqual(address_lookup.details("ChIJ-morada"), {})


@override_settings(GOOGLE_PLACES_API_KEY="chave-de-mentira")
class AddressEndpointTests(HomeVisitBase):
    """O endereço que o formulário consulta, e quem lhe pode chegar."""

    def url(self):
        return reverse("appointments:home_visit_address")

    def test_it_is_closed_to_who_is_not_from_the_internal_area(self):
        # A chave é do servidor; um endereço aberto ao mundo seria a mesma
        # coisa que publicá-la.
        self.client.logout()

        resposta = self.client.get(self.url(), {"q": "Rua das Flores"})

        self.assertIn(resposta.status_code, (302, 403))

    def test_it_answers_with_the_suggestions(self):
        with patch(
            "appointments.address_lookup.urlopen",
            return_value=RespostaFalsa(SUGESTOES),
        ):
            resposta = self.client.get(self.url(), {"q": "Rua das Flores"})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["suggestions"][0]["place_id"], "ChIJ-morada")

    def test_asking_for_one_place_answers_with_the_fields(self):
        with patch(
            "appointments.address_lookup.urlopen",
            return_value=RespostaFalsa(DETALHES),
        ):
            resposta = self.client.get(self.url(), {"place_id": "ChIJ-morada"})

        self.assertEqual(resposta.json()["home_street"], "Rua das Flores")

    def test_the_form_points_at_it(self):
        html = self.client.get(
            reverse("appointments:appointment_create")
        ).content.decode()

        self.assertIn(self.url(), html)
        self.assertIn("data-address-search", html)
