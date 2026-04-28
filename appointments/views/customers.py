from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from appointments.forms import CustomerForm
from appointments.models import Customer


class CustomerListView(LoginRequiredMixin, ListView):
    # Lists customers

    model = Customer
    template_name = "appointments/customer_list.html"
    context_object_name = "customers"


class CustomerCreateView(LoginRequiredMixin, CreateView):
    # Creates a new customer

    model = Customer
    form_class = CustomerForm
    template_name = "appointments/customer_form.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente criado com sucesso.")
        return super().form_valid(form)