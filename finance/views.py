"""Os ecrãs do financeiro.

Um resumo que responde "como correu o mês", e três listas por trás dele: o que
entrou, o que saiu, e o que está por receber.

Tudo atrás do `InternalAreaRequiredMixin`. O dinheiro da casa não é dado
clínico, mas também não é público — e a área interna é a fronteira que este
projeto já tem.
"""

from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    TemplateView,
    UpdateView,
)

from appointments.mixins import InternalAreaRequiredMixin
from appointments.models import Appointment
from finance import reports
from finance.forms import ExpenseForm, FinanceSettingForm, PaymentForm
from finance.models import Expense, FinanceSetting, Payment

MESES = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def mes_pedido(request):
    """O mês que se está a ver, vindo do endereço ou o de hoje.

    Um mês inválido — escrito à mão, ou de um link antigo — cai no mês atual em
    vez de rebentar: um ecrã de contas não deve dar erro por causa de um
    parâmetro.
    """

    hoje = timezone.localdate()

    try:
        ano = int(request.GET.get("ano") or hoje.year)
        mes = int(request.GET.get("mes") or hoje.month)

        date(ano, mes, 1)
    except (TypeError, ValueError):
        return hoje.year, hoje.month

    return ano, mes


class FinanceDashboardView(InternalAreaRequiredMixin, TemplateView):
    """Como correu o mês, num ecrã.

    Receita, despesa e o que sobrou — e, ao lado, o que ainda está por receber,
    que é o número que costuma faltar nestes resumos e o único sobre o qual se
    pode agir hoje.
    """

    template_name = "finance/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        ano, mes = mes_pedido(self.request)
        inicio, fim = reports.limites_do_mes(ano, mes)

        context["ano"] = ano
        context["mes"] = mes
        context["nome_do_mes"] = MESES[mes - 1]

        context["previsto"] = reports.previsto(inicio, fim)
        context["receita"] = reports.receita(inicio, fim)
        context["despesa"] = reports.despesa(inicio, fim)
        context["resultado"] = reports.resultado(inicio, fim)

        context["por_servico"] = reports.receita_por_servico(inicio, fim)
        context["por_categoria"] = reports.despesa_por_categoria(inicio, fim)

        context["por_pagar"] = reports.por_pagar()[:8]
        context["por_pagar_total"] = reports.total_por_pagar()
        context["por_pagar_quantas"] = reports.por_pagar().count()

        # Semanal e não anual: o ecrã inteiro é sobre um mês, e um gráfico
        # do ano era a única coisa aqui a falar de outra coisa.
        context["semanas"] = reports.receita_por_semana(inicio, fim)

        # As duas contas, debaixo do gráfico. Do mês que se está a ver, como
        # tudo o resto neste ecrã.
        context["investimento"] = reports.investimento(inicio, fim)
        context["disponivel"] = reports.disponivel(inicio, fim)
        context["percentagem"] = FinanceSetting.load().reinvestment_percent

        # Para as setas de navegação. Feito aqui e não no template porque
        # dezembro→janeiro muda o ano, e o template não sabe contar.
        context["mes_anterior"] = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
        context["mes_seguinte"] = (ano + 1, 1) if mes == 12 else (ano, mes + 1)

        return context


