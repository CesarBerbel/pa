from django.contrib import messages
from appointments.mixins import SuperuserRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from appointments.forms import CustomerForm
from appointments.models import Appointment, Customer


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
    # Updates an existing customer

    model = Customer
    form_class = CustomerForm
    template_name = "appointments/customer_form.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente atualizado com sucesso.")
        return super().form_valid(form)


class CustomerDeleteView(SuperuserRequiredMixin, TemplateView):
    # Shows delete confirmation on GET and deletes customer on POST

    template_name = "appointments/customer_confirm_delete.html"

    def get_customer(self):
        # Get customer safely by primary key
        return Customer.objects.get(pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        # Send customer data to confirmation template
        context = super().get_context_data(**kwargs)
        context["customer"] = self.get_customer()
        return context

    def post(self, request, pk):
        # Delete customer only if there are no appointments linked to it
        customer = self.get_customer()

        has_appointments = Appointment.objects.filter(
            customer=customer,
        ).exists()

        if has_appointments:
            messages.error(
                request,
                "Este cliente não pode ser apagado porque já possui marcações associadas.",
            )
            return redirect("appointments:customer_list")

        customer.delete()

        messages.success(
            request,
            "Cliente apagado com sucesso.",
        )

        return redirect("appointments:customer_list")
