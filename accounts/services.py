from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from appointments.appointment_services import AppointmentService


@dataclass
class CustomerSignupResult:
    user: object
    customer: object
    appointment: object | None = None


class CustomerSignupService:
    @staticmethod
    def has_appointment_request(service_id, date_value, start_time_value):
        return bool(service_id and date_value and start_time_value)

    @staticmethod
    def signup(form, service_id=None, date_value=None, start_time_value=None):
        with transaction.atomic():
            user = form.save()
            customer = form.customer
            appointment = None

            if CustomerSignupService.has_appointment_request(
                service_id,
                date_value,
                start_time_value,
            ):
                result = AppointmentService.create_public_appointment(
                    customer=customer,
                    service_id=service_id,
                    date_value=date_value,
                    start_time_value=start_time_value,
                    send_email=True,
                )

                if not result.success:
                    raise ValidationError(result.message)

                appointment = result.appointment

            return CustomerSignupResult(
                user=user,
                customer=customer,
                appointment=appointment,
            )
