from .business_hours import (
    BusinessHourCreateView,
    BusinessHourDeleteView,
    BusinessHourListView,
    BusinessHourUpdateView,
)
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
    VisualScheduleBlockView,
    VisualScheduleView,
)
from .services import (
    PublicServiceFeedView,
    ServiceCreateView,
    ServiceDeleteView,
    ServiceListView,
    ServiceUpdateView,
)

__all__ = [
    "BusinessHourUpdateView",
    "BusinessHourListView",
    "BusinessHourDeleteView",
    "BusinessHourCreateView",
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
    "PublicServiceFeedView",
    "ScheduleBlockCreateView",
    "ScheduleBlockDeleteView",
    "ScheduleBlockListView",
    "ScheduleBlockUpdateView",
    "DailyAgendaView",
    "VisualScheduleBlockView",
    "VisualScheduleView",
    "ServiceCreateView",
    "ServiceDeleteView",
    "ServiceListView",
    "ServiceUpdateView",
]
