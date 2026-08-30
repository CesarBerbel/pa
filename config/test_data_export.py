"""A exportação de dados.

Uma exportação errada não parte nada: produz um ficheiro que abre, com as
colunas certas e os valores trocados, e só se descobre do outro lado — depois
de o sistema antigo já ter sido desligado. Por isso o que aqui se guarda não é
"gerou um zip", é o conteúdo:

* que as **ligações** entre ficheiros sobrevivem, que é a única coisa que não
  se consegue reconstruir à mão depois;
* que os **acentos** chegam inteiros;
* que os **dados clínicos** não saem por engano nem por pedido de quem não
  pode levá-los.
"""

import csv
import io
import zipfile
from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import (
    Appointment,
    ClinicalNote,
    Customer,
    PatientRecord,
    ReturnVisit,
)
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from config import data_export
from finance.models import Expense, Payment


class ExportBase(TestCase):
    def setUp(self):
        self.utilizador = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123",
            full_name="Admin User",
        )

        self.hoje = timezone.localdate()

        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday, start_time=time(9, 0), end_time=time(18, 0)
            )

        self.servico = create_test_service(duration_minutes=60)
        self.servico.price = Decimal("30.00")
        self.servico.save(update_fields=["price"])

        # Com acentos e cedilha de propósito: é o nome que parte a codificação.
        self.cliente = Customer.objects.create(
            full_name="Conceição Gonçalves",
            email="conceicao@exemplo.pt",
            phone="+351910000000",
        )

        self.marcacao = Appointment.objects.create(
            customer=self.cliente,
            service=self.servico,
            date=self.hoje,
            start_time=time(10, 0),
            created_by=self.utilizador,
            status=Appointment.STATUS_COMPLETED,
        )

        self.client.force_login(self.utilizador)

    def ficheiros(self, clinico=False):
        conteudo = data_export.construir(clinico=clinico)

        with zipfile.ZipFile(io.BytesIO(conteudo)) as zip_ficheiro:
            return {nome: zip_ficheiro.read(nome) for nome in zip_ficheiro.namelist()}

    def linhas(self, bruto):
        texto = bruto.decode("utf-8-sig")

        return list(csv.DictReader(io.StringIO(texto)))


class WhatComesOutTests(ExportBase):
    def test_every_expected_file_is_in_the_zip(self):
        ficheiros = self.ficheiros()

        self.assertIn("clientes.csv", ficheiros)
        self.assertIn("marcacoes.csv", ficheiros)
        self.assertIn("servicos.csv", ficheiros)
        self.assertIn("LEIA-ME.txt", ficheiros)

    def test_the_customer_is_there_with_the_accents_intact(self):
        # O defeito clássico de um CSV: "Conceição" chega como "ConceiÃ§Ã£o".
        linhas = self.linhas(self.ficheiros()["clientes.csv"])

        self.assertEqual(linhas[0]["nome"], "Conceição Gonçalves")

    def test_the_file_starts_with_a_bom(self):
        # Sem o BOM o Excel lê o ficheiro na codificação da máquina e estraga
        # os acentos, mesmo estando o ficheiro certo.
        self.assertTrue(self.ficheiros()["clientes.csv"].startswith(b"\xef\xbb\xbf"))


class TheLinksBetweenFilesTests(ExportBase):
    """As chaves são a única coisa que não se reconstrói à mão do outro lado."""

    def test_an_appointment_points_at_its_customer_and_service(self):
        marcacao = self.linhas(self.ficheiros()["marcacoes.csv"])[0]

        self.assertEqual(marcacao["cliente_id"], str(self.cliente.id))
        self.assertEqual(marcacao["servico_id"], str(self.servico.id))

    def test_a_payment_points_at_its_appointment(self):
        Payment.objects.create(
            appointment=self.marcacao,
            amount=Decimal("27.50"),
            paid_on=self.hoje,
        )

        pagamento = self.linhas(self.ficheiros()["pagamentos.csv"])[0]

        self.assertEqual(pagamento["marcacao_id"], str(self.marcacao.id))

    def test_a_return_keeps_both_ends_of_the_history(self):
        # O retorno liga a marcação que o originou à que foi marcada. Perder
        # uma das pontas é perder o historico, que é a razão de o retorno
        # existir.
        seguinte = Appointment.objects.create(
            customer=self.cliente,
            service=self.servico,
            date=self.hoje + timedelta(days=30),
            start_time=time(11, 0),
            created_by=self.utilizador,
        )

        ReturnVisit.objects.create(
            customer=self.cliente,
            origin=self.marcacao,
            service=self.servico,
            target_date=self.hoje + timedelta(days=30),
            appointment=seguinte,
            status=ReturnVisit.STATUS_SCHEDULED,
        )

        retorno = self.linhas(self.ficheiros()["retornos.csv"])[0]

        self.assertEqual(retorno["marcacao_de_origem_id"], str(self.marcacao.id))
        self.assertEqual(retorno["marcacao_agendada_id"], str(seguinte.id))


