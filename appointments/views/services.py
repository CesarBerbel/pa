from django.contrib import messages
from appointments.mixins import SuperuserRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from appointments.forms import ServiceForm
from appointments.models import Appointment, Service


class ServiceListView(SuperuserRequiredMixin, ListView):
    # Lists available services

    model = Service
    template_name = "appointments/service_list.html"
    context_object_name = "services"


class ServiceCreateView(SuperuserRequiredMixin, CreateView):
    # Creates a new service

    model = Service
    form_class = ServiceForm
    template_name = "appointments/service_form.html"
    success_url = reverse_lazy("appointments:service_list")

    def form_valid(self, form):
        messages.success(self.request, "Serviço criado com sucesso.")
        return super().form_valid(form)


class ServiceUpdateView(SuperuserRequiredMixin, UpdateView):
    # Updates an existing service

    model = Service
    form_class = ServiceForm
    template_name = "appointments/service_form.html"
    success_url = reverse_lazy("appointments:service_list")

    def form_valid(self, form):
        messages.success(self.request, "Serviço atualizado com sucesso.")
        return super().form_valid(form)


class ServiceDeleteView(SuperuserRequiredMixin, TemplateView):
    # Shows delete confirmation on GET and deletes service on POST

    template_name = "appointments/service_confirm_delete.html"

    def get_service(self):
        # Get service safely by primary key
        return Service.objects.get(pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        # Send service data to confirmation template
        context = super().get_context_data(**kwargs)
        context["service"] = self.get_service()
        return context

    def post(self, request, pk):
        # Delete service only if there are no appointments linked to it
        service = self.get_service()

        has_appointments = Appointment.objects.filter(
            service=service,
        ).exists()

        if has_appointments:
            messages.error(
                request,
                "Este serviço não pode ser apagado porque já possui marcações associadas.",
            )
            return redirect("appointments:service_list")

        service.delete()

        messages.success(
            request,
            "Serviço apagado com sucesso.",
        )

        return redirect("appointments:service_list")