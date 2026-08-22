"""Casos antes e depois: a página pública e a gestão na área interna.

A página pública mostra pares de fotografias que se comparam arrastando uma
linha. A gestão é o CRUD do costume, com uma diferença: aqui há ficheiros, e
apagar um caso tem de apagar também as fotografias — senão ficam no disco para
sempre, sem nada que lhes chegue.
"""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from appointments.forms import BeforeAfterCaseForm
from appointments.mixins import InternalAreaRequiredMixin
from notifications.models import BeforeAfterCase


class PublicBeforeAfterView(TemplateView):
    """A galeria, como quem visita o site a vê.

    Só saem quatro de cada vez. Cada caso são duas fotografias, portanto uma
    página com trinta casos seriam sessenta imagens a pedir ao servidor de uma
    assentada — lenta a abrir e cara para quem está com dados móveis.

    O "mostrar mais" é acumulativo — `?mostrar=8` devolve os oito primeiros,
    não os quatro seguintes — para que a ligação funcione como ligação mesmo
    sem JavaScript: quem a seguir sem ele recebe a página com mais quatro, em
    vez de perder os que já estava a ver.
    """

    template_name = "appointments/public_before_after.html"

    PAGE_SIZE = 4

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        publicados = BeforeAfterCase.objects.filter(is_active=True)
        total = publicados.count()
        mostrar = self.quantos_mostrar(total)

        context["cases"] = publicados[:mostrar]
        context["shown"] = mostrar
        context["has_more"] = total > mostrar
        context["next_amount"] = mostrar + self.PAGE_SIZE

        return context

    def quantos_mostrar(self, total):
        """Quantos cabem no que foi pedido, sem confiar no que vem no URL."""

        try:
            pedido = int(self.request.GET.get("mostrar", self.PAGE_SIZE))
        except (TypeError, ValueError):
            pedido = self.PAGE_SIZE

        # Um `?mostrar=100000` não pode virar uma página com tudo lá dentro,
        # e um `?mostrar=-1` não pode virar uma fatia ao contrário.
        return max(self.PAGE_SIZE, min(pedido, total or self.PAGE_SIZE))


class BeforeAfterListView(InternalAreaRequiredMixin, ListView):
    model = BeforeAfterCase
    template_name = "appointments/before_after_list.html"
    context_object_name = "cases"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        todos = BeforeAfterCase.objects.all()

        context["case_total"] = todos.count()
        context["active_case_total"] = todos.filter(is_active=True).count()

        return context


class BeforeAfterCreateView(InternalAreaRequiredMixin, CreateView):
    model = BeforeAfterCase
    form_class = BeforeAfterCaseForm
    template_name = "appointments/before_after_form.html"
    success_url = reverse_lazy("appointments:before_after_list")

    def form_valid(self, form):
        messages.success(self.request, "Caso criado com sucesso.")
        return super().form_valid(form)


class BeforeAfterUpdateView(InternalAreaRequiredMixin, UpdateView):
    model = BeforeAfterCase
    form_class = BeforeAfterCaseForm
    template_name = "appointments/before_after_form.html"
    success_url = reverse_lazy("appointments:before_after_list")

    def form_valid(self, form):
        messages.success(self.request, "Caso atualizado com sucesso.")
        return super().form_valid(form)


class BeforeAfterDeleteView(InternalAreaRequiredMixin, TemplateView):
    template_name = "appointments/before_after_confirm_delete.html"

    def get_case(self):
        return BeforeAfterCase.objects.get(pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["case"] = self.get_case()

        return context

    def post(self, request, pk):
        caso = self.get_case()

        # As fotografias saem com o registo. `delete=False` porque a linha já
        # vai ser apagada a seguir: o que interessa aqui é o ficheiro.
        for imagem in (caso.before_image, caso.after_image):
            if imagem:
                imagem.delete(save=False)

        caso.delete()
        messages.success(request, "Caso apagado com sucesso.")

        return redirect("appointments:before_after_list")
