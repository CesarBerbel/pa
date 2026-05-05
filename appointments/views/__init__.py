from .appointments import (
    AppointmentCancelView,
    AppointmentCompleteView,
    AppointmentConfirmView,
    AppointmentCreateView,
    AppointmentListView,
    AppointmentUpdateView,
    CustomerAppointmentDetailView,
    CustomerAppointmentsView,
)
from .customers import (
    CustomerCreateView,
    CustomerDeleteView,
    CustomerListView,
    CustomerUpdateView,
)
from .diagnostics import ScheduleDiagnosticsView
from .public import (
    PublicAppointmentCreateView,
    PublicAppointmentLookupView,
    PublicAppointmentMagicView,
    PublicAppointmentSuccessView,
    PublicAvailableSlotsView,
    PublicCancelAppointmentByCodeView,
    PublicCancelAppointmentView,
    PublicCancelSuccessView,
    PublicVisualScheduleView,
)
from .schedule_blocks import (
    ScheduleBlockCreateView,
    ScheduleBlockDeleteView,
    ScheduleBlockListView,
    ScheduleBlockUpdateView,
)
from .schedules import (
    DailyAgendaView,
    VisualScheduleView,
)
from .services import (
    ServiceCreateView,
    ServiceDeleteView,
    ServiceListView,
    ServiceUpdateView,
)

__all__ = [
    "AppointmentCancelView",
    "AppointmentCompleteView",
    "AppointmentConfirmView",
    "AppointmentCreateView",
    "AppointmentListView",
    "AppointmentUpdateView",
    "CustomerAppointmentDetailView",
    "CustomerAppointmentsView",
    "CustomerCreateView",
    "CustomerDeleteView",
    "CustomerListView",
    "CustomerUpdateView",
    "ScheduleDiagnosticsView",
    "PublicAppointmentCreateView",
    "PublicAppointmentLookupView",
    "PublicAppointmentMagicView",
    "PublicAppointmentSuccessView",
    "PublicAvailableSlotsView",
    "PublicCancelAppointmentByCodeView",
    "PublicCancelAppointmentView",
    "PublicCancelSuccessView",
    "PublicVisualScheduleView",
    "ScheduleBlockCreateView",
    "ScheduleBlockDeleteView",
    "ScheduleBlockListView",
    "ScheduleBlockUpdateView",
    "DailyAgendaView",
    "VisualScheduleView",
    "ServiceCreateView",
    "ServiceDeleteView",
    "ServiceListView",
    "ServiceUpdateView",
]
