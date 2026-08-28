"""O acerto de caixa, e só ele, no admin do Django.

Os pagamentos e as despesas têm ecrãs próprios na área interna e não se
registam aqui: dois sítios para a mesma coisa divergem, e o admin do Django
não sabe as regras que aqueles ecrãs impõem.

O acerto de caixa é o contrário — é uma ferramenta de correção, usada de vez em
quando por quem tem de responder pelas contas, e não trabalho diário. Por isso
vive só aqui, atrás do `is_staff`, que nesta casa é coisa diferente do acesso à
área interna: quem gere a agenda não chega aqui a menos que alguém lho dê.
"""

from django.contrib import admin

from finance.models import CashCount


@admin.register(CashCount)
class CashCountAdmin(admin.ModelAdmin):
    list_display = (
        "counted_on",
        "account",
        "expected_amount",
        "counted_amount",
        "diferenca",
        "created_by",
    )
    list_filter = ("account", "counted_on")
    search_fields = ("notes",)
    date_hierarchy = "counted_on"
    readonly_fields = ("created_by", "created_at", "updated_at")

    fieldsets = (
        (
            None,
            {
                "description": (
                    "Conte o dinheiro da caixa e escreva o que lá estava. "
                    "<strong>Isto não altera a receita</strong>: a receita "
                    "continua a ser a soma dos pagamentos registados. O que "
                    "fica aqui é a diferença, com a data e a razão — e uma "
                    "diferença quer dizer que falta um registo ou sobra um "
                    "engano, que se corrige no pagamento e não no total."
                    "<br><br>"
                    "<strong>Escolha a conta</strong> que está a contar. As "
                    "duas são dinheiro diferente: o que está separado para "
                    "reinvestir não é o que está disponível, e uma diferença "
                    "encontrada numa não tem nada que fazer na outra."
                ),
                "fields": (
                    "account",
                    "counted_on",
                    "expected_amount",
                    "counted_amount",
                    "notes",
                ),
            },
        ),
        (
            "Registo",
            {
                "classes": ("collapse",),
                "fields": ("created_by", "created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Diferença", ordering="counted_amount")
    def diferenca(self, obj):
        """O que interessa ler na lista: sobrou ou faltou, e quanto."""

        valor = obj.difference

        if valor == 0:
            return "certo"

        return f"{valor:+} €"

    def get_changeform_initial_data(self, request):
        """Traz o esperado já preenchido, para hoje e para a conta disponível.

        Calculado e não escrito à mão: somar os pagamentos em dinheiro do dia
        de cabeça é exatamente o passo onde o erro entra, e é o passo que o
        computador faz melhor.

        **Só a conta disponível é que tem um esperado calculável.** A de
        investimento é dinheiro separado que não passa pela caixa: quem a
        contar sabe o que lá devia estar, o sistema não. Por isso o valor vem
        a zero quando se escolhe essa — e escreve-se à mão, que é o que uma
        contagem é.
        """

        from django.utils import timezone

        hoje = timezone.localdate()

        return {
            "account": CashCount.ACCOUNT_AVAILABLE,
            "counted_on": hoje,
            "expected_amount": CashCount.expected_for(hoje),
        }

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user

        super().save_model(request, obj, form, change)
