from django.contrib import messages
from appointments.mixins import SuperuserRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from appointments.forms import ScheduleBlockForm
from appointments.models import ScheduleBlock


class ScheduleBlockListView(SuperuserRequiredMixin, ListView):
    # Lists schedule blocks.

    model = ScheduleBlock
    template_name = "appointments/schedule_block_list.html"
    context_object_name = "blocks"

    def get_queryset(self):
        # Keep schedule blocks ordered by date and start time.
        return ScheduleBlock.objects.order_by(
            "date",
            "start_time",
        )


class ScheduleBlockCreateView(SuperuserRequiredMixin, CreateView):
    # Creates a new schedule block.

    model = ScheduleBlock
    form_class = ScheduleBlockForm
    template_name = "appointments/schedule_block_form.html"
    success_url = reverse_lazy("appointments:schedule_block_list")

    def form_valid(self, form):
        messages.success(self.request, "Bloqueio criado com sucesso.")
        return super().form_valid(form)


class ScheduleBlockUpdateView(SuperuserRequiredMixin, UpdateView):
    # Updates an existing schedule block.

    model = ScheduleBlock
    form_class = ScheduleBlockForm
    template_name = "appointments/schedule_block_form.html"
    success_url = reverse_lazy("appointments:schedule_block_list")

    def form_valid(self, form):
        messages.success(self.request, "Bloqueio atualizado com sucesso.")
        return super().form_valid(form)


class ScheduleBlockDeleteView(SuperuserRequiredMixin, DeleteView):
    # Deletes an existing schedule block.

    model = ScheduleBlock
    template_name = "appointments/schedule_block_confirm_delete.html"
    success_url = reverse_lazy("appointments:schedule_block_list")

    def form_valid(self, form):
        messages.success(self.request, "Bloqueio excluído com sucesso.")
        return super().form_valid(form)