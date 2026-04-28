from .appointments import (
    AppointmentCancelView,
    AppointmentCompleteView,
    AppointmentConfirmView,
    AppointmentCreateView,
    AppointmentListView,
    AppointmentUpdateView,
)
from .customers import (
    CustomerCreateView,
    CustomerListView,
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
)
from .schedule_blocks import (
    ScheduleBlockCreateView,
    ScheduleBlockListView,
    ScheduleBlockUpdateView,
)
from .schedules import (
    DailyAgendaView,
    VisualScheduleView,
)
from .services import (
    ServiceCreateView,
    ServiceListView,
)