"""O dinheiro que entra e o que sai.

Três decisões que decidem tudo o resto neste módulo:

**A receita conta-se quando o dinheiro chega, e não quando o serviço é
prestado.** Um atendimento concluído em agosto e pago em setembro é receita de
setembro. É assim que quem gere uma clínica pequena pensa no mês — o que
importa é o que entrou na caixa — e é por isso que o `Pagamento` tem data
própria em vez de usar a da marcação.

**O valor é o cobrado, não o de tabela.** Um desconto a uma cliente antiga, um
arredondamento, um valor combinado à parte: se a receita saísse do preço do
serviço, o total do mês seria o que se devia ter cobrado e não o que se
cobrou. O preço do serviço passa a ser só a sugestão que o formulário oferece.

**Uma marcação concluída sem pagamento é uma dívida, não um zero.** É o que
faz a lista de quem está a dever existir sem ninguém ter de a manter: quem
não tem pagamento registado está lá, e sai de lá quando o registo aparecer.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")


class FinanceSetting(models.Model):
    """Quanto de cada pagamento é posto de lado para reinvestir.

    A clínica separa o dinheiro em duas contas: uma para pôr de volta no
    negócio — material, equipamento, formação — e outra para o que fica
    disponível. Isto guarda a fatia da primeira.

    Existe uma linha só, com pk fixo. É uma definição da casa, não uma lista.
    """

    SINGLETON_PK = 1

    reinvestment_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Percentagem de reinvestimento",
        help_text=(
            "De cada pagamento, quanto vai para a conta de investimento. "
            "Zero não separa nada."
        ),
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Definição do financeiro"
        verbose_name_plural = "Definições do financeiro"

    def __str__(self):
        return f"{self.reinvestment_percent}% para investir"

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK

        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        definicao, _criada = cls.objects.get_or_create(pk=cls.SINGLETON_PK)

        return definicao

    @classmethod
    def percentagem(cls):
        """A fatia de agora, para carimbar num pagamento novo.

        Em caso de erro a ler a definição, devolve zero: separar dinheiro a
        mais por causa de uma falha de leitura é pior do que não separar nada,
        porque o de menos vê-se na conta e o de mais só se vê ao fim do mês.
        """

        try:
            return cls.load().reinvestment_percent
        except Exception:
            logger.exception("Não foi possível ler a percentagem de reinvestimento.")

            return ZERO


class Payment(models.Model):
    """O que foi cobrado por uma marcação, quando e como."""

    METHOD_CASH = "cash"
    METHOD_MBWAY = "mbway"
    METHOD_CARD = "card"
    METHOD_TRANSFER = "transfer"
    METHOD_OTHER = "other"

    METHOD_CHOICES = [
        (METHOD_CASH, "Dinheiro"),
        (METHOD_MBWAY, "MB Way"),
        (METHOD_CARD, "Multibanco"),
        (METHOD_TRANSFER, "Transferência"),
        (METHOD_OTHER, "Outro"),
    ]

    # Um para um: uma marcação cobra-se uma vez. Pagamentos em duas partes
    # existem, mas são raros nesta casa e resolvem-se com um registo pelo total
    # e uma nota — um modelo que os suportasse obrigaria todos os ecrãs a somar
    # linhas para responder "esta consulta está paga?".
    appointment = models.OneToOneField(
        "appointments.Appointment",
        on_delete=models.CASCADE,
        related_name="payment",
        verbose_name="Marcação",
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Valor cobrado",
        help_text="O que a pessoa pagou. Pode não ser o preço de tabela.",
    )

    method = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        default=METHOD_CASH,
        verbose_name="Como pagou",
    )

    # A data do dinheiro, não a do atendimento. É esta que decide em que mês a
    # receita entra.
    paid_on = models.DateField(
        default=timezone.localdate,
        verbose_name="Data do pagamento",
    )

    # A fatia que foi para investir, carimbada no momento do pagamento.
    #
    # Guardada e não aplicada ao vivo pela mesma razão do `expected_amount` do
    # acerto de caixa: mudar a percentagem de 70 para 50 não pode reescrever o
    # que já foi separado nos meses anteriores. Um saldo que muda sozinho
    # porque alguém mexeu numa definição deixa de ser um saldo.
    reinvestment_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        verbose_name="% para investir",
    )

    notes = models.TextField(blank=True, verbose_name="Notas")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_registered",
        verbose_name="Registado por",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-paid_on", "-id"]
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamentos"
        indexes = [
            # A pergunta mais frequente deste modelo é "quanto entrou entre
            # duas datas". Sem índice, isso é uma varredura da tabela inteira a
            # cada abertura do ecrã.
            models.Index(fields=["paid_on"]),
        ]

    def __str__(self):
        return f"{self.amount} € — {self.appointment}"

    def clean(self):
        # Um pagamento com data futura não é um pagamento: é uma expectativa, e
        # entraria na receita de um mês que ainda não aconteceu.
        if self.paid_on and self.paid_on > timezone.localdate():
            raise ValidationError(
                {"paid_on": "A data do pagamento não pode ser no futuro."}
            )

    def save(self, *args, **kwargs):
        """Carimba a fatia de reinvestimento, uma vez só.

        Só ao criar: reeditar um pagamento antigo — para corrigir o valor, por
        exemplo — não pode trazer-lhe a percentagem de hoje.
        """

        if self._state.adding and not self.reinvestment_percent:
            self.reinvestment_percent = FinanceSetting.percentagem()

        super().save(*args, **kwargs)

    @property
    def to_invest(self):
        """A parte deste pagamento que foi posta de lado."""

        return (self.amount * self.reinvestment_percent / 100).quantize(Decimal("0.01"))


class Expense(models.Model):
    """Uma despesa da clínica: material, renda, o que for.

    Sem ligação a marcações de propósito. Uma caixa de compressas serve trinta
    consultas e nenhuma em particular, e repartir custos por atendimento é
    contabilidade analítica — outro problema, e maior do que este.
    """

    CATEGORY_SUPPLIES = "supplies"
    CATEGORY_EQUIPMENT = "equipment"
    CATEGORY_RENT = "rent"
    CATEGORY_TRAINING = "training"
    CATEGORY_TRAVEL = "travel"
    CATEGORY_MARKETING = "marketing"
    CATEGORY_TAXES = "taxes"
    CATEGORY_OTHER = "other"

    CATEGORY_CHOICES = [
        (CATEGORY_SUPPLIES, "Material clínico"),
        (CATEGORY_EQUIPMENT, "Equipamento"),
        (CATEGORY_RENT, "Renda e despesas do espaço"),
        (CATEGORY_TRAINING, "Formação"),
        (CATEGORY_TRAVEL, "Deslocações"),
        (CATEGORY_MARKETING, "Divulgação"),
        (CATEGORY_TAXES, "Impostos e contribuições"),
        (CATEGORY_OTHER, "Outra"),
    ]

    spent_on = models.DateField(
        default=timezone.localdate,
        verbose_name="Data",
    )

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_SUPPLIES,
        verbose_name="Categoria",
    )

    description = models.CharField(
        max_length=200,
        verbose_name="Descrição",
        help_text="O que foi. Exemplo: caixa de compressas, 100 unidades.",
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Valor",
    )

    notes = models.TextField(blank=True, verbose_name="Notas")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_registered",
        verbose_name="Registada por",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-spent_on", "-id"]
        verbose_name = "Despesa"
        verbose_name_plural = "Despesas"
        indexes = [
            models.Index(fields=["spent_on"]),
        ]

    def __str__(self):
        return f"{self.description} — {self.amount} €"

    def clean(self):
        if self.spent_on and self.spent_on > timezone.localdate():
            raise ValidationError({"spent_on": "A data não pode ser no futuro."})


class CashCount(models.Model):
    """A contagem do dinheiro que está na caixa, e a diferença que apareceu.

    Serve para o momento em que se conta as notas e as moedas e o valor não
    bate com o que o sistema diz. Isso acontece — um troco mal dado, um
    pagamento por registar, uma despesa paga da caixa — e o que interessa não é
    esconder a diferença: é deixá-la escrita, com data e com a razão.

    **Não reescreve a receita.** É a decisão mais importante deste modelo e
    merece ser dita por inteiro: a receita continua a ser a soma dos pagamentos
    registados, e uma contagem não lhe toca. Se tocasse, os números do mês
    passavam a depender de quem contou a caixa e de quando — e um relatório que
    muda por causa de uma contagem deixa de poder ser conferido contra os
    pagamentos que o formam. O que uma diferença diz é que falta um registo ou
    sobra um engano, e o caminho é corrigir o registo, não o total.

    **O esperado fica guardado e não é recalculado.** É o que o sistema dizia
    no momento da contagem, e isso é um facto daquele momento. Recalculado hoje,
    um pagamento acrescentado depois faria a diferença de há um mês mudar
    sozinha — e o registo deixava de ser a fotografia que era suposto ser.

    Vive só no admin do Django, por decisão: é uma ferramenta de correção, não
    de trabalho diário, e a área interna é para o trabalho diário.
    """

    ACCOUNT_AVAILABLE = "available"
    ACCOUNT_INVESTMENT = "investment"

    ACCOUNT_CHOICES = [
        (ACCOUNT_AVAILABLE, "Disponível"),
        (ACCOUNT_INVESTMENT, "Investimento"),
    ]

    # Que conta é que esta contagem acerta. Sem isto, uma diferença encontrada
    # na caixa não sabia onde pousar — e as duas contas são dinheiro
    # diferente: o que está para reinvestir não é o que está disponível.
    account = models.CharField(
        max_length=20,
        choices=ACCOUNT_CHOICES,
        default=ACCOUNT_AVAILABLE,
        verbose_name="Conta",
    )

    counted_on = models.DateField(
        default=timezone.localdate,
        verbose_name="Dia contado",
        help_text="Uma contagem por dia. Contar duas vezes o mesmo dia é ter duas verdades.",
    )

    expected_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="O que o sistema diz",
        help_text="Pagamentos em dinheiro registados nesse dia.",
    )

    counted_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="O que estava na caixa",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Razão da diferença",
        help_text="O que explica a diferença, tanto quanto se saiba.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_counts",
        verbose_name="Contado por",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-counted_on"]
        verbose_name = "Acerto de caixa"
        verbose_name_plural = "Acertos de caixa"
        constraints = [
            # Uma contagem por dia **e por conta**: contar duas vezes a mesma
            # conta no mesmo dia é ter duas verdades sobre o mesmo dinheiro.
            models.UniqueConstraint(
                fields=["counted_on", "account"],
                name="uma_contagem_por_dia_e_conta",
            ),
        ]

    def __str__(self):
        return f"{self.counted_on:%d/%m/%Y} — {self.difference:+} €"

    @property
    def difference(self):
        """Contado menos esperado. Negativo é dinheiro a menos na caixa."""

        return (self.counted_amount or ZERO) - (self.expected_amount or ZERO)

    @staticmethod
    def expected_for(day):
        """O que o sistema diz que devia estar na caixa nesse dia.

        Só os pagamentos **em dinheiro**: o que entrou por MB Way ou multibanco
        não passa pela caixa, e somá-lo faria a diferença acusar sempre uma
        falta do tamanho dos pagamentos eletrónicos.
        """

        from django.db.models import Sum
        from django.db.models.functions import Coalesce

        return Payment.objects.filter(
            paid_on=day, method=Payment.METHOD_CASH
        ).aggregate(
            total=Coalesce(
                Sum("amount"),
                models.Value(ZERO),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        )[
            "total"
        ]

    def clean(self):
        if self.counted_on and self.counted_on > timezone.localdate():
            raise ValidationError(
                {"counted_on": "Não se conta uma caixa que ainda não aconteceu."}
            )
