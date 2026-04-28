from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from appointments.forms import ServiceForm
from appointments.models import Service


class ServiceListView(LoginRequiredMixin, ListView):
    # Lists available services

    model = Service
    template_name = "appointments/service_list.html"
    context_object_name = "services"


class ServiceCreateView(LoginRequiredMixin, CreateView):
    # Creates a new service

    model = Service
    form_class = ServiceForm
    template_name = "appointments/service_form.html"
    success_url = reverse_lazy("appointments:service_list")

    def form_valid(self, form):
        messages.success(self.request, "Serviço criado com sucesso.")
        return super().form_valid(form)