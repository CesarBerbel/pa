from datetime import time, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from appointments.mixins import (
    ClinicalAccessRequiredMixin,
    InternalAreaRequiredMixin,
    LoginRequiredMixin,
)
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from appointments.audit_services import AppointmentAuditService
from appointments import address_lookup
from appointments.message_preview import ACTION_CONFIRM, build_preview
from appointments import return_services
from appointments.phone_form_field import PhoneField
from appointments.cancellation_services import AppointmentCancellationService
from appointments.forms import (
    AppointmentCancelForm,
    AppointmentForm,
    AppointmentRescheduleForm,
    ClinicalNoteForm,
    ReturnVisitForm,
)
from appointments.models import (
    Appointment,
    AppointmentLog,
    ClinicalNote,
    Customer,
    ReturnVisit,
    Service,
)
from appointments.selectors import AppointmentFilters, AppointmentSelectors
from appointments.use_cases import (
    CompleteAppointmentUseCase,
    ConfirmAppointmentUseCase,
    deliver_confirmation_message,
)
from notifications.whatsapp import WhatsAppAppointmentNotificationService


def warn_schedule_override(request, form):
    """Avisa que a marcação ficou fora do horário normal.

    Encaixar é permitido, mas passar em silêncio esconderia um engano de
    digitação — 19:00 em vez de 09:00 seria aceite sem uma palavra.
    """

    motivo = getattr(form, "schedule_override_reason", None)

    if motivo:
        messages.warning(request, f"Encaixe fora do horário normal. {motivo}")


def group_appointments_by_day(appointments):
    """Junta as marcações em blocos de um dia, pela ordem em que já vinham.

    O agrupamento não reordena nada: um dicionário por ordem de inserção segue
    a ordenação que a lista trouxe. Ordenar os dias por data aqui desfazia a
    escolha de quem pediu a lista por cliente ou por serviço.
    """

    dias = {}

    for appointment in appointments:
        dias.setdefault(appointment.date, []).append(appointment)

    return [
        {"date": data, "appointments": marcacoes} for data, marcacoes in dias.items()
    ]


class AppointmentListView(InternalAreaRequiredMixin, ListView):
    # Lists appointments with filters and ordering.

    model = Appointment
    template_name = "appointments/appointment_list.html"
    context_object_name = "appointments"

    def get_filters(self):
        return AppointmentFilters.from_querydict(self.request.GET)

    def get_queryset(self):
        # Delegate filtering/query composition to the application selector layer.
        return AppointmentSelectors.list_appointments(self.get_filters())

    def get_context_data(self, **kwargs):
        # Add filter options and selected values to the template.
        context = super().get_context_data(**kwargs)

        context["services"] = Service.objects.order_by("name")
        context["status_choices"] = Appointment.STATUS_CHOICES

        context["filters"] = self.get_filters().as_template_context()

        # Os cartões são mostrados por dia. O agrupamento fica aqui e não no
        # template porque `regroup` só junta linhas seguidas, e bastava uma
        # ordenação que não fosse por data para o mesmo dia aparecer partido
        # em vários blocos.
        context["appointment_days"] = group_appointments_by_day(context["appointments"])

        context["today"] = timezone.localdate()

        return context


class AppointmentDetailView(InternalAreaRequiredMixin, DetailView):
    """Tudo o que se sabe de uma marcação, e as ações que agem sobre ela.

    A lista passou a ser de cartões sem botões. Sem um ecrã que reúna os dados
    todos, confirmar ou cancelar era carregar num ícone ao lado de uma linha,
    sem se ver a quem pertencia.
    """

    model = Appointment
    template_name = "appointments/appointment_detail.html"
    context_object_name = "appointment"

    def get_queryset(self):
        return Appointment.objects.select_related(
            "customer",
            "service",
            "created_by",
        )


