from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from appointments.forms import ScheduleBlockForm
from appointments.models import ScheduleBlock


class ScheduleBlockListView(LoginRequiredMixin, ListView):
    # Lists schedule blocks

    model = ScheduleBlock
    template_name = "appointments/schedule_block_list.html"
    context_object_name = "blocks"

    def get_queryset(self):
        return ScheduleBlock.objects.order_by(
            "date",
            "start_time",
        )


class ScheduleBlockCreateView(LoginRequiredMixin, CreateView):
    # Creates a new schedule block

    model = ScheduleBlock
    form_class = ScheduleBlockForm
    template_name = "appointments/schedule_block_form.html"
    success_url = reverse_lazy("appointments:schedule_block_list")

    def form_valid(self, form):
        messages.success(self.request, "Bloqueio criado com sucesso.")
        return super().form_valid(form)


class ScheduleBlockUpdateView(LoginRequiredMixin, UpdateView):
    # Updates an existing schedule block

    model = ScheduleBlock
    form_class = ScheduleBlockForm
    template_name = "appointments/schedule_block_form.html"
    success_url = reverse_lazy("appointments:schedule_block_list")

    def form_valid(self, form):
        messages.success(self.request, "Bloqueio atualizado com sucesso.")
        return super().form_valid(form)