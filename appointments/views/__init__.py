from .appointments import (
    AppointmentCancelView,
    AppointmentCompleteView,
    AppointmentConfirmView,
    AppointmentCreateView,
    AppointmentListView,
    AppointmentUpdateView,
    CustomerAppointmentsView,
    CustomerAppointmentDetailView,
)
from .customers import (
    CustomerCreateView,
    CustomerListView,
    CustomerUpdateView,
    CustomerDeleteView,
)
from .diagnostics import ScheduleDiagnosticsView

from .public import (
    PublicAppointmentCreateView,
    PublicAppointmentLookupView,
    PublicAppointmentSuccessView,
    PublicAvailableSlotsView,
    PublicCancelAppointmentByCodeView,
    PublicCancelAppointmentView,
    PublicCancelSuccessView,
    PublicVisualScheduleView,
    PublicAppointmentMagicView,
)
from .schedule_blocks import (
    ScheduleBlockCreateView,
    ScheduleBlockListView,
    ScheduleBlockUpdateView,
    ScheduleBlockDeleteView,
)
from .schedules import (
    DailyAgendaView,
    VisualScheduleView,
)
from .services import (
    ServiceCreateView,
    ServiceListView,
    ServiceUpdateView,
    ServiceDeleteView,
)