class AppointmentCreateView(InternalAreaRequiredMixin, CreateView):
    # Creates a new appointment.

    model = Appointment
    form_class = AppointmentForm
    template_name = "appointments/appointment_form.html"
    success_url = reverse_lazy("appointments:appointment_list")

    def get_initial(self):
        # Pre-fill appointment date and time using query params or current local datetime.
        initial = super().get_initial()

        current_datetime = timezone.localtime()

        date = self.request.GET.get("date")
        start_time = self.request.GET.get("start_time")

        if date:
            initial["date"] = date
        else:
            initial["date"] = current_datetime.date().isoformat()

        if start_time:
            initial["start_time"] = start_time
        else:
            initial["start_time"] = current_datetime.strftime("%H:%M")

        # Uma marcação criada aqui já foi combinada com a cliente — ao telefone,
        # no WhatsApp ou ao balcão. Nascia como "Agendada" e obrigava a
        # confirmá-la logo a seguir, num ecrã diferente, para dizer o que já se
        # sabia. O campo continua à mão: uma visita passada, registada depois de
        # acontecer, entra como concluída.
        initial["status"] = Appointment.STATUS_CONFIRMED

        # Vindo da lista de retornos, a cliente e o serviço já estão decididos:
        # o que falta é a hora. Preenchê-los aqui poupa escolhê-los outra vez.
        retorno = self.retorno_pedido()

        if retorno:
            initial["customer"] = retorno.customer_id
            initial["customer_mode"] = AppointmentForm.CUSTOMER_MODE_EXISTING

            if retorno.service_id:
                initial["service"] = retorno.service_id

            if not self.request.GET.get("date"):
                initial["date"] = retorno.target_date.isoformat()

            # A língua acompanha a pessoa: quem foi atendido em inglês da
            # primeira vez não passa a receber português na segunda.
            if retorno.origin_id:
                initial["customer_speaks_english"] = (
                    retorno.origin.customer_speaks_english
                )

        return initial

    def retorno_pedido(self):
        """O retorno que esta marcação vem cumprir, se vier de um."""

        return ReturnVisit.objects.filter(
            pk=self.request.GET.get("retorno") or 0,
            status=ReturnVisit.STATUS_PENDING,
        ).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["retorno"] = self.retorno_pedido()

        return context

    def get_form(self, form_class=None):
        """Vindo de um retorno, a pessoa e o serviço deixam de ser escolhas.

        Já foram decididos quando o retorno foi aberto, e o ecrã mostra-os como
        etiqueta. Mas o campo continua a ir no formulário — escondido — e um
        campo escondido é um campo que se pode trocar por fora.

        Apertar aqui as listas é o que fecha isso: com uma opção só, um valor
        trocado deixa de ser válido e o formulário recusa-o. Não é preciso
        confiar no que vem do browser para o ecrã poder ser simples.
        """

        form = super().get_form(form_class)

        retorno = self.retorno_pedido()

        if retorno:
            form.fields["customer"].queryset = Customer.objects.filter(
                pk=retorno.customer_id
            )

            if retorno.service_id:
                form.fields["service"].queryset = Service.objects.filter(
                    pk=retorno.service_id
                )

        return form

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.origin = Appointment.ORIGIN_INTERNAL

        response = super().form_valid(form)

        # O retorno passa a marcado, com a marcação que o cumpriu. Sem isto, a
        # pessoa ficava na lista de retornos depois de já ter sido marcada.
        retorno = self.retorno_pedido()

        if retorno:
            return_services.attach_appointment(retorno, self.object)

        # Sem isto, uma marcação criada aqui não deixava rasto nenhum: a
        # auditoria começava na primeira alteração, como se a marcação tivesse
        # aparecido sozinha.
        AppointmentAuditService.log(
            appointment=self.object,
            action=AppointmentLog.ACTION_CREATE,
            user=self.request.user,
            description="Marcação criada na área interna.",
            source=AppointmentLog.SOURCE_INTERNAL,
            changes=AppointmentAuditService.creation_changes(self.object),
        )

        messages.success(self.request, self.creation_message(form))
        warn_schedule_override(self.request, form)

        return response

    def creation_message(self, form):
        """O que dizer depois de gravar, conforme a escolha feita na janela.

        Dizer só "criada com sucesso" deixava por saber se a cliente foi
        avisada. Quem marca ao telefone precisa de o saber antes de desligar.
        """

        if not form.cleaned_data.get("send_confirmation"):
            return "Marcação criada. Não foi enviada mensagem à cliente."

        deliver_confirmation_message(self.object)

        if self.object.customer.email:
            return "Marcação criada e confirmação enviada à cliente."

        # Sem email, sobra o WhatsApp — e esse depende das regras de envio
        # estarem ligadas. Prometer o que não se sabe seria pior do que isto.
        return (
            "Marcação criada. A cliente não tem email registado; "
            "a confirmação segue apenas por WhatsApp, se estiver ativo."
        )


