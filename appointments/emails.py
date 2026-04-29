from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse

from notifications.services import EmailTemplateService


def generate_secure_link(appointment):
    # Generate a signed appointment access link.
    payload = {
        "reference_code": appointment.reference_code,
        "updated_at": appointment.updated_at.isoformat(),
    }

    token = signing.dumps(payload, salt="appointment-magic-link")

    return reverse(
        "appointments:public_appointment_magic",
        kwargs={"token": token},
    )


def build_full_url(path):
    # Builds an absolute URL for emails.
    site_url = getattr(settings, "SITE_URL", "https://seudominio.com")

    return f"{site_url}{path}"


def send_rendered_email(subject, body_text, body_html, recipient_list):
    # Sends text email with optional HTML alternative.
    email = EmailMultiAlternatives(
        subject=subject,
        body=body_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )

    if body_html:
        email.attach_alternative(body_html, "text/html")

    email.send(fail_silently=False)


def send_appointment_confirmation_email(appointment):
    # Sends appointment creation or confirmation email.
    customer_email = appointment.customer.email

    if not customer_email:
        return

    link = generate_secure_link(appointment)
    full_url = build_full_url(link)

    cancel_path = reverse(
        "appointments:public_cancel_by_code",
        kwargs={
            "reference_code": appointment.reference_code,
        },
    )

    cancel_url = build_full_url(cancel_path)

    is_confirmed = appointment.status == appointment.STATUS_CONFIRMED

    if is_confirmed:
        template_key = "appointment_confirmed"
        fallback_subject = "Confirmação da sua marcação"
        intro = "A sua marcação foi confirmada."
    else:
        template_key = "appointment_created"
        fallback_subject = "Pedido de marcação recebido"
        intro = "Recebemos o seu pedido de marcação. Em breve será confirmado."

    context = {
        "customer_name": appointment.customer.full_name,
        "service_name": appointment.service.name,
        "cancellation_link": cancel_url,
        "appointment_date": appointment.date.strftime("%d/%m/%Y"),
        "appointment_time": appointment.start_time.strftime("%H:%M"),
        "reference_code": appointment.reference_code,
        "magic_link": full_url,
        "intro": intro,
    }

    fallback_body = (
        f"Olá {context['customer_name']},\n\n"
        f"{context['intro']}\n\n"
        f"Serviço: {context['service_name']}\n"
        f"Data: {context['appointment_date']}\n"
        f"Horário: {context['appointment_time']}\n"
        f"Código: {context['reference_code']}\n\n"
        f"Ver detalhes:\n{context['magic_link']}\n\n"
        f"Obrigada,\n"
        f"Priscila Arantes - Enfermeira e Podóloga"
    )

    rendered_email = EmailTemplateService.render(
        template_key=template_key,
        context_data=context,
        fallback_subject=fallback_subject,
        fallback_body=fallback_body,
    )

    send_rendered_email(
        subject=rendered_email["subject"],
        body_text=rendered_email["body_text"],
        body_html=rendered_email["body_html"],
        recipient_list=[customer_email],
    )


def send_appointment_cancelled_email(appointment, cancellation_reason=""):
    # Sends appointment cancellation email.
    customer_email = appointment.customer.email

    if not customer_email:
        return

    context = {
        "customer_name": appointment.customer.full_name,
        "service_name": appointment.service.name,
        "appointment_date": appointment.date.strftime("%d/%m/%Y"),
        "appointment_time": appointment.start_time.strftime("%H:%M"),
        "reference_code": appointment.reference_code,
        "cancellation_reason": cancellation_reason or appointment.cancellation_reason,
    }

    fallback_subject = "Marcação cancelada"

    fallback_body = (
        f"Olá {context['customer_name']},\n\n"
        f"A sua marcação foi cancelada.\n\n"
        f"Serviço: {context['service_name']}\n"
        f"Data: {context['appointment_date']}\n"
        f"Horário: {context['appointment_time']}\n"
        f"Código: {context['reference_code']}\n\n"
        f"Motivo:\n{context['cancellation_reason']}\n\n"
        f"Obrigada,\n"
        f"Priscila Arantes PA"
    )

    rendered_email = EmailTemplateService.render(
        template_key="appointment_cancelled",
        context_data=context,
        fallback_subject=fallback_subject,
        fallback_body=fallback_body,
    )

    send_rendered_email(
        subject=rendered_email["subject"],
        body_text=rendered_email["body_text"],
        body_html=rendered_email["body_html"],
        recipient_list=[customer_email],
    )

def send_appointment_reminder_email(appointment):
    # Sends appointment reminder email.
    customer_email = appointment.customer.email

    if not customer_email:
        return

    link = generate_secure_link(appointment)
    full_url = build_full_url(link)

    cancel_path = reverse(
        "appointments:public_cancel_by_code",
        kwargs={
            "reference_code": appointment.reference_code,
        },
    )

    cancel_url = build_full_url(cancel_path)

    context = {
        "customer_name": appointment.customer.full_name,
        "service_name": appointment.service.name,
        "appointment_date": appointment.date.strftime("%d/%m/%Y"),
        "appointment_time": appointment.start_time.strftime("%H:%M"),
        "reference_code": appointment.reference_code,
        "magic_link": full_url,
        "cancellation_link": cancel_url,
    }

    fallback_subject = "Lembrete da sua marcação"

    fallback_body = (
        f"Olá {context['customer_name']},\n\n"
        f"Este é um lembrete da sua marcação.\n\n"
        f"Serviço: {context['service_name']}\n"
        f"Data: {context['appointment_date']}\n"
        f"Horário: {context['appointment_time']}\n"
        f"Código: {context['reference_code']}\n\n"
        f"Ver detalhes:\n{context['magic_link']}\n\n"
        f"Cancelar marcação:\n{context['cancellation_link']}\n\n"
        f"Obrigada,\n"
        f"Priscila Arantes PA"
    )

    rendered_email = EmailTemplateService.render(
        template_key="appointment_reminder",
        context_data=context,
        fallback_subject=fallback_subject,
        fallback_body=fallback_body,
    )

    send_rendered_email(
        subject=rendered_email["subject"],
        body_text=rendered_email["body_text"],
        body_html=rendered_email["body_html"],
        recipient_list=[customer_email],
    )