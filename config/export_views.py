"""O ecrã de exportação.

Duas coisas só: uma página que diz o que vai sair e um botão que o faz sair.

O botão é um POST e não um link. Um link põe o endereço no histórico do
browser, no `Referer` da página seguinte e nos registos de qualquer coisa pelo
meio — e este endereço devolve a lista de clientes toda. Um formulário com
`csrf_token` também impede que outro site o dispare por nós, que num pedido
que descarrega dados pessoais é a diferença que interessa.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.views.generic import TemplateView

from appointments.mixins import InternalAreaRequiredMixin
from appointments.models import (
    Appointment,
    ClinicalNote,
    Customer,
    PatientRecord,
    ReturnVisit,
    Service,
)
from config import data_export
from finance.models import Expense, Payment


class DataExportView(InternalAreaRequiredMixin, TemplateView):
    """Exportar tudo para levar para outro sistema.

    Fica na área interna e não no admin do Django porque é uma decisão de
    quem gere a casa — mudar de software, dar os dados à contabilista — e não
    uma operação técnica.
    """

    template_name = "config/data_export.html"

    def clinico(self):
        """Se esta pessoa pode levar as fichas clínicas.

        Lido do utilizador e nunca do formulário. Se viesse do formulário, o
        pedido é que decidia o que podia ver — e um pedido escreve-se à mão.
        """

        return self.request.user.has_clinical_access

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["pode_levar_clinicos"] = self.clinico()

        # Contado antes e mostrado na página: quem exporta quer saber o que
        # espera encontrar lá dentro, e um zip com zero linhas por causa de um
        # filtro esquecido é indistinguível de um zip correto até se abrir.
        context["contagens"] = [
            ("Clientes", Customer.objects.count()),
            ("Serviços", Service.objects.count()),
            ("Marcações", Appointment.objects.count()),
            ("Retornos", ReturnVisit.objects.count()),
            ("Pagamentos", Payment.objects.count()),
            ("Despesas", Expense.objects.count()),
        ]

        if self.clinico():
            context["contagens_clinicas"] = [
                ("Fichas clínicas", PatientRecord.objects.count()),
                ("Notas de evolução", ClinicalNote.objects.count()),
            ]

        context["ficheiros"] = [
            nome for nome, _, _ in data_export.tabelas_para(self.clinico())
        ]

        return context

    def post(self, request, *args, **kwargs):
        # A caixa só conta se esta pessoa puder mesmo levar dados clínicos: o
        # `and` é a verificação, o `checked` do formulário é só a vontade.
        clinico = self.clinico() and bool(request.POST.get("incluir_clinicos"))

        conteudo = data_export.construir(clinico=clinico)

        data_export.registar(request.user, clinico)

        resposta = HttpResponse(conteudo, content_type="application/zip")

        resposta["Content-Disposition"] = (
            f'attachment; filename="{data_export.nome_do_ficheiro()}"'
        )

        # Um ficheiro com dados pessoais não fica em cache de lado nenhum —
        # nem no browser, nem num intermediário.
        resposta["Cache-Control"] = "no-store"

        return resposta
