"""O financeiro: o que entra, o que sai, e o que fica por receber.

O que estes testes protegem são três decisões que decidem todos os números:

* a receita conta-se pela data do **dinheiro** e não pela do atendimento;
* o valor é o **cobrado** e não o de tabela;
* uma marcação concluída **sem pagamento é uma dívida**, não um zero.

Errar qualquer uma delas não parte nada — dá números plausíveis e errados, que
é o pior defeito que um ecrã de contas pode ter.
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, Customer
from appointments.tests.factories import create_test_service, ensure_test_business_hour
from finance import reports
from finance.models import CashCount, Expense, FinanceSetting, Payment


class FinanceBase(TestCase):
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
        self.service.price = Decimal("30.00")
        self.service.save(update_fields=["price"])

        self.hoje = timezone.localdate()

        for weekday in range(7):
            ensure_test_business_hour(
                weekday=weekday, start_time=time(9, 0), end_time=time(18, 0)
            )

        self.client.force_login(self.user)

    def marcacao(self, **campos):
        valores = {
            "customer": self.customer,
            "service": self.service,
            "date": self.hoje,
            "start_time": time(10, 0),
            "created_by": self.user,
            "status": Appointment.STATUS_COMPLETED,
        }
        valores.update(campos)

        return Appointment.objects.create(**valores)

    def pagamento(self, marcacao=None, valor="30.00", quando=None, **extra):
        return Payment.objects.create(
            appointment=marcacao or self.marcacao(),
            amount=Decimal(valor),
            paid_on=quando or self.hoje,
            **extra,
        )

    def despesa(self, valor="10.00", quando=None, **extra):
        campos = {
            "description": "Compressas",
            "amount": Decimal(valor),
            "spent_on": quando or self.hoje,
        }
        campos.update(extra)

        return Expense.objects.create(**campos)

    def mes_de(self, dia):
        return reports.limites_do_mes(dia.year, dia.month)


class WhenTheMoneyCountsTests(FinanceBase):
    """A receita é do mês em que o dinheiro chegou."""

    def test_a_payment_counts_on_the_month_it_was_received(self):
        # Atendimento num mês, pagamento no seguinte: é receita do seguinte.
        atendimento = date(2026, 1, 20)
        recebimento = date(2026, 2, 3)

        self.pagamento(
            self.marcacao(date=atendimento, start_time=time(11, 0)),
            quando=recebimento,
        )

        self.assertEqual(reports.receita(*self.mes_de(atendimento)), Decimal("0.00"))
        self.assertEqual(reports.receita(*self.mes_de(recebimento)), Decimal("30.00"))

    def test_the_last_day_of_the_month_is_inside_the_month(self):
        # Um intervalo aberto no fim deixava de fora o dia 31, que costuma ser
        # dos que mais rende.
        fim_do_mes = date(2026, 1, 31)

        self.pagamento(
            self.marcacao(date=fim_do_mes, start_time=time(12, 0)),
            quando=fim_do_mes,
        )

        self.assertEqual(reports.receita(*self.mes_de(fim_do_mes)), Decimal("30.00"))

    def test_a_month_with_nothing_is_zero_and_not_none(self):
        # `Sum` sem linhas devolve `None`, e `None` não se soma nem se
        # subtrai: o resultado do mês rebentava.
        vazio = self.mes_de(date(2020, 5, 10))

        self.assertEqual(reports.receita(*vazio), Decimal("0.00"))
        self.assertEqual(reports.despesa(*vazio), Decimal("0.00"))
        self.assertEqual(reports.resultado(*vazio), Decimal("0.00"))


class WhatWasChargedTests(FinanceBase):
    """O valor é o cobrado, não o de tabela."""

    def test_a_discount_is_what_shows_up_in_the_revenue(self):
        self.pagamento(valor="25.00")

        self.assertEqual(reports.receita(*self.mes_de(self.hoje)), Decimal("25.00"))

    def test_the_form_offers_the_list_price_as_a_starting_point(self):
        marcacao = self.marcacao()

        resposta = self.client.get(
            reverse("finance:payment_create", args=[marcacao.pk])
        )

        self.assertEqual(resposta.context["form"].initial["amount"], self.service.price)

    def test_but_the_written_value_wins(self):
        marcacao = self.marcacao()

        self.client.post(
            reverse("finance:payment_create", args=[marcacao.pk]),
            data={
                "amount": "22.50",
                "method": Payment.METHOD_MBWAY,
                "paid_on": self.hoje.isoformat(),
                "notes": "",
            },
        )

        self.assertEqual(marcacao.payment.amount, Decimal("22.50"))

    def test_a_payment_in_the_future_is_refused(self):
        # Não é um pagamento: é uma expectativa, e entrava na receita de um mês
        # que ainda não aconteceu.
        marcacao = self.marcacao()

        resposta = self.client.post(
            reverse("finance:payment_create", args=[marcacao.pk]),
            data={
                "amount": "30.00",
                "method": Payment.METHOD_CASH,
                "paid_on": (self.hoje + timedelta(days=1)).isoformat(),
                "notes": "",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Payment.objects.exists())


class WhoStillOwesTests(FinanceBase):
    """A lista de dívidas mantém-se sozinha."""

    def test_a_completed_appointment_without_payment_is_a_debt(self):
        marcacao = self.marcacao()

        self.assertIn(marcacao, reports.por_pagar())

    def test_registering_the_payment_takes_it_off_the_list(self):
        marcacao = self.marcacao()
        self.pagamento(marcacao)

        self.assertNotIn(marcacao, reports.por_pagar())

    def test_a_future_appointment_is_not_a_debt(self):
        # Ainda não aconteceu.
        futura = self.marcacao(
            date=self.hoje + timedelta(days=3),
            start_time=time(15, 0),
            status=Appointment.STATUS_CONFIRMED,
        )

        self.assertNotIn(futura, reports.por_pagar())

    def test_a_cancelled_one_never_was(self):
        cancelada = self.marcacao(
            start_time=time(16, 0), status=Appointment.STATUS_CANCELLED
        )

        self.assertNotIn(cancelada, reports.por_pagar())

    def test_the_estimate_uses_the_list_price(self):
        # É a única estimativa que há: o valor cobrado só existe depois de
        # haver pagamento, e estas são as que não têm.
        self.marcacao()

        self.assertEqual(reports.total_por_pagar(), Decimal("30.00"))

    def test_deleting_a_payment_puts_it_back(self):
        # Não é um efeito colateral escondido: é a razão de o botão existir.
        marcacao = self.marcacao()
        pagamento = self.pagamento(marcacao)

        self.client.post(reverse("finance:payment_delete", args=[pagamento.pk]))

        self.assertIn(marcacao, reports.por_pagar())


class TheMonthResultTests(FinanceBase):
    def test_what_is_left_is_what_came_in_minus_what_went_out(self):
        self.pagamento(valor="100.00")
        self.despesa(valor="30.00")

        self.assertEqual(reports.resultado(*self.mes_de(self.hoje)), Decimal("70.00"))

    def test_a_bad_month_shows_as_negative(self):
        """Um resultado travado em zero esconderia o mês que interessa olhar."""

        self.despesa(valor="80.00")

        self.assertEqual(reports.resultado(*self.mes_de(self.hoje)), Decimal("-80.00"))

    def test_revenue_by_service_adds_up(self):
        self.pagamento(valor="30.00")
        self.pagamento(self.marcacao(start_time=time(14, 0)), valor="20.00")

        linhas = list(reports.receita_por_servico(*self.mes_de(self.hoje)))

        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["total"], Decimal("50.00"))
        self.assertEqual(linhas[0]["quantas"], 2)

    def test_expenses_by_category_carry_a_readable_name(self):
        self.despesa(category=Expense.CATEGORY_RENT, valor="400.00")

        linhas = reports.despesa_por_categoria(*self.mes_de(self.hoje))

        self.assertEqual(linhas[0]["nome"], "Renda e despesas do espaço")


class OnlyOnePaymentPerAppointmentTests(FinanceBase):
    def test_the_second_attempt_opens_the_first_for_editing(self):
        # Sem isto, o segundo registo rebentava com um erro de base de dados
        # em vez de dizer o que se passa.
        marcacao = self.marcacao()
        pagamento = self.pagamento(marcacao)

        resposta = self.client.get(
            reverse("finance:payment_create", args=[marcacao.pk])
        )

        self.assertRedirects(
            resposta, reverse("finance:payment_update", args=[pagamento.pk])
        )


class TheScreensTests(FinanceBase):
    def paginas(self):
        return [
            reverse("finance:dashboard"),
            reverse("finance:payment_list"),
            reverse("finance:unpaid_list"),
            reverse("finance:expense_list"),
            reverse("finance:expense_create"),
        ]

    def test_they_all_open(self):
        for url in self.paginas():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_a_broken_month_in_the_address_does_not_break_the_screen(self):
        # Um ecrã de contas não deve dar erro por causa de um parâmetro
        # escrito à mão ou vindo de um link antigo.
        resposta = self.client.get(reverse("finance:dashboard") + "?ano=abc&mes=99")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["mes"], self.hoje.month)

    def test_december_rolls_into_january_of_the_next_year(self):
        resposta = self.client.get(reverse("finance:dashboard") + "?ano=2026&mes=12")

        self.assertEqual(resposta.context["mes_seguinte"], (2027, 1))
        self.assertEqual(resposta.context["mes_anterior"], (2026, 11))

    def test_a_customer_cannot_see_the_money(self):
        cliente = get_user_model().objects.create_user(
            email="cliente@exemplo.pt",
            password="StrongPassword123",
            full_name="Cliente",
        )

        self.client.force_login(cliente)

        for url in self.paginas():
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_an_anonymous_visitor_cannot_either(self):
        self.client.logout()

        for url in self.paginas():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)


class TheAppointmentScreenTests(FinanceBase):
    def detalhe(self, marcacao):
        return self.client.get(
            reverse("appointments:appointment_detail", args=[marcacao.pk])
        )

    def test_a_completed_appointment_offers_to_register_the_payment(self):
        marcacao = self.marcacao()

        self.assertContains(self.detalhe(marcacao), "Registar pagamento")

    def test_once_registered_it_shows_what_was_charged(self):
        marcacao = self.marcacao()
        self.pagamento(marcacao, valor="27.50", method=Payment.METHOD_MBWAY)

        resposta = self.detalhe(marcacao)

        # `27,50` e não `27.50`: o Django localiza os números, e em português
        # o separador decimal é a vírgula. Procurar o ponto é procurar o que
        # a página nunca escreve.
        self.assertContains(resposta, "27,50")
        self.assertContains(resposta, "MB Way")

    def test_an_appointment_that_has_not_happened_asks_for_nothing(self):
        futura = self.marcacao(
            date=self.hoje + timedelta(days=2),
            start_time=time(9, 30),
            status=Appointment.STATUS_CONFIRMED,
        )

        self.assertNotContains(self.detalhe(futura), "Registar pagamento")


class TheUnpaidListOnlyHasCompletedOnesTests(FinanceBase):
    """Só o que já aconteceu é que pode estar por receber."""

    def test_a_confirmed_appointment_in_the_past_is_not_a_debt(self):
        # Está por concluir, que é outra fila. Misturadas, o total por receber
        # contava dinheiro de atendimentos que ninguém confirmou terem
        # acontecido.
        atrasada = self.marcacao(
            date=self.hoje - timedelta(days=1),
            start_time=time(11, 0),
            status=Appointment.STATUS_CONFIRMED,
        )

        self.assertNotIn(atrasada, reports.por_pagar())
        self.assertEqual(reports.total_por_pagar(), Decimal("0.00"))

    def test_every_status_other_than_completed_stays_out(self):
        for estado in (
            Appointment.STATUS_SCHEDULED,
            Appointment.STATUS_CONFIRMED,
            Appointment.STATUS_CANCELLED,
        ):
            with self.subTest(estado=estado):
                Appointment.objects.all().delete()

                self.marcacao(
                    date=self.hoje - timedelta(days=2),
                    start_time=time(12, 0),
                    status=estado,
                )

                self.assertEqual(reports.por_pagar().count(), 0)


class TheWeeklyChartTests(FinanceBase):
    """A receita do mês repartida por semanas civis, de segunda a domingo.

    Semanas civis e não blocos de sete dias a contar do dia 1: uma clínica
    trabalha a semanas, e "de 8 a 14" não quer dizer nada a quem pensa em "a
    semana passada".
    """

    def semanas(self, ano, mes):
        return reports.receita_por_semana(*reports.limites_do_mes(ano, mes))

    def test_the_weeks_cover_the_month_and_nothing_more(self):
        inicio, fim = reports.limites_do_mes(2026, 8)
        semanas = self.semanas(2026, 8)

        self.assertEqual(semanas[0]["inicio"], inicio)
        self.assertEqual(semanas[-1]["fim"], fim)

    def test_they_do_not_overlap_and_leave_no_gaps(self):
        semanas = self.semanas(2026, 8)

        for anterior, seguinte in zip(semanas[:-1], semanas[1:], strict=True):
            self.assertEqual(seguinte["inicio"] - anterior["fim"], timedelta(days=1))

    def test_the_first_and_last_come_clipped(self):
        """Agosto de 2026 começa a um sábado.

        A primeira semana tem dois dias, e é o que ela é: ir buscar receita de
        julho para a encher seria contar dinheiro de outro mês.
        """

        semanas = self.semanas(2026, 8)

        self.assertEqual(semanas[0]["rotulo"], "1–2")
        self.assertEqual(semanas[0]["inicio"].weekday(), 5)

    def test_a_payment_lands_on_its_week(self):
        quando = date(2026, 8, 12)

        self.pagamento(
            self.marcacao(date=quando, start_time=time(11, 0)),
            valor="40.00",
            quando=quando,
        )

        semanas = self.semanas(2026, 8)
        com_dinheiro = [s for s in semanas if s["total"]]

        self.assertEqual(len(com_dinheiro), 1)
        self.assertEqual(com_dinheiro[0]["total"], Decimal("40.00"))
        self.assertLessEqual(com_dinheiro[0]["inicio"], quando)
        self.assertGreaterEqual(com_dinheiro[0]["fim"], quando)

    def test_the_weeks_add_up_to_the_month(self):
        # Se não somassem, uma das duas contas estava errada e não havia como
        # saber qual.
        inicio, fim = reports.limites_do_mes(self.hoje.year, self.hoje.month)

        self.pagamento(valor="30.00")
        self.pagamento(self.marcacao(start_time=time(14, 0)), valor="25.00")

        total = sum(s["total"] for s in reports.receita_por_semana(inicio, fim))

        self.assertEqual(total, reports.receita(inicio, fim))

    def test_the_dashboard_draws_them(self):
        resposta = self.client.get(reverse("finance:dashboard"))

        self.assertContains(resposta, "finance-weeks")
        self.assertContains(resposta, "Semana a semana")


class WhatIsStillToComeTests(FinanceBase):
    """Previsto é o que **falta** entrar, não o que o mês inteiro valeu."""

    def mes_atual(self):
        return self.mes_de(self.hoje)

    def test_a_confirmed_appointment_still_to_come_counts(self):
        self.marcacao(
            date=self.hoje + timedelta(days=2),
            start_time=time(9, 30),
            status=Appointment.STATUS_CONFIRMED,
        )

        self.assertEqual(reports.previsto(*self.mes_atual()), Decimal("30.00"))

    def test_one_waiting_for_confirmation_does_not(self):
        # Contar dinheiro de uma consulta que ninguém confirmou é contar com o
        # que pode não acontecer.
        self.marcacao(
            date=self.hoje + timedelta(days=2),
            start_time=time(9, 30),
            status=Appointment.STATUS_SCHEDULED,
        )

        self.assertEqual(reports.previsto(*self.mes_atual()), Decimal("0.00"))

    def test_one_that_already_happened_does_not(self):
        """Já não é previsão nenhuma.

        Ou foi concluída — e aí o que interessa é a receita ou a dívida — ou
        está por concluir, e essa aparece no dashboard operacional.
        """

        self.marcacao(
            date=self.hoje - timedelta(days=1),
            start_time=time(11, 0),
            status=Appointment.STATUS_CONFIRMED,
        )

        self.assertEqual(reports.previsto(*self.mes_atual()), Decimal("0.00"))

    def test_a_cancelled_one_does_not(self):
        self.marcacao(
            date=self.hoje + timedelta(days=2),
            start_time=time(9, 30),
            status=Appointment.STATUS_CANCELLED,
        )

        self.assertEqual(reports.previsto(*self.mes_atual()), Decimal("0.00"))

    def test_a_month_that_already_passed_expects_nothing(self):
        self.assertEqual(
            reports.previsto(*self.mes_de(date(2020, 5, 10))), Decimal("0.00")
        )

    def test_the_card_carries_no_explanation(self):
        resposta = self.client.get(reverse("finance:dashboard"))

        self.assertContains(resposta, "Previsto")
        self.assertNotContains(resposta, "finance-tile-note")


class WhatIsDoneAndUnpaidOnTheDashboardTests(FinanceBase):
    """Quanto está concluído e sem pagamento, como número e não só como lista."""

    def test_the_dashboard_shows_the_amount(self):
        self.marcacao()

        resposta = self.client.get(reverse("finance:dashboard"))

        self.assertEqual(resposta.context["por_pagar_total"], Decimal("30.00"))
        self.assertContains(resposta, "Por receber")
        self.assertContains(resposta, "finance-tile-owed")

    def test_registering_the_payment_brings_it_down(self):
        marcacao = self.marcacao()
        self.pagamento(marcacao)

        resposta = self.client.get(reverse("finance:dashboard"))

        self.assertEqual(resposta.context["por_pagar_total"], Decimal("0.00"))

    def test_the_tile_leads_to_the_list(self):
        self.marcacao()

        self.assertContains(
            self.client.get(reverse("finance:dashboard")),
            reverse("finance:unpaid_list"),
        )


class TheCashCountTests(FinanceBase):
    """O acerto de caixa: contar o dinheiro e deixar a diferença escrita."""

    def contagem(self, esperado="30.00", contado="30.00", quando=None, **extra):
        return CashCount.objects.create(
            counted_on=quando or self.hoje,
            expected_amount=Decimal(esperado),
            counted_amount=Decimal(contado),
            **extra,
        )

    def test_the_difference_is_what_is_missing_or_left_over(self):
        self.assertEqual(
            self.contagem(esperado="30.00", contado="28.50").difference,
            Decimal("-1.50"),
        )

    def test_money_left_over_is_a_positive_difference(self):
        self.assertEqual(
            self.contagem(esperado="30.00", contado="32.00").difference,
            Decimal("2.00"),
        )

    def test_the_expected_only_counts_cash(self):
        """O que entrou por MB Way não passa pela caixa.

        Somá-lo faria a diferença acusar sempre uma falta do tamanho dos
        pagamentos eletrónicos.
        """

        self.pagamento(valor="30.00", method=Payment.METHOD_CASH)
        self.pagamento(
            self.marcacao(start_time=time(14, 0)),
            valor="50.00",
            method=Payment.METHOD_MBWAY,
        )

        self.assertEqual(CashCount.expected_for(self.hoje), Decimal("30.00"))

    def test_a_day_with_no_cash_expects_nothing(self):
        self.assertEqual(CashCount.expected_for(self.hoje), Decimal("0.00"))

    def test_counting_does_not_touch_the_revenue(self):
        """É a decisão mais importante deste modelo.

        Se uma contagem alterasse a receita, os números do mês passavam a
        depender de quem contou a caixa e de quando — e um relatório que muda
        por causa de uma contagem deixa de poder ser conferido contra os
        pagamentos que o formam.
        """

        self.pagamento(valor="30.00", method=Payment.METHOD_CASH)

        antes = reports.receita(*self.mes_de(self.hoje))

        self.contagem(esperado="30.00", contado="10.00")

        self.assertEqual(reports.receita(*self.mes_de(self.hoje)), antes)

    def test_the_expected_is_frozen_at_the_moment_of_counting(self):
        """Um pagamento acrescentado depois não muda a diferença de então.

        Recalculada hoje, a diferença de há um mês mudava sozinha — e o
        registo deixava de ser a fotografia que era suposto ser.
        """

        contagem = self.contagem(esperado="30.00", contado="30.00")

        self.pagamento(valor="50.00", method=Payment.METHOD_CASH)

        contagem.refresh_from_db()

        self.assertEqual(contagem.expected_amount, Decimal("30.00"))
        self.assertEqual(contagem.difference, Decimal("0.00"))

    def test_only_one_count_per_day(self):
        # Contar duas vezes o mesmo dia é ter duas verdades.
        from django.db import IntegrityError, transaction

        self.contagem()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.contagem()

    def test_a_day_that_has_not_happened_is_refused(self):
        contagem = CashCount(
            counted_on=self.hoje + timedelta(days=1),
            expected_amount=Decimal("0.00"),
            counted_amount=Decimal("0.00"),
        )

        with self.assertRaises(ValidationError):
            contagem.full_clean()


class TheCashCountIsAdminOnlyTests(FinanceBase):
    """Só no admin do Django, e o admin é outra porta que a área interna."""

    def test_it_has_no_screen_in_the_internal_area(self):
        from django.urls import NoReverseMatch

        for nome in ("cashcount_list", "cash_count", "cashcount"):
            with self.subTest(nome=nome), self.assertRaises(NoReverseMatch):
                reverse(f"finance:{nome}")

    def test_the_finance_dashboard_does_not_mention_it(self):
        resposta = self.client.get(reverse("finance:dashboard"))

        self.assertNotContains(resposta, "cashcount")
        self.assertNotContains(resposta, "Acerto de caixa")

    def test_it_is_registered_in_the_django_admin(self):
        from django.contrib import admin as django_admin

        self.assertIn(CashCount, django_admin.site._registry)

    def test_internal_access_alone_does_not_open_the_admin(self):
        """`is_staff` é coisa diferente do acesso à área interna.

        Quem gere a agenda não chega ao admin a menos que alguém lho dê, e é
        isso que faz de "só pelo admin" uma restrição a sério.
        """

        interna = get_user_model().objects.create_user(
            email="agenda@exemplo.pt",
            password="StrongPassword123",
            full_name="Quem gere a agenda",
            is_internal_staff=True,
        )

        self.assertTrue(interna.has_internal_access)
        self.assertFalse(interna.is_staff)

        self.client.force_login(interna)

        resposta = self.client.get("/admin/finance/cashcount/")

        self.assertNotEqual(resposta.status_code, 200)

    def test_a_staff_user_gets_the_expected_already_filled_in(self):
        # Somar os pagamentos em dinheiro do dia de cabeça é exatamente o passo
        # onde o erro entra.
        self.pagamento(valor="30.00", method=Payment.METHOD_CASH)

        resposta = self.client.get("/admin/finance/cashcount/add/")
        inicial = resposta.context["adminform"].form.initial

        self.assertEqual(resposta.status_code, 200)

        # Pelo valor e não pela sua escrita: um `<input type="number">`
        # normaliza `30.00` para `30`, e procurar a string no HTML era testar
        # a formatação do Django em vez do que o campo traz.
        self.assertEqual(inicial["expected_amount"], Decimal("30.00"))
        self.assertEqual(inicial["counted_on"], self.hoje)


class TheTwoAccountsTests(FinanceBase):
    """O dinheiro reparte-se em duas contas: a de investir e a disponível."""

    def com_percentagem(self, valor):
        definicao = FinanceSetting.load()
        definicao.reinvestment_percent = Decimal(valor)
        definicao.save()

        return definicao

    def test_the_slice_goes_to_the_investment_account(self):
        self.com_percentagem("70.00")
        self.pagamento(valor="100.00")

        self.assertEqual(
            reports.investimento(*self.mes_de(self.hoje)), Decimal("70.00")
        )

    def test_the_rest_stays_available(self):
        self.com_percentagem("70.00")
        self.pagamento(valor="100.00")

        self.assertEqual(reports.disponivel(*self.mes_de(self.hoje)), Decimal("30.00"))

    def test_the_two_add_up_to_the_revenue(self):
        # Se não somassem, um euro tinha desaparecido ou aparecido do nada.
        self.com_percentagem("70.00")
        self.pagamento(valor="100.00")
        self.pagamento(self.marcacao(start_time=time(14, 0)), valor="35.50")

        mes = self.mes_de(self.hoje)

        self.assertEqual(
            reports.investimento(*mes) + reports.disponivel(*mes),
            reports.receita(*mes),
        )

    def test_expenses_come_out_of_the_available_and_not_the_investment(self):
        """A conta de investimento é dinheiro guardado com um destino.

        Descontar-lhe a renda seria gastar duas vezes o mesmo euro.
        """

        self.com_percentagem("70.00")
        self.pagamento(valor="100.00")
        self.despesa(valor="20.00")

        mes = self.mes_de(self.hoje)

        self.assertEqual(reports.investimento(*mes), Decimal("70.00"))
        self.assertEqual(reports.disponivel(*mes), Decimal("10.00"))

    def test_the_available_can_go_negative(self):
        self.com_percentagem("70.00")
        self.pagamento(valor="100.00")
        self.despesa(valor="80.00")

        self.assertEqual(reports.disponivel(*self.mes_de(self.hoje)), Decimal("-50.00"))

    def test_without_a_percentage_nothing_is_set_aside(self):
        self.com_percentagem("0.00")
        self.pagamento(valor="100.00")

        mes = self.mes_de(self.hoje)

        self.assertEqual(reports.investimento(*mes), Decimal("0.00"))
        self.assertEqual(reports.disponivel(*mes), Decimal("100.00"))


class ThePercentageIsStampedTests(FinanceBase):
    """Mudar a percentagem não reescreve o que já foi separado."""

    def com_percentagem(self, valor):
        definicao = FinanceSetting.load()
        definicao.reinvestment_percent = Decimal(valor)
        definicao.save()

    def test_a_payment_keeps_the_percentage_it_was_born_with(self):
        self.com_percentagem("70.00")
        pagamento = self.pagamento(valor="100.00")

        self.com_percentagem("20.00")

        pagamento.refresh_from_db()

        self.assertEqual(pagamento.reinvestment_percent, Decimal("70.00"))
        self.assertEqual(
            reports.investimento(*self.mes_de(self.hoje)), Decimal("70.00")
        )

    def test_a_new_payment_uses_the_new_one(self):
        self.com_percentagem("70.00")
        self.pagamento(valor="100.00")

        self.com_percentagem("20.00")
        self.pagamento(self.marcacao(start_time=time(14, 0)), valor="100.00")

        # 70 do primeiro, 20 do segundo.
        self.assertEqual(
            reports.investimento(*self.mes_de(self.hoje)), Decimal("90.00")
        )

    def test_editing_an_old_payment_does_not_restamp_it(self):
        # Corrigir o valor de um pagamento antigo não pode trazer-lhe a
        # percentagem de hoje.
        self.com_percentagem("70.00")
        pagamento = self.pagamento(valor="100.00")

        self.com_percentagem("20.00")

        pagamento.amount = Decimal("50.00")
        pagamento.save()
        pagamento.refresh_from_db()

        self.assertEqual(pagamento.reinvestment_percent, Decimal("70.00"))

    def test_what_this_payment_set_aside(self):
        self.com_percentagem("70.00")

        self.assertEqual(self.pagamento(valor="35.50").to_invest, Decimal("24.85"))


class TheCashCountPicksAnAccountTests(FinanceBase):
    """Uma diferença encontrada numa conta não tem que fazer na outra."""

    def contagem(self, conta, esperado="0.00", contado="0.00", quando=None):
        return CashCount.objects.create(
            account=conta,
            counted_on=quando or self.hoje,
            expected_amount=Decimal(esperado),
            counted_amount=Decimal(contado),
        )

    def test_an_adjustment_moves_only_its_own_account(self):
        definicao = FinanceSetting.load()
        definicao.reinvestment_percent = Decimal("70.00")
        definicao.save()

        self.pagamento(valor="100.00")

        self.contagem(CashCount.ACCOUNT_INVESTMENT, esperado="70.00", contado="65.00")

        mes = self.mes_de(self.hoje)

        self.assertEqual(reports.investimento(*mes), Decimal("65.00"))
        self.assertEqual(reports.disponivel(*mes), Decimal("30.00"))

    def test_the_other_way_round_too(self):
        definicao = FinanceSetting.load()
        definicao.reinvestment_percent = Decimal("70.00")
        definicao.save()

        self.pagamento(valor="100.00")

        self.contagem(CashCount.ACCOUNT_AVAILABLE, esperado="30.00", contado="28.00")

        mes = self.mes_de(self.hoje)

        self.assertEqual(reports.investimento(*mes), Decimal("70.00"))
        self.assertEqual(reports.disponivel(*mes), Decimal("28.00"))

    def test_one_count_per_day_and_account(self):
        # Contar duas vezes a mesma conta no mesmo dia é ter duas verdades
        # sobre o mesmo dinheiro. Contas diferentes no mesmo dia é normal.
        from django.db import IntegrityError, transaction

        self.contagem(CashCount.ACCOUNT_AVAILABLE)
        self.contagem(CashCount.ACCOUNT_INVESTMENT)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.contagem(CashCount.ACCOUNT_AVAILABLE)

    def test_the_admin_offers_the_account(self):
        resposta = self.client.get("/admin/finance/cashcount/add/")

        self.assertContains(resposta, 'name="account"')
        self.assertEqual(
            resposta.context["adminform"].form.initial["account"],
            CashCount.ACCOUNT_AVAILABLE,
        )


class ThePercentageScreenTests(FinanceBase):
    def test_the_dashboard_shows_both_accounts(self):
        resposta = self.client.get(reverse("finance:dashboard"))

        self.assertContains(resposta, "Para investir")
        self.assertContains(resposta, "Disponível")
        self.assertContains(resposta, reverse("finance:setting"))

    def test_the_percentage_can_be_changed_from_the_internal_area(self):
        # É uma decisão de como se gere a casa, tomada por quem a gere. O
        # acerto de caixa é que é ferramenta de correção, e esse fica no admin.
        self.client.post(
            reverse("finance:setting"), data={"reinvestment_percent": "70.00"}
        )

        self.assertEqual(FinanceSetting.load().reinvestment_percent, Decimal("70.00"))

    def test_more_than_a_hundred_percent_is_refused(self):
        resposta = self.client.post(
            reverse("finance:setting"), data={"reinvestment_percent": "120.00"}
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(FinanceSetting.load().reinvestment_percent, Decimal("0.00"))

    def test_a_customer_cannot_change_it(self):
        cliente = get_user_model().objects.create_user(
            email="cliente@exemplo.pt",
            password="StrongPassword123",
            full_name="Cliente",
        )

        self.client.force_login(cliente)

        self.assertNotEqual(
            self.client.get(reverse("finance:setting")).status_code, 200
        )
