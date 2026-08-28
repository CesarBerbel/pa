"""As contas: quanto entrou, quanto saiu, e o que sobrou.

Tudo aqui é somado pela base de dados e não em Python. Não é preciosismo: um
ano de pagamentos trazido para memória para ser somado num ciclo é a diferença
entre um ecrã que abre e um ecrã que se pensa que está partido.

**As datas são a do dinheiro.** Um pagamento conta no mês em que foi recebido
e uma despesa no mês em que foi feita, e não na data da consulta que os
originou. É como se lê um extrato bancário, e é o que responde à pergunta que
se faz ao fim do mês.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from appointments.models import Appointment
from finance.models import CashCount, Expense, Payment

ZERO = Decimal("0.00")

# `Coalesce` porque um `Sum` sem linhas devolve `None`, e `None` não se soma
# nem se subtrai. Um mês sem despesas tem zero de despesas, não "sem valor".
DINHEIRO = DecimalField(max_digits=12, decimal_places=2)


def _soma(queryset, campo="amount"):
    return queryset.aggregate(
        total=Coalesce(Sum(campo), Value(ZERO), output_field=DINHEIRO)
    )["total"]


def limites_do_mes(ano, mes):
    """O primeiro e o último dia do mês, inclusive.

    Devolvidos como datas e não como um intervalo aberto porque é assim que os
    filtros deste módulo os usam: `__range` inclui as duas pontas, e o último
    dia do mês tem de contar.
    """

    return date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])


def receita(inicio, fim):
    return _soma(Payment.objects.filter(paid_on__range=(inicio, fim)))


def despesa(inicio, fim):
    return _soma(Expense.objects.filter(spent_on__range=(inicio, fim)))


def resultado(inicio, fim):
    """O que sobrou. Pode ser negativo, e é importante que possa.

    Um resultado travado em zero esconderia exatamente o mês que interessa
    olhar.
    """

    return receita(inicio, fim) - despesa(inicio, fim)


def receita_por_servico(inicio, fim):
    """Quanto cada serviço rendeu no período, do que mais rendeu ao que menos.

    Pelo serviço da marcação e não pelo preço de tabela: o que se soma é o que
    foi cobrado.
    """

    return (
        Payment.objects.filter(paid_on__range=(inicio, fim))
        .values("appointment__service__name")
        .annotate(
            total=Coalesce(Sum("amount"), Value(ZERO), output_field=DINHEIRO),
            quantas=Count("id"),
        )
        .order_by("-total")
    )


def despesa_por_categoria(inicio, fim):
    despesas = (
        Expense.objects.filter(spent_on__range=(inicio, fim))
        .values("category")
        .annotate(
            total=Coalesce(Sum("amount"), Value(ZERO), output_field=DINHEIRO),
            quantas=Count("id"),
        )
        .order_by("-total")
    )

    # O nome legível vem das escolhas do modelo. Resolver isto aqui e não no
    # template evita um `get_..._display` sobre um dicionário, que não existe.
    nomes = dict(Expense.CATEGORY_CHOICES)

    return [
        {**linha, "nome": nomes.get(linha["category"], linha["category"])}
        for linha in despesas
    ]


def receita_por_semana(inicio, fim):
    """A receita do mês repartida pelas semanas, de segunda a domingo.

    Semanas civis e não blocos de sete dias a contar do dia 1: uma clínica
    trabalha a semanas, e "de 8 a 14" não quer dizer nada a quem pensa em
    "a semana passada". A primeira e a última do mês vêm cortadas — é o que
    elas são de facto, e cortá-las é mais honesto do que ir buscar receita de
    outro mês para as encher.

    Cada semana sai com o intervalo de dias que ocupa dentro do mês, para o
    gráfico poder dizer a que dias corresponde cada barra.
    """

    pagamentos = Payment.objects.filter(paid_on__range=(inicio, fim))

    por_dia = {
        linha["paid_on"]: linha["total"]
        for linha in pagamentos.values("paid_on").annotate(
            total=Coalesce(Sum("amount"), Value(ZERO), output_field=DINHEIRO)
        )
    }

    semanas = []
    dia = inicio

    while dia <= fim:
        # O domingo desta semana, ou o fim do mês se ele vier primeiro.
        fim_da_semana = min(dia + timedelta(days=6 - dia.weekday()), fim)

        total = ZERO
        cursor = dia

        while cursor <= fim_da_semana:
            total += por_dia.get(cursor, ZERO)
            cursor += timedelta(days=1)

        semanas.append(
            {
                "inicio": dia,
                "fim": fim_da_semana,
                "rotulo": f"{dia.day}–{fim_da_semana.day}",
                "total": total,
            }
        )

        dia = fim_da_semana + timedelta(days=1)

    return semanas


def por_pagar(ate=None):
    """Marcações concluídas sem pagamento registado.

    É a lista de quem está a dever, e ninguém a mantém à mão: uma marcação
    entra aqui por não ter pagamento e sai daqui quando o tiver.

    Só as concluídas. Uma marcação futura ainda não é uma dívida, e uma
    cancelada nunca chegou a ser.
    """

    return (
        Appointment.objects.filter(
            status=Appointment.STATUS_COMPLETED,
            payment__isnull=True,
            date__lte=ate or timezone.localdate(),
        )
        .select_related("customer", "service")
        .order_by("date", "start_time")
    )


def total_por_pagar(ate=None):
    """Quanto está por receber, pelo preço de tabela de cada serviço.

    Pelo preço de tabela porque é a única estimativa que há: o valor cobrado só
    existe depois de haver pagamento, e estas são precisamente as que não têm.
    Quem olhar para este número tem de saber que é uma estimativa — e é por
    isso que o ecrã lhe chama "cerca de".
    """

    return _soma(por_pagar(ate), "service__price")


def previsto(inicio, fim, hoje=None):
    """O que ainda está para acontecer neste mês, pelo preço de tabela.

    Previsto é o que **falta** entrar, e não o que o mês inteiro valeu. Por
    isso são só as marcações **futuras** e **confirmadas**:

    * as que já passaram não são previsão nenhuma — ou foram concluídas, e
      então o que interessa delas é a receita ou a dívida, ou estão por
      concluir, e essas aparecem no dashboard operacional;
    * as agendadas por confirmar ainda não são um compromisso: contar dinheiro
      de uma consulta que ninguém confirmou é contar com o que pode não
      acontecer.

    Num mês já passado dá zero, e está certo: não há nada previsto num mês que
    já aconteceu.

    Pelo preço de tabela porque é a única estimativa que há antes de haver
    pagamento. Depois de haver, o valor certo é o cobrado — e é esse que a
    `receita` conta.
    """

    hoje = hoje or timezone.localdate()

    return _soma(
        Appointment.objects.filter(
            date__range=(max(inicio, hoje), fim),
            status=Appointment.STATUS_CONFIRMED,
        ),
        "service__price",
    )


def _acertos(inicio, fim, conta):
    """A soma das diferenças encontradas nas contagens dessa conta.

    Calculada na base de dados e não pela propriedade `difference` do modelo:
    somar em Python obrigava a trazer todas as contagens para memória, e o que
    se quer daqui é um número.
    """

    return CashCount.objects.filter(
        counted_on__range=(inicio, fim), account=conta
    ).aggregate(
        total=Coalesce(
            Sum(F("counted_amount") - F("expected_amount"), output_field=DINHEIRO),
            Value(ZERO),
            output_field=DINHEIRO,
        )
    )[
        "total"
    ]


def _separado(inicio, fim):
    """A fatia dos pagamentos que ficou carimbada para investir.

    De cada pagamento sai a percentagem que ficou gravada **nele**, e não a de
    hoje. Mudar a percentagem de 70 para 50 não reescreve o que já foi
    separado: um saldo que muda sozinho porque alguém mexeu numa definição
    deixa de ser um saldo.
    """

    return Payment.objects.filter(paid_on__range=(inicio, fim)).aggregate(
        total=Coalesce(
            Sum(
                F("amount") * F("reinvestment_percent") / Value(Decimal("100")),
                output_field=DINHEIRO,
            ),
            Value(ZERO),
            output_field=DINHEIRO,
        )
    )["total"]


def investimento(inicio, fim):
    """O saldo da conta de investimento no mês.

    A fatia separada dos pagamentos, mais as diferenças encontradas ao contar
    esta conta. É para isso que os acertos servem: quando o dinheiro contado
    não bate com o registado, a diferença tem de aparecer algures, e o sítio é
    o saldo da conta que foi contada.
    """

    return _separado(inicio, fim) + _acertos(inicio, fim, CashCount.ACCOUNT_INVESTMENT)


def disponivel(inicio, fim):
    """O que sobra depois de separar o investimento e pagar as despesas.

    Escrito com o `_separado` e não com o `investimento`: os acertos da conta
    de investimento não mexem nesta. Uma versão anterior subtraía o saldo do
    investimento e voltava a somar o acerto dele para o anular — dava o mesmo
    número e não havia como ler que dava.

    As despesas saem daqui e não do investimento porque é daqui que se vive: a
    conta de investimento é dinheiro guardado com um destino, e descontar-lhe a
    renda seria gastar duas vezes o mesmo euro.

    Pode ser negativo, e é importante que possa — um mês em que as despesas
    passaram o que sobrou é exatamente o mês que interessa ver.
    """

    return (
        receita(inicio, fim)
        - _separado(inicio, fim)
        - despesa(inicio, fim)
        + _acertos(inicio, fim, CashCount.ACCOUNT_AVAILABLE)
    )