class HowTheValuesAreWrittenTests(ExportBase):
    def test_the_status_comes_as_a_code_and_as_a_name(self):
        # O código para quem importa, o nome para quem confere.
        marcacao = self.linhas(self.ficheiros()["marcacoes.csv"])[0]

        self.assertEqual(marcacao["estado_codigo"], Appointment.STATUS_COMPLETED)
        self.assertEqual(marcacao["estado"], self.marcacao.get_status_display())

    def test_dates_are_iso_and_not_the_portuguese_format(self):
        # 30/08 e 08/30 são o mesmo texto e dias diferentes.
        marcacao = self.linhas(self.ficheiros()["marcacoes.csv"])[0]

        self.assertEqual(marcacao["data"], self.hoje.isoformat())
        self.assertEqual(marcacao["hora"], "10:00")

    def test_money_uses_a_decimal_point(self):
        # O ecrã mostra 27,50; um importador espera 27.50.
        Payment.objects.create(
            appointment=self.marcacao,
            amount=Decimal("27.50"),
            paid_on=self.hoje,
        )

        pagamento = self.linhas(self.ficheiros()["pagamentos.csv"])[0]

        self.assertEqual(pagamento["valor"], "27.50")

    def test_an_expense_carries_its_category_code(self):
        Expense.objects.create(
            description="Compressas",
            amount=Decimal("10.00"),
            spent_on=self.hoje,
            category=Expense.CATEGORY_SUPPLIES,
        )

        despesa = self.linhas(self.ficheiros()["despesas.csv"])[0]

        self.assertEqual(despesa["categoria_codigo"], Expense.CATEGORY_SUPPLIES)

    def test_an_empty_table_still_exports_its_header(self):
        # Um ficheiro sem cabeçalho não se importa: o outro lado não sabe o
        # que são as colunas quando um dia houver linhas.
        linhas = self.ficheiros()["despesas.csv"].decode("utf-8-sig").splitlines()

        self.assertEqual(len(linhas), 1)
        self.assertIn("categoria_codigo", linhas[0])


class ClinicalDataStaysBehindTests(ExportBase):
    def setUp(self):
        super().setUp()

        PatientRecord.objects.create(
            customer=self.cliente,
            main_complaint="Dor no calcanhar",
            has_diabetes=True,
        )

        ClinicalNote.objects.create(
            appointment=self.marcacao,
            procedures="Desbridamento",
            created_by=self.utilizador,
        )

    def test_the_default_export_leaves_the_clinical_files_out(self):
        ficheiros = self.ficheiros(clinico=False)

        self.assertNotIn("fichas_clinicas.csv", ficheiros)
        self.assertNotIn("notas_clinicas.csv", ficheiros)

    def test_asking_for_them_brings_them(self):
        ficheiros = self.ficheiros(clinico=True)

        ficha = self.linhas(ficheiros["fichas_clinicas.csv"])[0]

        self.assertEqual(ficha["queixa_principal"], "Dor no calcanhar")
        self.assertEqual(ficha["diabetes"], "sim")

    def test_the_complaint_never_appears_in_the_ordinary_files(self):
        # A garantia que interessa não é "o ficheiro não veio", é "o dado não
        # saiu" — nem de arrasto numa coluna de outro ficheiro.
        junto = b"".join(self.ficheiros(clinico=False).values())

        self.assertNotIn("Dor no calcanhar", junto.decode("utf-8-sig"))
        self.assertNotIn("Desbridamento", junto.decode("utf-8-sig"))

    def test_the_readme_says_whether_clinical_data_is_inside(self):
        sem = self.ficheiros(clinico=False)["LEIA-ME.txt"].decode("utf-8")
        com = self.ficheiros(clinico=True)["LEIA-ME.txt"].decode("utf-8")

        self.assertIn("nao foram incluidos", sem)
        self.assertIn("dados de saude", com)