class PaymentListView(InternalAreaRequiredMixin, ListView):
    template_name = "finance/payment_list.html"
    context_object_name = "payments"
    paginate_by = 50

    def get_queryset(self):
        ano, mes = mes_pedido(self.request)
        inicio, fim = reports.limites_do_mes(ano, mes)

        return (
            Payment.objects.filter(paid_on__range=(inicio, fim))
            .select_related("appointment__customer", "appointment__service")
            .order_by("-paid_on", "-id")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        ano, mes = mes_pedido(self.request)
        inicio, fim = reports.limites_do_mes(ano, mes)

        context["ano"] = ano
        context["mes"] = mes
        context["nome_do_mes"] = MESES[mes - 1]
        context["total"] = reports.receita(inicio, fim)

        return context


class PaymentCreateView(InternalAreaRequiredMixin, CreateView):
    """Registar o pagamento de uma marcação.

    Chega-se aqui pela marcação e não por uma lista: um pagamento é sempre de
    alguma coisa, e escolher a marcação num campo à parte era repetir o
    caminho que já foi feito para lá chegar.
    """

    model = Payment
    form_class = PaymentForm
    template_name = "finance/payment_form.html"

    def marcacao(self):
        return get_object_or_404(
            Appointment.objects.select_related("customer", "service"),
            pk=self.kwargs["pk"],
        )

    def dispatch(self, request, *args, **kwargs):
        recusa = self.get_permission_denied_response()

        if recusa:
            return recusa

        marcacao = self.marcacao()

        # Uma marcação cobra-se uma vez. Sem isto, o segundo registo rebentava
        # com um erro de base de dados em vez de dizer o que se passa.
        if hasattr(marcacao, "payment"):
            messages.info(
                request,
                f"O pagamento de {marcacao.customer.full_name} já estava registado.",
            )

            return redirect("finance:payment_update", pk=marcacao.payment.pk)

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["appointment"] = self.marcacao()

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["appointment"] = self.marcacao()

        return context

    def form_valid(self, form):
        form.instance.appointment = self.marcacao()
        form.instance.created_by = self.request.user

        resposta = super().form_valid(form)

        messages.success(self.request, "Pagamento registado.")

        return resposta

    def get_success_url(self):
        return self.request.POST.get("next") or reverse(
            "appointments:appointment_detail", args=[self.kwargs["pk"]]
        )


class PaymentUpdateView(InternalAreaRequiredMixin, UpdateView):
    model = Payment
    form_class = PaymentForm
    template_name = "finance/payment_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["appointment"] = self.object.appointment

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["appointment"] = self.object.appointment

        return context

    def form_valid(self, form):
        messages.success(self.request, "Pagamento atualizado.")

        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "appointments:appointment_detail", args=[self.object.appointment_id]
        )


class PaymentDeleteView(InternalAreaRequiredMixin, DeleteView):
    """Apagar um registo de pagamento devolve a marcação à lista de dívidas.

    Não é um efeito colateral escondido: é a razão de existir. Um pagamento
    registado por engano tem de poder ser desfeito, e a marcação volta a
    contar como por receber sem ninguém ter de a pôr lá.
    """

    model = Payment
    template_name = "finance/payment_confirm_delete.html"

    def post(self, request, *args, **kwargs):
        messages.success(request, "Registo de pagamento apagado.")

        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse(
            "appointments:appointment_detail", args=[self.object.appointment_id]
        )


class UnpaidListView(InternalAreaRequiredMixin, ListView):
    """Quem está a dever. A lista mantém-se sozinha."""

    template_name = "finance/unpaid_list.html"
    context_object_name = "appointments"
    paginate_by = 50

    def get_queryset(self):
        return reports.por_pagar()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total"] = reports.total_por_pagar()

        return context


class ExpenseListView(InternalAreaRequiredMixin, ListView):
    template_name = "finance/expense_list.html"
    context_object_name = "expenses"
    paginate_by = 50

    def get_queryset(self):
        ano, mes = mes_pedido(self.request)
        inicio, fim = reports.limites_do_mes(ano, mes)

        return Expense.objects.filter(spent_on__range=(inicio, fim))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        ano, mes = mes_pedido(self.request)
        inicio, fim = reports.limites_do_mes(ano, mes)

        context["ano"] = ano
        context["mes"] = mes
        context["nome_do_mes"] = MESES[mes - 1]
        context["total"] = reports.despesa(inicio, fim)

        return context


class ExpenseCreateView(InternalAreaRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "finance/expense_form.html"
    success_url = reverse_lazy("finance:expense_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user

        messages.success(self.request, "Despesa registada.")

        return super().form_valid(form)


class ExpenseUpdateView(InternalAreaRequiredMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "finance/expense_form.html"
    success_url = reverse_lazy("finance:expense_list")

    def form_valid(self, form):
        messages.success(self.request, "Despesa atualizada.")

        return super().form_valid(form)


class ExpenseDeleteView(InternalAreaRequiredMixin, DeleteView):
    model = Expense
    template_name = "finance/expense_confirm_delete.html"
    success_url = reverse_lazy("finance:expense_list")

    def post(self, request, *args, **kwargs):
        messages.success(request, "Despesa apagada.")

        return super().post(request, *args, **kwargs)


class FinanceSettingView(InternalAreaRequiredMixin, UpdateView):
    """A percentagem de reinvestimento.

    Fica na área interna e não no admin: é uma decisão de como se gere a casa,
    tomada por quem a gere. O acerto de caixa é que é ferramenta de correção, e
    esse fica no admin.
    """

    model = FinanceSetting
    form_class = FinanceSettingForm
    template_name = "finance/setting_form.html"
    success_url = reverse_lazy("finance:dashboard")

    def get_object(self, queryset=None):
        return FinanceSetting.load()

    def form_valid(self, form):
        messages.success(self.request, "Percentagem de reinvestimento atualizada.")

        return super().form_valid(form)
