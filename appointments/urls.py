from django.urls import path

from appointments.views.schedule_blocks import ScheduleBlockDeleteView

from .views import (
    AppointmentCancelView,
    AppointmentCreateView,
    AppointmentListView,
    AppointmentUpdateView,
    CustomerCreateView,
    CustomerListView,
    DailyAgendaView,
    ScheduleBlockCreateView,
    ScheduleBlockListView,
    ScheduleBlockUpdateView,
    ServiceCreateView,
    ServiceListView,
    VisualScheduleView,
    PublicAppointmentCreateView,
    PublicAppointmentSuccessView,
    PublicAvailableSlotsView,
    PublicCancelAppointmentView,
    PublicCancelSuccessView,
    PublicCancelAppointmentByCodeView,
    PublicAppointmentLookupView,
    ScheduleDiagnosticsView,
    PublicVisualScheduleView,
    AppointmentConfirmView,
    AppointmentCompleteView,
    CustomerAppointmentsView,
    CustomerAppointmentDetailView,
    PublicAppointmentMagicView,
    CustomerUpdateView,
    CustomerDeleteView,
    ServiceUpdateView,
    ServiceDeleteView,
    ScheduleBlockDeleteView,
)

app_name = "appointments"

urlpatterns = [
    path("agenda/", DailyAgendaView.as_view(), name="daily_agenda"),
    path("agenda-publica/", PublicVisualScheduleView.as_view(), name="public_visual_schedule"),
    path("agenda/horarios/", VisualScheduleView.as_view(), name="visual_schedule"),

    path("diagnostico/horarios/", ScheduleDiagnosticsView.as_view(), name="schedule_diagnostics"),

    path("bloqueios/", ScheduleBlockListView.as_view(), name="schedule_block_list"),
    path("bloqueios/novo/", ScheduleBlockCreateView.as_view(), name="schedule_block_create"),
    path("bloqueios/<int:pk>/editar/", ScheduleBlockUpdateView.as_view(), name="schedule_block_update"),
    path("bloqueios/<int:pk>/excluir/", ScheduleBlockDeleteView.as_view(), name="schedule_block_delete"),

    path("servicos/", ServiceListView.as_view(), name="service_list"),
    path("servicos/novo/", ServiceCreateView.as_view(), name="service_create"),
    path("servicos/<int:pk>/editar/", ServiceUpdateView.as_view(), name="service_update"),
    path("servicos/<int:pk>/excluir/", ServiceDeleteView.as_view(), name="service_delete"),

    path("clientes/", CustomerListView.as_view(), name="customer_list"),
    path("clientes/novo/", CustomerCreateView.as_view(), name="customer_create"),
    path("clientes/<int:pk>/editar/", CustomerUpdateView.as_view(), name="customer_update"),
    path("clientes/<int:pk>/excluir/", CustomerDeleteView.as_view(), name="customer_delete"),
    path("marcar/", PublicAppointmentCreateView.as_view(), name="public_appointment_create"),
    path("marcar/horarios/", PublicAvailableSlotsView.as_view(), name="public_available_slots"),
    path("marcar/sucesso/", PublicAppointmentSuccessView.as_view(), name="public_appointment_success"),

    path("consultar/", PublicAppointmentLookupView.as_view(), name="public_appointment_lookup"),

    path("cancelar/", PublicCancelAppointmentView.as_view(), name="public_cancel"),
    path("cancelar/sucesso/", PublicCancelSuccessView.as_view(), name="public_cancel_success"),
    path("cancelar/sucesso/<str:reference_code>/", PublicCancelSuccessView.as_view(), name="public_cancel_success_with_code"),
    path("cancelar/<str:reference_code>/", PublicCancelAppointmentByCodeView.as_view(), name="public_cancel_by_code"),

    path("marcacoes/", AppointmentListView.as_view(), name="appointment_list"),
    path("marcacoes/nova/", AppointmentCreateView.as_view(), name="appointment_create"),
    path("marcacoes/<int:pk>/editar/", AppointmentUpdateView.as_view(), name="appointment_update"),
    path("marcacoes/<int:pk>/cancelar/", AppointmentCancelView.as_view(), name="appointment_cancel"),
    path("marcacoes/<int:pk>/confirmar/", AppointmentConfirmView.as_view(), name="appointment_confirm"),
    path("marcacoes/<int:pk>/concluir/", AppointmentCompleteView.as_view(), name="appointment_complete"),

    path("minhas-marcacoes/", CustomerAppointmentsView.as_view(), name="customer_appointments"),
    path("minhas-marcacoes/<str:reference_code>/", CustomerAppointmentDetailView.as_view(), name="customer_appointment_detail"),

    # Cancelamento via código de referência pelo email
    path("m/<str:token>/", PublicAppointmentMagicView.as_view(), name="public_appointment_magic"),  
]