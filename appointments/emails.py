from django.conf import settings
from django.core.mail import send_mail
from django.core import signing
from django.urls import reverse


def generate_secure_link(appointment):
    payload = {
        "reference_code": appointment.reference_code,
        "updated_at": appointment.updated_at.isoformat(),
    }

    token = signing.dumps(payload, salt="appointment-magic-link")

    return reverse(
        "appointments:public_appointment_magic",
        kwargs={"token": token},
    )

def send_appointment_confirmation_email(appointment):
    customer_email = appointment.customer.email

    if not customer_email:
        return
    
    link = generate_secure_link(appointment)
    full_url = f"{settings.SITE_URL}{link}"

    is_confirmed = appointment.status == appointment.STATUS_CONFIRMED

    if is_confirmed:
        subject = "Confirmação da sua marcação"
        intro = "A sua marcação foi confirmada."
    else:
        subject = "Pedido de marcação recebido"
        intro = "Recebemos o seu pedido de marcação. Em breve será confirmado."

    message = (
        f"Olá {appointment.customer.full_name},\n\n"
        f"{intro}\n\n"
        f"Serviço: {appointment.service.name}\n"
        f"Data: {appointment.date.strftime('%d/%m/%Y')}\n"
        f"Horário: {appointment.start_time.strftime('%H:%M')}\n"
        f"Código: {appointment.reference_code}\n\n"
        f"Ver detalhes:\n{full_url}\n\n"
        f"Obrigada,\n"
        f"Priscila Arantes - Enfermeira e Podóloga"
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [customer_email],
        fail_silently=False,
    )


def send_appointment_cancelled_email(appointment):
    customer_email = appointment.customer.email

    if not customer_email:
        return

    subject = "Marcação cancelada"

    message = (
        f"Olá {appointment.customer.full_name},\n\n"
        f"A sua marcação foi cancelada com sucesso.\n\n"
        f"Serviço: {appointment.service.name}\n"
        f"Data: {appointment.date.strftime('%d/%m/%Y')}\n"
        f"Horário: {appointment.start_time.strftime('%H:%M')}\n\n"
        f"Se desejar, poderá realizar uma nova marcação a qualquer momento.\n\n"
        f"Obrigada,\n"
        f"Priscila Arantes PA"
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [customer_email],
        fail_silently=False,
    )    