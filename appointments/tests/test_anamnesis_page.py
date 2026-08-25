"""A anamnese com a lista de clientes ao lado.

Era uma página que só se abria pela lista de clientes, uma de cada vez, com
uma volta pelo meio a cada pessoa. Passou a ter a lista à esquerda: escolhe-se
quem se quer e a ficha abre ao lado.
"""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from appointments.models import Customer, PatientRecord

LISTA = re.compile(r'<ul class="anamnesis-people-list".*?</ul>', re.S)


class AnamnesisPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.ana = Customer.objects.create(
            full_name="Ana Ferreira",
            email="ana@exemplo.pt",
            phone="+351911111111",
        )
        self.maria = Customer.objects.create(
            full_name="Maria Silva",
            email="maria@exemplo.pt",
            phone="+351922222222",
        )

        self.client.force_login(self.user)

    def indice(self):
        return self.client.get(reverse("appointments:patient_record_index"))

    def ficha(self, cliente):
        return self.client.get(
            reverse("appointments:patient_record", args=[cliente.pk])
        )

    def lista(self, resposta):
        return LISTA.search(resposta.content.decode()).group(0)

    def test_the_menu_page_lists_everyone(self):
        lista = self.lista(self.indice())

        self.assertIn("Ana Ferreira", lista)
        self.assertIn("Maria Silva", lista)

    def test_the_menu_page_opens_nobody(self):
        # Abrir a ficha da primeira da lista seria mostrar dados de saúde de
        # alguém que ninguém pediu para ver.
        resposta = self.indice()

        self.assertIsNone(resposta.context["view"].__dict__.get("object"))
        self.assertIn("Escolha uma cliente", resposta.content.decode())
        self.assertEqual(PatientRecord.objects.count(), 0)

    def test_every_name_links_to_its_own_record(self):
        lista = self.lista(self.indice())

        for cliente in [self.ana, self.maria]:
            with self.subTest(cliente=cliente.full_name):
                self.assertIn(
                    reverse("appointments:patient_record", args=[cliente.pk]), lista
                )

    def test_choosing_a_name_opens_the_record_beside_the_list(self):
        resposta = self.ficha(self.maria)
        html = resposta.content.decode()

        # A ficha, e a lista ainda lá.
        self.assertEqual(resposta.context["customer"], self.maria)
        self.assertIn("Ficha de anamnese", html)
        self.assertIn("Ana Ferreira", self.lista(resposta))

    def test_the_open_one_is_marked_in_the_list(self):
        lista = self.lista(self.ficha(self.maria))

        aberta = re.search(
            r'class="anamnesis-person ([^"]*)"[^>]*>\s*<span[^>]*>Maria', lista
        )

        self.assertIsNotNone(aberta)
        self.assertIn("is-open", aberta.group(1))

    def test_the_others_are_not_marked(self):
        lista = self.lista(self.ficha(self.maria))
        ana = re.search(
            r'class="anamnesis-person ([^"]*)"[^>]*>\s*<span[^>]*>Ana', lista
        )

        self.assertNotIn("is-open", ana.group(1))

    def test_the_list_can_be_put_away(self):
        # É o botão que a recolhe para a lateral e a traz de volta.
        html = self.indice().content.decode()

        self.assertIn("data-anamnesis-toggle", html)
        self.assertIn("data-anamnesis-people", html)

    def test_the_list_has_a_way_to_find_a_name(self):
        # Duzentos nomes sem procura não se usam.
        self.assertIn("data-anamnesis-search", self.indice().content.decode())

    def test_a_name_ordered_alphabetically(self):
        nomes = re.findall(r'data-name="([^"]+)"', self.lista(self.indice()))

        self.assertEqual(nomes, sorted(nomes))

    def test_who_has_no_record_is_greyed_out(self):
        # Cinzento, mas clicável: o que abre do outro lado é o botão de criar.
        PatientRecord.objects.create(customer=self.maria)

        lista = self.lista(self.indice())

        ana = re.search(
            r'class="anamnesis-person ([^"]*)"[^>]*data-name="Ana[^"]*"', lista
        )
        maria = re.search(
            r'class="anamnesis-person ([^"]*)"[^>]*data-name="Maria[^"]*"', lista
        )

        self.assertIn("has-no-record", ana.group(1))
        self.assertNotIn("has-no-record", maria.group(1))

    def test_who_has_no_record_still_links_to_her_page(self):
        lista = self.lista(self.indice())

        self.assertIn(reverse("appointments:patient_record", args=[self.ana.pk]), lista)

    def test_who_has_alerts_shows_it_before_the_record_is_opened(self):
        # É o que muda o atendimento, e vê-se sem abrir a ficha.
        PatientRecord.objects.create(customer=self.ana, has_diabetes=True)

        lista = self.lista(self.indice())

        self.assertIn("anamnesis-person-alert", lista)

    def test_the_page_is_not_indexable(self):
        # São dados de saúde.
        self.assertIn("noindex,nofollow", self.indice().content.decode())


