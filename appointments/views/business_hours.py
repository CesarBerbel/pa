from django.contrib import messages
from appointments.mixins import InternalAreaRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from appointments.forms import BusinessHourForm
from appointments.models import BusinessHour


class BusinessHourListView(InternalAreaRequiredMixin, ListView):
    # Lists registered working hours.

    model = BusinessHour
    template_name = "appointments/business_hour_list.html"
    context_object_name = "business_hours"

    def get_queryset(self):
        # Return working hours ordered by weekday.
        return BusinessHour.objects.order_by("weekday")


class BusinessHourCreateView(InternalAreaRequiredMixin, CreateView):
    # Creates a new working hour entry.

    model = BusinessHour
    form_class = BusinessHourForm
    template_name = "appointments/business_hour_form.html"
    success_url = reverse_lazy("appointments:business_hour_list")

    def form_valid(self, form):
        messages.success(self.request, "Horário trabalhado criado com sucesso.")
        return super().form_valid(form)


class BusinessHourUpdateView(InternalAreaRequiredMixin, UpdateView):
    # Updates an existing working hour entry.

    model = BusinessHour
    form_class = BusinessHourForm
    template_name = "appointments/business_hour_form.html"
    success_url = reverse_lazy("appointments:business_hour_list")

    def form_valid(self, form):
        messages.success(self.request, "Horário trabalhado atualizado com sucesso.")
        return super().form_valid(form)


class BusinessHourDeleteView(InternalAreaRequiredMixin, TemplateView):
    # Shows delete confirmation on GET and deletes working hour on POST.

    template_name = "appointments/business_hour_confirm_delete.html"

    def get_business_hour(self):
        # Get working hour by primary key.
        return BusinessHour.objects.get(pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        # Send working hour data to the confirmation template.
        context = super().get_context_data(**kwargs)
        context["business_hour"] = self.get_business_hour()
        return context

    def post(self, request, pk):
        # Delete working hour only after POST confirmation.
        business_hour = self.get_business_hour()
        weekday_name = business_hour.get_weekday_display()

        business_hour.delete()

        messages.success(
            request,
            f"Horário trabalhado de {weekday_name} apagado com sucesso.",
        )

        return redirect("appointments:business_hour_list")
