"""Os formulários do financeiro."""

from django import forms

from finance.models import Expense, FinanceSetting, Payment


class PaymentForm(forms.ModelForm):
    """Registar o que foi cobrado por uma marcação.

    O valor nasce preenchido com o preço de tabela do serviço — é o que se
    cobra quase sempre — mas continua a ser um campo. Um desconto a uma cliente
    antiga ou um arredondamento não devem obrigar a nada: escreve-se por cima.
    """

    class Meta:
        model = Payment
        fields = ["amount", "method", "paid_on", "notes"]

        widgets = {
            "paid_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, appointment=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["notes"].required = False

        if appointment and not self.instance.pk and not self.initial.get("amount"):
            preco = getattr(appointment.service, "price", None)

            if preco is not None:
                self.initial["amount"] = preco

        self.fields["amount"].help_text = (
            "Vem preenchido com o preço do serviço. Escreva por cima se "
            "cobrou outro valor."
        )


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["spent_on", "category", "description", "amount", "notes"]

        widgets = {
            "spent_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["notes"].required = False


class FinanceSettingForm(forms.ModelForm):
    """A fatia de cada pagamento que vai para a conta de investimento."""

    class Meta:
        model = FinanceSetting
        fields = ["reinvestment_percent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["reinvestment_percent"].help_text = (
            "Aplica-se aos pagamentos registados a partir de agora. Os que já "
            "existem ficam com a percentagem que tinham quando foram "
            "registados — mudar isto não reescreve meses passados."
        )
