from django.contrib import messages
from appointments.mixins import SuperuserRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from appointments.forms import CustomerForm
from appointments.models import Customer


class CustomerListView(SuperuserRequiredMixin, ListView):
    # Lists customers

    model = Customer
    template_name = "appointments/customer_list.html"
    context_object_name = "customers"


class CustomerCreateView(SuperuserRequiredMixin, CreateView):
    # Creates a new customer

    model = Customer
    form_class = CustomerForm
    template_name = "appointments/customer_form.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente criado com sucesso.")
        return super().form_valid(form)
    
class CustomerUpdateView(SuperuserRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "appointments/customer_form.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente atualizado com sucesso.")
        return super().form_valid(form)    