class AppointmentUpdateView(InternalAreaRequiredMixin, UpdateView):
    """Remarcar: mudar o serviço, o dia, a hora e o estado de uma marcação.

    Não é uma edição de tudo. A cliente fica onde está — trocá-la seria
    transformar a marcação de uma pessoa na marcação de outra —, e o que se faz
    aqui é o que se faz ao telefone quando alguém não pode vir no dia
    combinado.
    """

    model = Appointment
    form_class = AppointmentRescheduleForm
    template_name = "appointments/appointment_reschedule_form.html"
    success_url = reverse_lazy("appointments:appointment_list")

    def get_initial(self):
        initial = super().get_initial()

        # Quem remarca está a combinar o horário novo com a cliente, ao
        # telefone ou ao balcão: fica confirmado. Uma marcação que voltasse a
        # "Agendada" obrigava a confirmá-la outra vez, noutro ecrã, para dizer
        # o que já se sabia.
        initial["status"] = Appointment.STATUS_CONFIRMED

        return initial

    def dispatch(self, request, *args, **kwargs):
        # Validate access before loading the appointment, otherwise anonymous
        # users could infer appointment state from the redirect and message.
        permission_denied_response = self.get_permission_denied_response()

        if permission_denied_response:
            return permission_denied_response

        # Prevent editing completed appointments even by direct URL access.
        appointment = self.get_object()

        if appointment.status == Appointment.STATUS_COMPLETED:
            messages.error(
                request,
                "Marcações concluídas não podem ser editadas.",
            )
            return redirect("appointments:appointment_list")

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # O retrato tem de ser tirado da base de dados e antes de gravar: o
        # `self.object` já traz os valores novos do formulário, e comparar com
        # ele daria sempre "nada mudou".
        anterior = AppointmentAuditService.snapshot(
            Appointment.objects.select_related("customer", "service").get(
                pk=self.object.pk
            )
        )

        previous_status = Appointment.objects.values_list(
            "status",
            flat=True,
        ).get(pk=self.object.pk)

        response = super().form_valid(form)

        self.object.refresh_from_db()

        alteracoes = AppointmentAuditService.diff(
            anterior,
            AppointmentAuditService.snapshot(self.object),
        )

        AppointmentAuditService.log(
            appointment=self.object,
            action=AppointmentLog.ACTION_UPDATE,
            user=self.request.user,
            description="Marcação alterada na área interna.",
            source=AppointmentLog.SOURCE_INTERNAL,
            changes=alteracoes,
        )

        was_confirmed_now = (
            previous_status != Appointment.STATUS_CONFIRMED
            and self.object.status == Appointment.STATUS_CONFIRMED
        )

        if was_confirmed_now:
            AppointmentAuditService.log(
                appointment=self.object,
                action=AppointmentLog.ACTION_CONFIRM,
                user=self.request.user,
                description="Marcação confirmada ao alterar o estado.",
                source=AppointmentLog.SOURCE_INTERNAL,
            )

            whatsapp_result = WhatsAppAppointmentNotificationService.send_confirmation(
                self.object
            )

            if whatsapp_result.success:
                should_show_whatsapp_message = (
                    not whatsapp_result.skipped or settings.WHATSAPP_CLOUD_API_ENABLED
                )

                if should_show_whatsapp_message:
                    messages.success(
                        self.request,
                        f"Marcação atualizada com sucesso. {whatsapp_result.message}",
                    )
                else:
                    messages.success(
                        self.request,
                        "Marcação atualizada com sucesso.",
                    )
            else:
                messages.warning(
                    self.request,
                    "Marcação atualizada e confirmada, mas não foi possível "
                    f"enviar o WhatsApp: {whatsapp_result.message}",
                )
        else:
            messages.success(self.request, "Marcação atualizada com sucesso.")

        warn_schedule_override(self.request, form)

        return response


def destino_depois_da_marcacao(appointment):
    """Para onde se volta depois de concluir ou cancelar uma marcação.

    Quem chegou a esta marcação a partir dos retornos veio de uma lista de
    telefonemas por fazer, e é a essa lista que precisa de voltar — atirá-la
    para a lista geral de marcações obrigava a procurar o caminho de volta.

    "A partir dos retornos" é qualquer uma das duas pontas: a marcação que
    cumpre um retorno, e a que o gerou. Nos dois casos o assunto em mãos é o
    retorno, não a marcação.
    """

    from appointments.models import ReturnVisit

    ligada = ReturnVisit.objects.filter(
        Q(appointment=appointment) | Q(origin=appointment)
    ).exists()

    if ligada:
        return "appointments:return_visit_list"

    return "appointments:appointment_list"


