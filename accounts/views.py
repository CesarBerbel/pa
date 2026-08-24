import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View
from django.contrib.auth.views import LoginView, LogoutView

from accounts import passkey_services
from django.urls import reverse_lazy
from django.views.generic import TemplateView
from appointments.mixins import InternalAreaRequiredMixin
from appointments.models import Appointment, Customer
from .forms import EmailAuthenticationForm, CustomerSignupForm
from django.views.generic import CreateView
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect

from .services import CustomerSignupService
from datetime import timedelta
from decimal import Decimal
from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce


class UserLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("home")


class CustomerSignupView(CreateView):
    form_class = CustomerSignupForm
    template_name = "accounts/customer_signup.html"

    def get_initial(self):
        initial = super().get_initial()

        initial["full_name"] = self.request.GET.get("name", "")
        initial["phone"] = self.request.GET.get("phone", "")
        initial["email"] = self.request.GET.get("email", "")

        return initial

    def form_valid(self, form):
        service_id = self.request.GET.get("service")
        date_value = self.request.GET.get("date")
        start_time_value = self.request.GET.get("start_time")

        try:
            result = CustomerSignupService.signup(
                form=form,
                service_id=service_id,
                date_value=date_value,
                start_time_value=start_time_value,
            )

            # O backend vai explícito porque há mais do que um configurado
            # (o do axes, que só vigia, e o do Django, que autentica): sem ele
            # o `login()` recusa-se a escolher. Aqui a conta acabou de ser
            # criada e não passou por `authenticate()` nenhum, por isso não há
            # backend guardado no utilizador para o `login()` reaproveitar.
            login(
                self.request,
                result.user,
                backend="django.contrib.auth.backends.ModelBackend",
            )

            if result.appointment:
                self.request.session["last_reference_code"] = (
                    result.appointment.reference_code
                )
                return redirect("appointments:public_appointment_success")

        except Exception:
            messages.error(
                self.request,
                "Não foi possível concluir a marcação. Escolha outro horário na agenda.",
            )
            return redirect("appointments:public_visual_schedule")

        return redirect("appointments:public_visual_schedule")


class DashboardView(InternalAreaRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    # O painel é para agir, não para arquivar: passando disto, o caminho é a
    # lista de marcações, que filtra e pagina.
    pending_confirmations_shown = 8

    def get_percentage(self, part, total):
        if not total:
            return 0

        return round((part / total) * 100, 1)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        month_start = today.replace(day=1)
        next_month_start = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12
            else month_start.replace(month=month_start.month + 1)
        )

        today_appointments = Appointment.objects.filter(date=today)
        month_appointments = Appointment.objects.filter(
            date__gte=month_start,
            date__lt=next_month_start,
        )

        month_total = month_appointments.count()
        month_cancelled = month_appointments.filter(
            status=Appointment.STATUS_CANCELLED
        ).count()

        context["metrics"] = {
            "today_total": today_appointments.count(),
            "today_scheduled": today_appointments.filter(
                status=Appointment.STATUS_SCHEDULED
            ).count(),
            "today_confirmed": today_appointments.filter(
                status=Appointment.STATUS_CONFIRMED
            ).count(),
            "today_completed": today_appointments.filter(
                status=Appointment.STATUS_COMPLETED
            ).count(),
            "today_cancelled": today_appointments.filter(
                status=Appointment.STATUS_CANCELLED
            ).count(),
            "tomorrow_total": Appointment.objects.filter(date=tomorrow).count(),
            "month_total": month_total,
            "month_completed": month_appointments.filter(
                status=Appointment.STATUS_COMPLETED
            ).count(),
            "month_cancelled": month_cancelled,
            "month_cancellation_rate": self.get_percentage(
                month_cancelled, month_total
            ),
            "month_revenue": month_appointments.filter(
                status=Appointment.STATUS_COMPLETED
            ).aggregate(
                total=Coalesce(
                    Sum("service__price"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )[
                "total"
            ],
            "customers_total": Customer.objects.count(),
            "customers_with_email": Customer.objects.exclude(email="").count(),
            "reminders_today_total": 0,
            "reminders_today_success": 0,
            "reminders_today_error": 0,
            "reminders_24h_today": 0,
            "reminders_2h_today": 0,
        }

        por_confirmar = (
            Appointment.objects.filter(
                status=Appointment.STATUS_SCHEDULED,
                # A partir de hoje: uma marcação cujo dia já passou não se
                # confirma, cancela-se. Mostrá-la aqui punha ao lado do botão
                # de confirmar uma coisa que já não se confirma.
                date__gte=today,
            )
            .select_related("customer", "service")
            .order_by("date", "start_time")
        )

        context["pending_confirmations_total"] = por_confirmar.count()
        context["pending_confirmations"] = por_confirmar[
            : self.pending_confirmations_shown
        ]

        return context


class PasskeyDeviceListView(LoginRequiredMixin, TemplateView):
    """Dispositivos registados para entrar com biometria."""

    template_name = "accounts/passkey_devices.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["credentials"] = self.request.user.webauthn_credentials.all()
        context["canonical_host"] = passkey_services.get_rp_id()
        context["host_matches"] = passkey_services.host_matches_canonical_domain(
            self.request
        )

        return context


class PasskeyRegisterOptionsView(LoginRequiredMixin, View):
    def post(self, request):
        if not passkey_services.host_matches_canonical_domain(request):
            return JsonResponse(
                {
                    "error": (
                        "Abra o site em "
                        f"{passkey_services.get_rp_id()} para registar o dispositivo."
                    )
                },
                status=400,
            )

        return HttpResponse(
            passkey_services.build_registration_options(request, request.user),
            content_type="application/json",
        )


class PasskeyRegisterVerifyView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Pedido inválido."}, status=400)

        result = passkey_services.complete_registration(
            request=request,
            user=request.user,
            credential=payload.get("credential"),
            device_name=payload.get("name", ""),
        )

        if not result.success:
            return JsonResponse({"error": result.message}, status=400)

        return JsonResponse({"message": result.message})


class PasskeyAuthOptionsView(View):
    # Sem login: é este o passo que antecede a autenticação.

    def post(self, request):
        return HttpResponse(
            passkey_services.build_authentication_options(request),
            content_type="application/json",
        )


class PasskeyAuthVerifyView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Pedido inválido."}, status=400)

        result = passkey_services.complete_authentication(
            request=request,
            credential=payload.get("credential"),
        )

        if not result.success:
            return JsonResponse({"error": result.message}, status=400)

        login(
            request,
            result.user,
            backend="django.contrib.auth.backends.ModelBackend",
        )

        destino = (
            reverse("dashboard")
            if result.user.has_internal_access
            else reverse("appointments:customer_appointments")
        )

        return JsonResponse({"redirect_url": destino})


class PasskeyDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        # Filtrado pelo utilizador: ninguém remove o dispositivo de outra pessoa.
        removidos, _ = request.user.webauthn_credentials.filter(pk=pk).delete()

        if removidos:
            messages.success(request, "Dispositivo removido.")
        else:
            messages.error(request, "Dispositivo não encontrado.")

        return redirect("accounts:passkey_devices")
