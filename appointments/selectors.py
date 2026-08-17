from __future__ import annotations

from dataclasses import dataclass

from django.db import models
from django.utils import timezone

from appointments.availability import AvailabilityService
from appointments.models import Appointment


@dataclass(frozen=True)
class AppointmentFilters:
    q: str = ""
    status: str = ""
    service: str = ""
    date_from: str = ""
    date_to: str = ""
    reminder: str = ""
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
            reminder=querydict.get("reminder", "").strip(),
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

    def as_template_context(self):
        return {
            "q": self.q,
            "status": self.status,
            "service": self.service,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "reminder": self.reminder,
            "ordering": self.ordering,
            "show_all": self.show_all,
            "limits_to_upcoming": self.limits_to_upcoming,
            "hides_cancelled": self.hides_cancelled,
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

        if filters.reminder == "24h_sent":
            queryset = queryset.filter(reminder_24h_sent_at__isnull=False)
        elif filters.reminder == "24h_pending":
            queryset = queryset.filter(
                reminder_24h_sent_at__isnull=True,
            ).exclude(
                status__in=[Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED]
            )
        elif filters.reminder == "2h_sent":
            queryset = queryset.filter(reminder_2h_sent_at__isnull=False)
        elif filters.reminder == "2h_pending":
            queryset = queryset.filter(
                reminder_2h_sent_at__isnull=True,
            ).exclude(
                status__in=[Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED]
            )

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
