from django.contrib import messages
from appointments.mixins import ClinicalAccessRequiredMixin, InternalAreaRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from appointments.clinical_services import log_patient_record_change
from appointments.forms import CustomerForm, PatientRecordForm
from appointments.models import Appointment, ClinicalNote, Customer, PatientRecord


class CustomerListView(InternalAreaRequiredMixin, ListView):
    # Lists customers

    model = Customer
    template_name = "appointments/customer_list.html"
    context_object_name = "customers"

    def get_queryset(self):
        # select_related evita uma consulta por cliente ao mostrar o aviso
        # clínico ao lado de cada nome.
        return super().get_queryset().select_related("patient_record")


class PatientRecordUpdateView(ClinicalAccessRequiredMixin, UpdateView):
    """Ficha de anamnese de uma cliente.

    Contém dados de saúde e vive apenas na área interna. A ficha é criada na
    primeira abertura, para não obrigar a um passo separado de "criar ficha".
    """

    model = PatientRecord
    form_class = PatientRecordForm
    template_name = "appointments/patient_record_form.html"

    def get_customer(self):
        return get_object_or_404(Customer, pk=self.kwargs["pk"])

    def get_object(self, queryset=None):
        record, _created = PatientRecord.objects.get_or_create(
            customer=self.get_customer(),
        )

        return record

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        customer = self.object.customer

        context["customer"] = customer
        context["record_logs"] = self.object.logs.select_related("performed_by")[:20]
        context["clinical_notes"] = ClinicalNote.objects.filter(
            appointment__customer=customer
        ).select_related("appointment", "appointment__service", "created_by")

        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user

        response = super().form_valid(form)

        # Depois de guardar, para que o histórico só registe o que ficou de facto
        # gravado.
        log_patient_record_change(
            record=self.object,
            user=self.request.user,
            form=form,
        )

        messages.success(self.request, "Ficha de anamnese guardada.")

        return response

    def get_success_url(self):
        return reverse(
            "appointments:patient_record",
            kwargs={"pk": self.object.customer_id},
        )


class CustomerCreateView(InternalAreaRequiredMixin, CreateView):
    # Creates a new customer

    model = Customer
    form_class = CustomerForm
    template_name = "appointments/customer_form.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente criado com sucesso.")
        return super().form_valid(form)


class CustomerUpdateView(InternalAreaRequiredMixin, UpdateView):
    # Updates an existing customer

    model = Customer
    form_class = CustomerForm
    template_name = "appointments/customer_form.html"
    success_url = reverse_lazy("appointments:customer_list")

    def form_valid(self, form):
        messages.success(self.request, "Cliente atualizado com sucesso.")
        return super().form_valid(form)


class CustomerDeleteView(InternalAreaRequiredMixin, TemplateView):
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
