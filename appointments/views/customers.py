from django.contrib import messages
from appointments.mixins import ClinicalAccessRequiredMixin, InternalAreaRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

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


class PatientRecordIndexView(ClinicalAccessRequiredMixin, TemplateView):
    """A anamnese sem cliente escolhida: a lista, à espera de um clique.

    O menu tem de abrir alguma coisa, e abrir a ficha da primeira cliente da
    lista seria escolher por quem entrou — e mostrar dados de saúde de alguém
    que ninguém pediu para ver.
    """

    template_name = "appointments/patient_record_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["customers"] = patient_record_sidebar()

        return context


def patient_record_sidebar():
    """As clientes da lista lateral, com o que ela mostra de cada uma.

    `select_related` porque a lista assinala quem tem ficha e quem não tem: sem
    isso, era uma consulta por cliente só para desenhar a barra do lado.
    """

    return Customer.objects.select_related("patient_record").order_by("full_name")


class PatientRecordCreateView(ClinicalAccessRequiredMixin, View):
    """Abre a ficha de anamnese de uma cliente que ainda não tem nenhuma.

    É POST e não uma ligação porque cria um registo de dados de saúde: uma
    ficha não deve nascer por alguém ter passado o rato por cima de um link,
    nem por um browser ter adiantado a página.
    """

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)

        _record, criada = PatientRecord.objects.get_or_create(customer=customer)

        if criada:
            messages.success(
                request,
                f"Ficha de anamnese criada para {customer.full_name}.",
            )

        return redirect("appointments:patient_record", pk=customer.pk)


class PatientRecordUpdateView(ClinicalAccessRequiredMixin, UpdateView):
    """Ficha de anamnese de uma cliente.

    Contém dados de saúde e vive apenas na área interna.

    A ficha já não nasce ao abrir a página. Nascia, e o resultado era que toda
    a gente tinha ficha: bastava alguém ter carregado no ícone uma vez para
    ficar um registo clínico vazio, indistinguível de uma ficha por preencher.
    Quem não tem ficha vê o botão que a cria.
    """

    model = PatientRecord
    form_class = PatientRecordForm
    template_name = "appointments/patient_record_form.html"

    def get_customer(self):
        return get_object_or_404(Customer, pk=self.kwargs["pk"])

    def get_object(self, queryset=None):
        return PatientRecord.objects.filter(customer=self.get_customer()).first()

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        if self.object is None:
            return self.render_to_response(self.contexto_sem_ficha())

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Sem ficha não há formulário na página, portanto isto só acontece a
        # quem submeta o endereço à mão. Volta ao botão de criar.
        if self.object is None:
            return self.render_to_response(self.contexto_sem_ficha())

        return super().post(request, *args, **kwargs)

    def contexto_sem_ficha(self):
        customer = self.get_customer()

        return {
            "customer": customer,
            "customers": patient_record_sidebar(),
            "record_missing": True,
            "clinical_notes": ClinicalNote.objects.filter(
                appointment__customer=customer
            ).select_related("appointment", "appointment__service", "created_by"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        customer = self.object.customer

        context["customer"] = customer
        context["customers"] = patient_record_sidebar()
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
