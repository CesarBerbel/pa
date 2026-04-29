from django.contrib import messages
from django.db.models import ProtectedError
from appointments.mixins import SuperuserRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from appointments.forms import ServiceForm
from appointments.models import Service


class ServiceListView(SuperuserRequiredMixin, ListView):
    # Lists available services.

    model = Service
    template_name = "appointments/service_list.html"
    context_object_name = "services"


class ServiceCreateView(SuperuserRequiredMixin, CreateView):
    # Creates a new service.

    model = Service
    form_class = ServiceForm
    template_name = "appointments/service_form.html"
    success_url = reverse_lazy("appointments:service_list")

    def form_valid(self, form):
        messages.success(self.request, "Serviço criado com sucesso.")
        return super().form_valid(form)


class ServiceUpdateView(SuperuserRequiredMixin, UpdateView):
    # Updates an existing service.

    model = Service
    form_class = ServiceForm
    template_name = "appointments/service_form.html"
    success_url = reverse_lazy("appointments:service_list")

    def form_valid(self, form):
        messages.success(self.request, "Serviço atualizado com sucesso.")
        return super().form_valid(form)


class ServiceDeleteView(SuperuserRequiredMixin, DeleteView):
    # Deletes a service only when there are no protected related appointments.

    model = Service
    template_name = "appointments/service_confirm_delete.html"
    success_url = reverse_lazy("appointments:service_list")

    def form_valid(self, form):
        # Protect appointment history by handling protected foreign key errors gracefully.
        try:
            response = super().form_valid(form)
            messages.success(self.request, "Serviço excluído com sucesso.")
            return response
        except ProtectedError:
            messages.error(
                self.request,
                "Este serviço não pode ser excluído porque possui marcações vinculadas. "
                "Para preservar o histórico, desative o serviço em vez de excluí-lo.",
            )
            return redirect("appointments:service_list")