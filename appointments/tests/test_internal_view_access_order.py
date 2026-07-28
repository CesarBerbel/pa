from datetime import date, time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.urls import reverse

from appointments.models import Appointment, BusinessHour, Customer
from appointments.tests.factories import create_test_service
from appointments.views.appointments import AppointmentCancelView, AppointmentUpdateView


class InternalViewAccessOrderTests(TestCase):
    # Internal views that inspect the appointment inside dispatch() must run the
    # access check first. Otherwise an anonymous request receives a redirect that
    # depends on the appointment status, leaking whether it exists and its state.

    def setUp(self):
        User = get_user_model()

        self.factory = RequestFactory()

        self.admin_user = User.objects.create_superuser(
            email="admin@test.com",
            password="testpass123",
            full_name="Admin User",
        )

        self.customer = Customer.objects.create(
            full_name="Cliente Teste",
            email="cliente@test.com",
            phone="+351917777777",
        )

        self.service = create_test_service()

        self.appointment_date = date(2026, 5, 4)

        BusinessHour.objects.update_or_create(
            weekday=self.appointment_date.weekday(),
            defaults={
                "start_time": time(9, 0),
                "end_time": time(18, 0),
                "is_active": True,
            },
        )

        self.completed_appointment = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.appointment_date,
            start_time=time(10, 0),
            status=Appointment.STATUS_COMPLETED,
        )

        self.cancelled_appointment = Appointment.objects.create(
            customer=self.customer,
            service=self.service,
            created_by=self.admin_user,
            date=self.appointment_date,
            start_time=time(12, 0),
            status=Appointment.STATUS_CANCELLED,
        )

    def build_request(self, path, user):
        request = self.factory.get(path)
        request.user = user
        request.session = SessionStore()
        request._messages = FallbackStorage(request)

        return request

    def test_anonymous_update_of_completed_appointment_redirects_to_home(self):
        request = self.build_request("/marcacoes/1/editar/", AnonymousUser())

        response = AppointmentUpdateView.as_view()(
            request,
            pk=self.completed_appointment.pk,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertEqual(len(request._messages), 0)

    def test_anonymous_cancel_of_cancelled_appointment_redirects_to_home(self):
        request = self.build_request("/marcacoes/1/cancelar/", AnonymousUser())

        response = AppointmentCancelView.as_view()(
            request,
            pk=self.cancelled_appointment.pk,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertEqual(len(request._messages), 0)

    def test_non_superuser_update_of_completed_appointment_redirects_to_home(self):
        normal_user = get_user_model().objects.create_user(
            email="cliente@test.com",
            password="testpass123",
            full_name="Cliente User",
        )

        request = self.build_request("/marcacoes/1/editar/", normal_user)

        response = AppointmentUpdateView.as_view()(
            request,
            pk=self.completed_appointment.pk,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertEqual(len(request._messages), 0)

    def test_superuser_update_of_completed_appointment_still_blocked_with_message(self):
        request = self.build_request("/marcacoes/1/editar/", self.admin_user)

        response = AppointmentUpdateView.as_view()(
            request,
            pk=self.completed_appointment.pk,
        )

        messages = [str(message) for message in request._messages]

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("appointments:appointment_list"))
        self.assertIn("Marcações concluídas não podem ser editadas.", messages)

    def test_superuser_cancel_of_cancelled_appointment_still_blocked_with_message(self):
        request = self.build_request("/marcacoes/1/cancelar/", self.admin_user)

        response = AppointmentCancelView.as_view()(
            request,
            pk=self.cancelled_appointment.pk,
        )

        messages = [str(message) for message in request._messages]

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("appointments:appointment_list"))
        self.assertIn("Esta marcação já está cancelada.", messages)