class AppointmentCancelView(InternalAreaRequiredMixin, UpdateView):
    # Shows an internal cancellation form and cancels an appointment with a required reason.

    model = Appointment
    form_class = AppointmentCancelForm
    template_name = "appointments/appointment_cancel_form.html"
    success_url = reverse_lazy("appointments:appointment_list")

    def get_success_url(self):
        """Cancelar um retorno é um assunto da lista de retornos.

        O destino é decidido no `dispatch` e guardado, e não calculado aqui:
        cancelar solta o retorno da marcação — para a pessoa voltar a ficar por
        marcar — e nessa altura já não há ligação nenhuma para encontrar. Lido
        depois, isto mandava sempre para a lista de marcações.
        """

        return reverse(getattr(self, "destino", "appointments:appointment_list"))

    def get_form_kwargs(self):
        # Remove instance because AppointmentCancelForm is a regular Form, not a ModelForm.
        kwargs = super().get_form_kwargs()
        kwargs.pop("instance", None)
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        # Validate access before loading the appointment, otherwise anonymous
        # users could infer appointment state from the redirect and message.
        permission_denied_response = self.get_permission_denied_response()

        if permission_denied_response:
            return permission_denied_response

        # Prevent opening the cancellation form for appointments that cannot be cancelled.
        appointment = self.get_object()

        # Antes de cancelar, enquanto a ligação ao retorno ainda existe.
        self.destino = destino_depois_da_marcacao(appointment)

        if appointment.status == Appointment.STATUS_CANCELLED:
            messages.warning(
                request,
                "Esta marcação já está cancelada.",
            )
            return redirect("appointments:appointment_list")

        if appointment.status == Appointment.STATUS_COMPLETED:
            messages.error(
                request,
                "Marcações concluídas não podem ser canceladas.",
            )
            return redirect("appointments:appointment_list")

        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        # Pre-fill the reason if the appointment already has one.
        initial = super().get_initial()
        initial["cancellation_reason"] = self.object.cancellation_reason
        return initial

    def form_valid(self, form):
        # Cancel the appointment using centralized business rules.
        appointment = self.get_object()

        result = AppointmentCancellationService.cancel(
            appointment=appointment,
            user=self.request.user,
            cancellation_reason=form.cleaned_data["cancellation_reason"],
            send_message=wants_to_notify(self.request),
        )

        if result.success:
            messages.success(self.request, result.message)

            # `get_success_url` e não `self.success_url`: é ele que sabe se
            # esta marcação veio de um retorno, e a diferença é para onde a
            # pessoa aterra a seguir.
            return redirect(self.get_success_url())

        form.add_error(None, result.message)
        return self.form_invalid(form)


