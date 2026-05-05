from django.contrib import messages
from appointments.mixins import SuperuserRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from appointments.forms import ScheduleBlockForm
from appointments.models import ScheduleBlock


class ScheduleBlockListView(SuperuserRequiredMixin, ListView):
    # Lists schedule blocks.

    model = ScheduleBlock
    template_name = "appointments/schedule_block_list.html"
    context_object_name = "blocks"

    def get_queryset(self):
        # Return schedule blocks ordered by date and start time.
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


class ScheduleBlockDeleteView(SuperuserRequiredMixin, TemplateView):
    # Shows delete confirmation on GET and deletes schedule block on POST.

    template_name = "appointments/schedule_block_confirm_delete.html"

    def get_schedule_block(self):
        # Get schedule block by primary key.
        return ScheduleBlock.objects.get(pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        # Send schedule block data to the confirmation template.
        context = super().get_context_data(**kwargs)
        context["schedule_block"] = self.get_schedule_block()
        return context

    def post(self, request, pk):
        # Delete schedule block only after POST confirmation.
        schedule_block = self.get_schedule_block()

        schedule_block.delete()

        messages.success(
            request,
            "Bloqueio apagado com sucesso.",
        )

        return redirect("appointments:schedule_block_list")
