from django.urls import path

from finance.views import (
    ExpenseCreateView,
    ExpenseDeleteView,
    ExpenseListView,
    ExpenseUpdateView,
    FinanceDashboardView,
    FinanceSettingView,
    PaymentCreateView,
    PaymentDeleteView,
    PaymentListView,
    PaymentUpdateView,
    UnpaidListView,
)

app_name = "finance"

urlpatterns = [
    path("", FinanceDashboardView.as_view(), name="dashboard"),
    path("recebimentos/", PaymentListView.as_view(), name="payment_list"),
    path("por-receber/", UnpaidListView.as_view(), name="unpaid_list"),
    # O pagamento entra pela marcação: é sempre de alguma coisa, e escolher a
    # marcação num campo à parte era repetir o caminho já feito para lá chegar.
    path(
        "marcacoes/<int:pk>/pagamento/",
        PaymentCreateView.as_view(),
        name="payment_create",
    ),
    path(
        "pagamentos/<int:pk>/editar/",
        PaymentUpdateView.as_view(),
        name="payment_update",
    ),
    path(
        "pagamentos/<int:pk>/apagar/",
        PaymentDeleteView.as_view(),
        name="payment_delete",
    ),
    path("reinvestimento/", FinanceSettingView.as_view(), name="setting"),
    path("despesas/", ExpenseListView.as_view(), name="expense_list"),
    path("despesas/nova/", ExpenseCreateView.as_view(), name="expense_create"),
    path(
        "despesas/<int:pk>/editar/", ExpenseUpdateView.as_view(), name="expense_update"
    ),
    path(
        "despesas/<int:pk>/apagar/", ExpenseDeleteView.as_view(), name="expense_delete"
    ),
]