def back_to(request, fallback="appointments:appointment_list"):
    """Para onde voltar depois de agir sobre uma marcação.

    Confirmar a partir do painel devolvia a lista de marcações, o que obrigava
    a voltar atrás para confirmar a seguinte. O destino vem do formulário, mas
    é validado: um `next` que aponte para fora do site é um redirecionamento
    aberto, e esses servem para levar quem clica a uma página que imita esta.
    """

    destino = request.POST.get("next", "")

    if destino and url_has_allowed_host_and_scheme(
        destino,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return destino

    return reverse(fallback)


def wants_to_notify(request):
    """Se a janela de confirmação respondeu que sim.

    Ausente é não. Sem JavaScript o campo vai vazio, e nesse caso a marcação
    muda de estado à mesma — o que se perde é o aviso, nunca o contrário.
    """

    return request.POST.get("send_message") == "1"


class HomeVisitAddressSuggestView(InternalAreaRequiredMixin, View):
    """Moradas sugeridas enquanto se escreve, e a morada escolhida em campos.

    Duas coisas num sítio só porque são a mesma conversa com a Google, e
    porque partilham a sessão que a faz custar uma consulta em vez de uma por
    tecla escrita.

    Fica atrás da área interna de propósito: a chave é do servidor, e um
    endereço aberto ao mundo seria a mesma coisa que a publicar.
    """

    def get(self, request):
        sessao = request.GET.get("sessao", "")
        place_id = request.GET.get("place_id", "")

        if place_id:
            return JsonResponse(address_lookup.details(place_id, session_token=sessao))

        return JsonResponse(
            {
                "suggestions": address_lookup.suggest(
                    request.GET.get("q", ""),
                    session_token=sessao,
                )
            }
        )


class ReturnVisitListView(InternalAreaRequiredMixin, ListView):
    """Os retornos por marcar. É a agenda de telefonemas.

    Sem esta lista, um retorno é uma frase que ninguém volta a ler. Os
    atrasados vêm primeiro porque são os mais antigos, e é essa a ordem por que
    interessa ligar.
    """

    template_name = "appointments/return_visit_list.html"
    context_object_name = "returns"

    def get_queryset(self):
        if self.request.GET.get("estado") == "todos":
            return (
                ReturnVisit.objects.select_related("customer", "service", "appointment")
                .all()
                .order_by("-target_date")
            )

        return return_services.pending()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["late_count"] = return_services.late().count()
        context["pending_count"] = return_services.pending().count()
        context["showing_all"] = self.request.GET.get("estado") == "todos"

        return context


class ReturnVisitNewView(InternalAreaRequiredMixin, CreateView):
    """A porta da frente para abrir um retorno.

    Os outros dois caminhos — a conclusão de um atendimento e o botão da ficha
    da pessoa — servem quem já está no meio de uma coisa. Este serve quem abre
    a lista de retornos porque alguém ligou a pedir revisão, e é o caso que
    não tinha por onde entrar.

    O que se escolhe aqui é **um atendimento**, e é isso que dá o histórico: a
    pessoa e o serviço vêm dele, e a marcação que vier a cumprir o retorno fica
    ligada à consulta que o originou.
    """

    model = ReturnVisit
    form_class = ReturnVisitForm
    template_name = "appointments/return_visit_form.html"
    success_url = reverse_lazy("appointments:return_visit_list")

    def get_initial(self):
        initial = super().get_initial()

        # Vindo do botão de uma marcação, ela já vem escolhida — e com ela a
        # data que o serviço propõe, se propuser alguma.
        origem = self.atendimento_pedido()

        if origem:
            initial["origin"] = origem.pk

            dias = return_services.suggested_days(origem)

            if dias:
                initial["target_date"] = origem.date + timedelta(days=dias)

        return initial

    def atendimento_pedido(self):
        try:
            return Appointment.objects.select_related("service").get(
                pk=self.request.GET.get("atendimento") or 0,
                status=Appointment.STATUS_COMPLETED,
            )
        except (Appointment.DoesNotExist, ValueError):
            return None

    def form_valid(self, form):
        form.instance.created_by = (
            self.request.user if self.request.user.is_authenticated else None
        )

        resposta = super().form_valid(form)

        messages.success(
            self.request,
            f"Retorno de {self.object.customer.full_name} registado. "
            "Fica na lista até ser marcado.",
        )

        return resposta


class ReturnVisitCreateView(InternalAreaRequiredMixin, View):
    """Abre um retorno à mão, a partir da ficha ou do detalhe da marcação.

    É POST porque grava. Serve o caso de quem liga depois a pedir revisão, sem
    ter havido uma conclusão de atendimento pelo meio.
    """

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)

        try:
            dias = int(request.POST.get("dias") or 0)
        except ValueError:
            dias = 0

        if dias <= 0:
            messages.error(request, "Indique dentro de quantos dias a pessoa volta.")

            return redirect(self.destino(request, customer))

        ReturnVisit.objects.create(
            customer=customer,
            service_id=request.POST.get("service") or None,
            target_date=timezone.localdate() + timedelta(days=dias),
            created_by=request.user,
            notes=(request.POST.get("notas") or "").strip(),
        )

        messages.success(
            request,
            f"Retorno de {customer.full_name} registado. Fica na lista até ser marcado.",
        )

        return redirect(self.destino(request, customer))

    def destino(self, request, customer):
        return request.POST.get("next") or reverse("appointments:customer_list")


class ReturnVisitDismissView(InternalAreaRequiredMixin, View):
    """Dispensa um retorno, sem o apagar.

    Apagá-lo perdia a decisão: no mês seguinte ninguém sabia se aquela pessoa
    tinha sido dispensada ou se o retorno nunca chegou a existir.
    """

    def post(self, request, pk):
        retorno = get_object_or_404(ReturnVisit, pk=pk)

        return_services.dismiss(retorno)

        messages.success(
            request,
            f"Retorno de {retorno.customer.full_name} dispensado.",
        )

        return redirect("appointments:return_visit_list")


