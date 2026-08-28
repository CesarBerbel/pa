from __future__ import annotations

from dataclasses import dataclass

from django.db import models
from django.utils import timezone

from appointments.availability import AvailabilityService
from appointments.models import Appointment, ScheduleBlock


@dataclass(frozen=True)
class AppointmentFilters:
    q: str = ""
    status: str = ""
    service: str = ""
    date_from: str = ""
    date_to: str = ""
    ordering: str = "date_asc"
    show_all: bool = False

    @classmethod
    def from_querydict(cls, querydict):
        return cls(
            q=querydict.get("q", "").strip(),
            status=querydict.get("status", "").strip(),
            service=querydict.get("service", "").strip(),
            date_from=querydict.get("date_from", "").strip(),
            date_to=querydict.get("date_to", "").strip(),
            ordering=querydict.get("ordering", "date_asc").strip() or "date_asc",
            show_all=querydict.get("all", "").strip() == "1",
        )

    @property
    def limits_to_upcoming(self):
        """Se a lista deve ficar só pelo que ainda está para vir.

        O ecrã de marcações é uma ferramenta de trabalho: o que interessa de
        manhã é o que aí vem, não o arquivo. Mas basta um pedido explícito para
        o limite sair da frente — procurar por um código ou escolher um
        intervalo de datas é dizer que se quer olhar para outra coisa, e
        devolver "nada encontrado" sobre uma marcação que existe seria pior do
        que mostrar histórico a mais.
        """

        if self.show_all:
            return False

        # Pedir as canceladas é pedir para as ver, e a maior parte delas está
        # no passado — quem cancela costuma fazê-lo sobre um dia que entretanto
        # chega e passa. Manter aqui o limite do futuro esvaziava o filtro e
        # dava a entender que não havia nenhuma.
        if self.status == Appointment.STATUS_CANCELLED:
            return False

        return not (self.q or self.date_from or self.date_to)

    @property
    def hides_cancelled(self):
        """As canceladas ficam de fora até alguém as pedir.

        Pedir é filtrar pelo estado, procurar por texto, ou carregar em ver
        tudo. Uma marcação cancelada continua a existir e tem de poder ser
        encontrada quando é ela que se procura.
        """

        if self.show_all:
            return False

        return not (self.q or self.status)

    @property
    def active_count(self):
        """Quantos filtros estão mesmo a mexer no resultado.

        No telemóvel o painel de filtros fica fechado, e um painel fechado
        esconde a razão de a lista estar como está. O número no botão evita
        que se conclua que não há marcações quando o que há é um filtro
        deixado para trás numa pesquisa anterior.
        """

        narrowing = [self.q, self.status, self.service, self.date_from, self.date_to]
        count = len([value for value in narrowing if value])

        if self.show_all:
            count += 1

        # A ordenação não corta resultados, mas troca o topo da lista — que no
        # telemóvel é quase tudo o que se vê.
        if self.ordering != "date_asc":
            count += 1

        return count

    def as_template_context(self):
        return {
            "q": self.q,
            "status": self.status,
            "service": self.service,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "ordering": self.ordering,
            "show_all": self.show_all,
            "limits_to_upcoming": self.limits_to_upcoming,
            "hides_cancelled": self.hides_cancelled,
            "active_count": self.active_count,
        }


class AppointmentSelectors:
    allowed_orderings = {
        "date_asc": ("date", "start_time"),
        "date_desc": ("-date", "-start_time"),
        "customer_asc": ("customer__full_name", "date", "start_time"),
        "customer_desc": ("-customer__full_name", "date", "start_time"),
        "service_asc": ("service__name", "date", "start_time"),
        "service_desc": ("-service__name", "date", "start_time"),
        "status_asc": ("status", "date", "start_time"),
        "status_desc": ("-status", "date", "start_time"),
        "created_desc": ("-created_at",),
        "created_asc": ("created_at",),
    }

    @classmethod
    def list_appointments(cls, filters: AppointmentFilters):
        queryset = Appointment.objects.select_related(
            "customer",
            "service",
            "created_by",
            # O retorno que esta marcação cumpre, para o distintivo da lista.
            # Sem isto era uma consulta por cartão — trinta marcações no ecrã,
            # trinta idas à base de dados para desenhar uma etiqueta.
            "return_visit",
            "return_visit__origin",
        )

        if filters.limits_to_upcoming:
            # Pela data do dia e não pela hora: uma marcação das 09:00 tem de
            # continuar à vista às 11:00, que é quando se vai lá confirmar ou
            # concluir o que já passou hoje.
            queryset = queryset.filter(date__gte=timezone.localdate())

        if filters.hides_cancelled:
            queryset = queryset.exclude(status=Appointment.STATUS_CANCELLED)

        if filters.q:
            queryset = queryset.filter(
                models.Q(reference_code__icontains=filters.q)
                | models.Q(customer__full_name__icontains=filters.q)
                | models.Q(customer__email__icontains=filters.q)
                | models.Q(customer__phone__icontains=filters.q)
                | models.Q(service__name__icontains=filters.q)
            )

        if filters.status:
            queryset = queryset.filter(status=filters.status)

        if filters.service:
            queryset = queryset.filter(service_id=filters.service)

        if filters.date_from:
            queryset = queryset.filter(date__gte=filters.date_from)

        if filters.date_to:
            queryset = queryset.filter(date__lte=filters.date_to)

        return queryset.order_by(
            *cls.allowed_orderings.get(
                filters.ordering, cls.allowed_orderings["date_asc"]
            )
        )

    @staticmethod
    def customer_appointments(customer):
        if not customer:
            return []

        return (
            Appointment.objects.filter(
                customer=customer,
            )
            .select_related(
                "service",
            )
            .order_by("-date", "-start_time")
        )

    @staticmethod
    def customer_appointment_by_reference(customer, reference_code):
        if not customer:
            return None

        return (
            Appointment.objects.filter(
                customer=customer,
                reference_code=reference_code.strip().upper(),
            )
            .select_related(
                "service",
                "customer",
            )
            .first()
        )

    @staticmethod
    def appointments_for_date(selected_date, include_cancelled=True):
        queryset = (
            Appointment.objects.filter(
                date=selected_date,
            )
            .select_related(
                "customer",
                "service",
            )
            .order_by("start_time")
        )

        if not include_cancelled:
            queryset = queryset.exclude(status=Appointment.STATUS_CANCELLED)

        return queryset

    @staticmethod
    def blocks_for_date(selected_date):
        return AvailabilityService.get_active_blocks_for_date(selected_date)


class ScheduleBlockSelectors:
    @staticmethod
    def still_in_effect(today=None):
        """Bloqueios que ainda têm efeito hoje ou a partir de hoje.

        Um bloqueio de um dia só conta enquanto esse dia não passar. Um
        bloqueio que se repete conta enquanto a repetição não terminar — e é
        por isso que a data de início não serve de filtro: o que começou ontem
        e acaba amanhã continua a fechar a agenda hoje.

        Sem data de fim, a repetição não acaba, e o bloqueio conta sempre.
        """

        today = today or timezone.localdate()

        return ScheduleBlock.objects.filter(
            models.Q(is_recurring=False, date__gte=today)
            | (
                models.Q(is_recurring=True)
                & (
                    models.Q(recurrence_end_date__isnull=True)
                    | models.Q(recurrence_end_date__gte=today)
                )
            )
        )