class AnamnesisPageAccessTests(TestCase):
    """Quem lá pode chegar. A ficha tem dados de saúde."""

    def setUp(self):
        self.rececao = get_user_model().objects.create_user(
            email="rececao@example.com",
            password="StrongPassword123",
            full_name="Receção",
            is_internal_staff=True,
            can_access_clinical_data=False,
        )

    def test_reception_cannot_open_the_list(self):
        self.client.force_login(self.rececao)

        resposta = self.client.get(reverse("appointments:patient_record_index"))

        self.assertNotEqual(resposta.status_code, 200)

    def test_a_visitor_cannot_open_the_list(self):
        resposta = self.client.get(reverse("appointments:patient_record_index"))

        self.assertNotEqual(resposta.status_code, 200)


class CreatingTheRecordTests(TestCase):
    """A ficha deixou de nascer só por alguém abrir a página.

    Nascia, e o resultado era que toda a gente tinha ficha: bastava um clique
    no ícone para ficar um registo clínico vazio, indistinguível de uma ficha
    por preencher. Agora quem a quer, cria-a.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Ana Ferreira",
            email="ana@exemplo.pt",
            phone="+351911111111",
        )

        self.client.force_login(self.user)

        self.pagina = reverse("appointments:patient_record", args=[self.customer.pk])
        self.criar = reverse(
            "appointments:patient_record_create", args=[self.customer.pk]
        )

    def test_opening_the_page_creates_nothing(self):
        self.client.get(self.pagina)

        self.assertEqual(PatientRecord.objects.count(), 0)

    def test_without_a_record_the_page_offers_the_button(self):
        html = self.client.get(self.pagina).content.decode()

        self.assertIn("Criar ficha de anamnese", html)
        self.assertIn(self.criar, html)
        self.assertNotIn("Guardar ficha", html)

    def test_the_button_creates_it_and_opens_it(self):
        resposta = self.client.post(self.criar)

        self.assertRedirects(resposta, self.pagina)
        self.assertTrue(PatientRecord.objects.filter(customer=self.customer).exists())

    def test_with_a_record_the_form_is_what_shows_up(self):
        self.client.post(self.criar)

        html = self.client.get(self.pagina).content.decode()

        self.assertIn("Guardar ficha", html)
        self.assertNotIn("Criar ficha de anamnese", html)

    def test_creating_twice_does_not_duplicate(self):
        self.client.post(self.criar)
        self.client.post(self.criar)

        self.assertEqual(PatientRecord.objects.count(), 1)

    def test_a_link_cannot_create_it(self):
        # É POST de propósito: uma ficha não deve nascer de uma ligação que um
        # browser adiantou sozinho.
        self.client.get(self.criar)

        self.assertEqual(PatientRecord.objects.count(), 0)

    def test_reception_cannot_create_one(self):
        rececao = get_user_model().objects.create_user(
            email="rececao@example.com",
            password="StrongPassword123",
            full_name="Receção",
            is_internal_staff=True,
            can_access_clinical_data=False,
        )

        self.client.force_login(rececao)
        self.client.post(self.criar)

        self.assertEqual(PatientRecord.objects.count(), 0)

    def test_the_visits_show_up_even_without_a_record(self):
        # As consultas são das marcações e não da ficha: quem ainda não tem
        # ficha pode já ter sido atendida.
        from datetime import time, timedelta

        from django.utils import timezone

        from appointments.models import Appointment, ClinicalNote
        from appointments.tests.factories import create_test_service

        marcacao = Appointment.objects.create(
            customer=self.customer,
            service=create_test_service(duration_minutes=60),
            date=timezone.localdate() - timedelta(days=7),
            start_time=time(10, 0),
            created_by=self.user,
        )
        ClinicalNote.objects.create(
            appointment=marcacao,
            procedures="Desbaste de calo.",
            created_by=self.user,
        )

        html = self.client.get(self.pagina).content.decode()

        self.assertIn("Consultas anteriores", html)
        self.assertIn("Desbaste de calo", html)


class TheIconInTheCustomerListTests(TestCase):
    """O ícone da anamnese na lista de clientes."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Ana Ferreira",
            email="ana@exemplo.pt",
            phone="+351911111111",
        )

        self.client.force_login(self.user)

    def cartao(self):
        """Os botões do cartão da cliente, e não o CSS com o mesmo nome."""

        html = self.client.get(reverse("appointments:customer_list")).content.decode()
        inicio = html.index('<div class="customer-card-actions">')

        return html[inicio : html.index("Editar cliente", inicio)]

    def test_without_a_record_the_icon_looks_disabled_and_asks_first(self):
        cartao = self.cartao()

        self.assertIn("is-recordless", cartao)
        self.assertIn("confirm(", cartao)
        self.assertIn(
            reverse("appointments:patient_record_create", args=[self.customer.pk]),
            cartao,
        )

    def test_with_a_record_the_icon_is_a_plain_link(self):
        PatientRecord.objects.create(customer=self.customer)

        cartao = self.cartao()

        self.assertNotIn("is-recordless", cartao)
        self.assertNotIn("confirm(", cartao)
        self.assertIn(
            reverse("appointments:patient_record", args=[self.customer.pk]), cartao
        )