class WhoCanExportTests(ExportBase):
    def endereco(self):
        return reverse("data_export")

    def test_a_stranger_cannot_reach_the_page(self):
        self.client.logout()

        self.assertEqual(self.client.get(self.endereco()).status_code, 302)

    def test_a_customer_cannot_reach_the_page(self):
        self.client.logout()

        cliente = get_user_model().objects.create_user(
            email="cliente@exemplo.pt",
            password="StrongPassword123",
            full_name="Cliente",
        )
        self.client.force_login(cliente)

        self.assertEqual(self.client.get(self.endereco()).status_code, 302)

    def test_a_stranger_cannot_download_by_posting(self):
        # A página está protegida; o que interessa é que o POST também esteja,
        # que é o que devolve mesmo os dados.
        self.client.logout()

        resposta = self.client.post(self.endereco())

        self.assertEqual(resposta.status_code, 302)
        self.assertNotEqual(resposta.get("Content-Type"), "application/zip")

    def test_someone_without_clinical_access_is_not_offered_the_choice(self):
        self.client.logout()

        rececao = get_user_model().objects.create_user(
            email="rececao@exemplo.pt",
            password="StrongPassword123",
            full_name="Receção",
            is_internal_staff=True,
        )
        self.client.force_login(rececao)

        resposta = self.client.get(self.endereco())

        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'name="incluir_clinicos"')

    def test_and_cannot_get_them_by_writing_the_field_by_hand(self):
        # A caixa não existe no ecrã dessa pessoa; nada impede que o campo seja
        # escrito à mão no pedido. É a verificação no servidor que impede.
        PatientRecord.objects.create(
            customer=self.cliente,
            main_complaint="Dor no calcanhar",
        )

        self.client.logout()

        rececao = get_user_model().objects.create_user(
            email="rececao@exemplo.pt",
            password="StrongPassword123",
            full_name="Receção",
            is_internal_staff=True,
        )
        self.client.force_login(rececao)

        resposta = self.client.post(self.endereco(), data={"incluir_clinicos": "on"})

        with zipfile.ZipFile(io.BytesIO(resposta.content)) as zip_ficheiro:
            nomes = zip_ficheiro.namelist()

        self.assertNotIn("fichas_clinicas.csv", nomes)


class TheDownloadTests(ExportBase):
    def test_the_post_returns_a_zip_named_after_today(self):
        resposta = self.client.post(reverse("data_export"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/zip")
        self.assertIn(
            f'filename="exportacao-{self.hoje.isoformat()}.zip"',
            resposta["Content-Disposition"],
        )

    def test_the_download_is_never_cached(self):
        resposta = self.client.post(reverse("data_export"))

        self.assertEqual(resposta["Cache-Control"], "no-store")

    def test_the_zip_actually_opens(self):
        resposta = self.client.post(reverse("data_export"))

        with zipfile.ZipFile(io.BytesIO(resposta.content)) as zip_ficheiro:
            self.assertIsNone(zip_ficheiro.testzip())

    def test_the_export_is_written_to_the_log(self):
        # É o único rasto de que os dados saíram: não há registo por marcação
        # nem por ficha que apanhe uma exportação.
        with self.assertLogs("config", level="WARNING") as registo:
            self.client.post(reverse("data_export"))

        self.assertIn("admin@example.com", "\n".join(registo.output))

    def test_the_page_says_how_many_of_each_there_are(self):
        resposta = self.client.get(reverse("data_export"))

        self.assertContains(resposta, "Clientes")
        self.assertContains(resposta, "Marcações")


class TheReadmeTests(ExportBase):
    def test_it_explains_how_the_files_join_up(self):
        # O LEIA-ME é o que faz a diferença entre um zip de CSVs e uma
        # exportação que alguém consegue importar sem perguntar nada.
        texto = self.ficheiros()["LEIA-ME.txt"].decode("utf-8")

        self.assertIn("marcacoes.cliente_id", texto)
        self.assertIn("clientes.id", texto)

    def test_it_lists_only_the_files_that_came(self):
        texto = self.ficheiros(clinico=False)["LEIA-ME.txt"].decode("utf-8")

        self.assertIn("clientes.csv", texto)
        self.assertNotIn("fichas_clinicas.csv", texto)
