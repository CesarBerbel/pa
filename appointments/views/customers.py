from django.contrib import messages
from django.db.models import ProtectedError
from appointments.mixins import SuperuserRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from appointments.forms import CustomerForm
from appointments.models import Customer


class CustomerListView(SuperuserRequiredMixin, ListView):
    # Lists customers.

    model = Customer
    template_name = "appointments/customer_list.html"
    context_object_name = "customers"


class CustomerCreateView(SuperuserRequiredMixin, CreateView):
    # Creates a new customer.

    model = Customer
    form_class = CustomerForm
    template_name = "appointments/customer_form.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente criado com sucesso.")
        return super().form_valid(form)


class CustomerUpdateView(SuperuserRequiredMixin, UpdateView):
    # Updates an existing customer.

    model = Customer
    form_class = CustomerForm
    template_name = "appointments/customer_form.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente atualizado com sucesso.")
        return super().form_valid(form)


class CustomerDeleteView(SuperuserRequiredMixin, DeleteView):
    # Deletes a customer only when there are no protected related appointments.

    model = Customer
    template_name = "appointments/customer_confirm_delete.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        # Protect appointment history by handling protected foreign key errors gracefully.
        try:
            response = super().form_valid(form)
            messages.success(self.request, "Cliente excluído com sucesso.")
            return response
        except ProtectedError:
            messages.error(
                self.request,
                "Este cliente não pode ser excluído porque possui marcações vinculadas. "
                "Para preservar o histórico, edite os dados do cliente em vez de excluí-lo.",
            )
            return redirect("appointments:customer_list")