class NewAppointmentMessagePreviewView(InternalAreaRequiredMixin, View):
    """O que a cliente receberia por uma marcação que ainda não existe.

    A janela de gravar pergunta se a cliente é avisada, e perguntava sem
    mostrar a resposta: nos outros ecrãs há uma marcação gravada para
    pré-visualizar, e aqui a marcação é justamente o que ainda não existe.

    Por isso é montada em memória, com o que está escrito no formulário, e
    nunca chega à base de dados. O cliente novo também não: gravá-lo para poder
    mostrar a mensagem seria registá-lo por alguém ter aberto a janela.
    """

    def post(self, request):
        appointment = self.montar(request.POST)

        if appointment is None:
            return JsonResponse(
                {
                    "emails": [],
                    "whatsapp": [],
                    "notes": [
                        "Escolha o cliente, o serviço e a data para ver a mensagem."
                    ],
                    "is_empty": True,
                }
            )

        preview = build_preview(appointment, action=ACTION_CONFIRM)

        # O código e a ligação nascem ao gravar. Os que aqui aparecem têm a
        # forma certa e não são os que vão sair — dizê-lo é melhor do que
        # mostrar um código em branco ou deixar quem lê a compará-los depois.
        preview.notes.append(
            "O código da marcação e a ligação são criados ao gravar; "
            "na mensagem verdadeira seguem os definitivos."
        )

        return JsonResponse(preview.as_dict())

    def montar(self, dados):
        """A marcação que o formulário está a descrever, sem a gravar."""

        service = Service.objects.filter(pk=dados.get("service") or 0).first()
        customer = self.cliente(dados)

        if not service or not customer:
            return None

        appointment = Appointment(
            customer=customer,
            service=service,
            date=parse_date(dados.get("date") or "") or timezone.localdate(),
            start_time=parse_time(dados.get("start_time") or "") or time(9, 0),
            # Uma marcação criada aqui é combinada na clínica, e o texto que a
            # cliente recebe depende disso: `confirmation_event_for` escolhe
            # entre a resposta a um pedido e o registo do que ficou combinado.
            origin=Appointment.ORIGIN_INTERNAL,
            status=Appointment.STATUS_CONFIRMED,
            is_home_visit=bool(dados.get("is_home_visit")),
            customer_speaks_english=bool(dados.get("customer_speaks_english")),
        )

        for campo in AppointmentForm.CAMPOS_DA_MORADA:
            setattr(appointment, campo, (dados.get(campo) or "").strip())

        if not appointment.is_home_visit:
            for campo in AppointmentForm.CAMPOS_DA_MORADA:
                setattr(appointment, campo, "")

        # A ligação da mensagem é assinada com estes dois. Sem eles, montar a
        # mensagem rebentava — a marcação nunca foi gravada e não tem nem
        # código nem data de alteração.
        appointment.reference_code = appointment.generate_reference_code()
        appointment.updated_at = timezone.now()

        return appointment

    def cliente(self, dados):
        if dados.get("customer_mode") == AppointmentForm.CUSTOMER_MODE_NEW:
            nome = (dados.get("new_customer_name") or "").strip()
            telefone = self.telefone(dados, "new_customer_phone")

            if not nome:
                return None

            # Em memória e sem gravar: o registo do cliente é do formulário, e
            # acontece quando a marcação for mesmo criada.
            return Customer(
                full_name=nome,
                phone=telefone,
                email=(dados.get("new_customer_email") or "").strip(),
            )

        return Customer.objects.filter(pk=dados.get("customer") or 0).first()

    def telefone(self, dados, nome_do_campo):
        """O número que está a ser escrito, pelo mesmo caminho do formulário.

        O telefone tem duas caixas — o indicativo e o número —, e lê-las à mão
        aqui era escrever a mesma regra duas vezes. Uma delas ficaria para trás
        na primeira alteração, que foi exatamente o que aconteceu quando o
        campo deixou de ser uma caixa só: a pré-visualização passou a dizer
        "nenhum número válido para enviar" para uma cliente que tinha o número
        escrito à frente de quem estava a marcar.

        Um número por acabar não é um erro: quem está a meio do formulário vê a
        mensagem sem o WhatsApp, e não uma janela partida.
        """

        campo = PhoneField(required=False)
        partes = campo.widget.value_from_datadict(dados, {}, nome_do_campo)

        try:
            return campo.clean(partes) or ""
        except ValidationError:
            return ""


class AppointmentMessagePreviewView(InternalAreaRequiredMixin, View):
    """O que a cliente receberia, para a janela mostrar antes de decidir.

    É POST e não GET porque o cancelamento precisa do motivo que ainda está a
    ser escrito no formulário — e porque nada disto deve acabar no histórico
    do browser nem em registos de acesso.
    """

    def post(self, request, pk):
        appointment = get_object_or_404(
            Appointment.objects.select_related("customer", "service"), pk=pk
        )

        try:
            preview = build_preview(
                appointment,
                action=request.POST.get("acao", ""),
                cancellation_reason=request.POST.get("cancellation_reason", ""),
            )
        except ValueError:
            return JsonResponse({"error": "Ação desconhecida."}, status=400)

        return JsonResponse(preview.as_dict())


class AppointmentConfirmView(InternalAreaRequiredMixin, View):
    # Confirms an appointment without deleting it.

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        result = ConfirmAppointmentUseCase.execute(
            appointment=appointment,
            user=request.user,
            send_message=wants_to_notify(request),
        )

        if result.success:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)

        return redirect(back_to(request))


class AppointmentCompleteView(InternalAreaRequiredMixin, View):
    # Marks an appointment as completed only if it is confirmed.

    def post(self, request, pk):
        appointment = Appointment.objects.get(pk=pk)

        result = CompleteAppointmentUseCase.execute(
            appointment=appointment,
            user=request.user,
            send_message=wants_to_notify(request),
        )

        if result.success:
            messages.success(request, result.message)
            self.abrir_retorno(request, appointment)
        else:
            messages.error(request, result.message)

        # O `next` do formulário ganha, quando vier: quem conclui a partir do
        # financeiro está a arrumar uma lista, e ser atirado para outro ecrã
        # obriga a voltar atrás para arrumar a seguinte. Sem `next`, vale a
        # regra de sempre — e o `back_to` valida o destino, que um `next` para
        # fora do site é um redirecionamento aberto.
        if request.POST.get("next"):
            return redirect(back_to(request))

        return redirect(destino_depois_da_marcacao(appointment))

    def marcar_retorno(self, request, appointment):
        """Marca já o retorno, com o dia e a hora que foram combinados."""

        data = parse_date(request.POST.get("return_date") or "")
        hora = parse_time(request.POST.get("return_time") or "")

        if not data or not hora:
            messages.error(
                request,
                "O retorno não ficou marcado: faltou a data ou a hora.",
            )

            return

        retorno, aviso = return_services.book_from_appointment(
            appointment,
            data,
            hora,
            user=request.user,
        )

        if aviso:
            # A conclusão já aconteceu quando isto corre, e uma hora ocupada
            # não pode desfazê-la: fica o retorno previsto e diz-se porquê.
            messages.warning(request, aviso)

            return

        messages.info(
            request,
            f"Retorno marcado para {data.strftime('%d/%m/%Y')} "
            f"às {hora.strftime('%H:%M')}.",
        )

    def abrir_retorno(self, request, appointment):
        """Regista o retorno que a janela do "Concluir" pediu.

        É aqui e não noutro sítio porque é o único momento em que quem atende
        sabe se é preciso voltar: acabou de ver o pé. Passada essa janela, o
        retorno passa a depender de alguém se lembrar.

        Três respostas possíveis, e a do meio já existia. A de baixo — marcar
        ali mesmo o dia e a hora — é a que faltava: sem ela, uma data combinada
        com a pessoa à frente virava um "prever" e alguém tinha de a marcar
        outra vez a partir de uma lista.
        """

        modo = (request.POST.get("return_mode") or "").strip()

        # Sem `return_mode` é um formulário anterior a esta alteração — ou um
        # pedido escrito à mão. O que ele traz é o número de dias, e é assim
        # que continua a ser lido.
        if not modo:
            modo = "predicted" if request.POST.get("return_days") else "none"

        if modo == "scheduled":
            self.marcar_retorno(request, appointment)

            return

        if modo != "predicted":
            return

        try:
            dias = int(request.POST.get("return_days") or 0)
        except ValueError:
            dias = 0

        if dias <= 0:
            return

        retorno = return_services.create_from_appointment(
            appointment,
            dias,
            user=request.user,
        )

        if retorno:
            messages.info(
                request,
                (
                    f"Retorno de {appointment.customer.full_name} previsto para "
                    f"{retorno.target_date:%d/%m/%Y}. Fica na lista de retornos "
                    "até ser marcado."
                ),
            )


class CustomerAppointmentsView(LoginRequiredMixin, TemplateView):
    # Shows appointments for the authenticated customer.

    template_name = "appointments/customer_appointments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        customer = getattr(self.request.user, "customer_profile", None)

        context["appointments"] = AppointmentSelectors.customer_appointments(customer)

        return context


class CustomerAppointmentDetailView(LoginRequiredMixin, TemplateView):
    # Shows appointment details for the authenticated customer.

    template_name = "appointments/customer_appointment_detail.html"

    def get_appointment(self):
        customer = getattr(self.request.user, "customer_profile", None)

        if not customer:
            return None

        reference_code = self.kwargs.get("reference_code", "").strip().upper()

        return AppointmentSelectors.customer_appointment_by_reference(
            customer=customer,
            reference_code=reference_code,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["appointment"] = self.get_appointment()
        return context


class ClinicalNoteUpdateView(ClinicalAccessRequiredMixin, UpdateView):
    """Nota de evolução de uma marcação: os atos praticados.

    Criada na primeira abertura, tal como a ficha de anamnese, para não obrigar
    a um passo separado no meio do atendimento.
    """

    model = ClinicalNote
    form_class = ClinicalNoteForm
    template_name = "appointments/clinical_note_form.html"

    def get_appointment(self):
        return get_object_or_404(
            Appointment.objects.select_related("customer", "service"),
            pk=self.kwargs["pk"],
        )

    def get_object(self, queryset=None):
        note, _created = ClinicalNote.objects.get_or_create(
            appointment=self.get_appointment(),
        )

        return note

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["appointment"] = self.object.appointment
        return context

    def form_valid(self, form):
        if not self.object.created_by_id:
            form.instance.created_by = self.request.user

        messages.success(self.request, "Nota de evolução guardada.")

        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "appointments:clinical_note",
            kwargs={"pk": self.object.appointment_id},
        )


class AppointmentAuditView(InternalAreaRequiredMixin, ListView):
    """Histórico do que se passou com as marcações.

    Uma linha por ação, com quem a fez, quando, de onde partiu e o que mudou.
    Serve para responder depois do facto — quem desmarcou esta cliente, a que
    horas estava antes de ser mudada — e por isso é só de leitura: um registo
    que se pode editar não prova nada.
    """

    model = AppointmentLog
    template_name = "appointments/appointment_audit.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        registos = (
            AppointmentLog.objects.select_related(
                "appointment",
                "appointment__customer",
                "appointment__service",
                "performed_by",
            ).all()
            # O `pk` desempata dois registos do mesmo instante, tal como no
            # `Meta` do modelo. Este `order_by` substitui o do modelo, por
            # isso o desempate tem de ser repetido aqui.
            .order_by("-created_at", "-pk")
        )

        acao = self.request.GET.get("action", "").strip()
        origem = self.request.GET.get("source", "").strip()
        pesquisa = self.request.GET.get("q", "").strip()
        utilizador = self.request.GET.get("user", "").strip()

        if acao:
            registos = registos.filter(action=acao)

        if origem:
            registos = registos.filter(source=origem)

        if utilizador:
            registos = registos.filter(performed_by_id=utilizador)

        if pesquisa:
            registos = registos.filter(
                Q(appointment__reference_code__icontains=pesquisa)
                | Q(appointment__customer__full_name__icontains=pesquisa)
                | Q(description__icontains=pesquisa)
            )

        return registos

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["action_choices"] = AppointmentLog.ACTION_CHOICES
        context["source_choices"] = AppointmentLog.SOURCE_CHOICES

        # Só quem realmente aparece no registo. A lista completa de
        # utilizadores encheria o filtro com gente que nunca lá está.
        context["users"] = (
            get_user_model()
            .objects.filter(appointment_logs__isnull=False)
            .distinct()
            .order_by("full_name")
        )

        filtros = {
            "action": self.request.GET.get("action", ""),
            "source": self.request.GET.get("source", ""),
            "user": self.request.GET.get("user", ""),
            "q": self.request.GET.get("q", ""),
        }

        # No telemóvel o painel de filtros está fechado por omissão. O contador
        # é o que impede alguém de ler uma lista filtrada como se fosse o
        # registo todo.
        filtros["active_count"] = len([valor for valor in filtros.values() if valor])

        context["filters"] = filtros

        return context
