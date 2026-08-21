"""O que a cliente receberia se a ação fosse mesmo para a frente.

A janela que pergunta "avisar a cliente?" mostrava a pergunta sem mostrar a
resposta: quem decidia não via o que ia sair. Uma frase escrita à mão a
descrever a mensagem resolvia o ecrã e mentia à primeira vez que alguém
editasse um modelo.

Por isso isto não descreve a mensagem — **produz-a**, pelo mesmo caminho do
envio a sério. Os emails passam pelas mesmas funções de envio, com a entrega
desviada para uma lista; o WhatsApp percorre as mesmas regras e pede aos mesmos
fornecedores o texto que construiriam. A única coisa que não acontece é a
chamada final.

O estado é o outro pormenor que faz diferença: o texto de uma confirmação
depende de a marcação estar confirmada, e no momento da pré-visualização ela
ainda não está. Aqui a marcação é posta, em memória e sem gravar, no estado em
que vai ficar — senão a pré-visualização mostrava o email errado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from appointments.emails import (
    capture_emails,
    send_appointment_cancelled_email,
    send_appointment_completed_email,
    send_appointment_confirmation_email,
    send_professional_notification_email,
)
from appointments.models import Appointment
from appointments.use_cases import confirmation_event_for
from notifications import whatsapp_dispatch
from notifications.models import EmailEventSetting, WhatsAppEventSetting

ACTION_CONFIRM = "confirm"
ACTION_COMPLETE = "complete"
ACTION_CANCEL = "cancel"

ACTIONS = (ACTION_CONFIRM, ACTION_COMPLETE, ACTION_CANCEL)


@dataclass
class MessagePreview:
    emails: list = field(default_factory=list)
    whatsapp: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def is_empty(self):
        return not self.emails and not self.whatsapp

    def as_dict(self):
        return {
            "emails": self.emails,
            "whatsapp": self.whatsapp,
            "notes": self.notes,
            "is_empty": self.is_empty,
        }


def _emails_da_confirmacao(appointment):
    send_appointment_confirmation_email(appointment)


def _emails_da_conclusao(appointment):
    from notifications.followup_services import completion_messages_for

    proprias = list(completion_messages_for(appointment))

    if not proprias:
        send_appointment_completed_email(appointment)
        return

    # As mensagens do serviço substituem o agradecimento comum, e é o
    # `send_followup` que decide o modelo — mas esse também grava o registo de
    # envio, que numa pré-visualização não pode acontecer.
    from appointments.emails import send_service_followup_email

    for mensagem in proprias:
        try:
            send_service_followup_email(appointment=appointment, followup=mensagem)
        except ValueError:
            # Modelo inativo. No envio a sério isto fica registado como erro;
            # aqui basta não mostrar uma mensagem que não vai sair.
            continue


def _emails_do_cancelamento(appointment, cancellation_reason):
    send_appointment_cancelled_email(
        appointment=appointment,
        cancellation_reason=cancellation_reason,
    )

    send_professional_notification_email(
        appointment,
        EmailEventSetting.EVENT_APPOINTMENT_CANCELLED,
        "appointment_cancelled_professional",
    )


def build_preview(appointment, action, cancellation_reason=""):
    """As mensagens que esta ação faria sair, sem fazer sair nenhuma."""

    if action not in ACTIONS:
        raise ValueError(f"Ação desconhecida: {action}")

    preview = MessagePreview()

    if action == ACTION_CONFIRM:
        appointment.status = Appointment.STATUS_CONFIRMED
        evento_whatsapp = confirmation_event_for(appointment)
    elif action == ACTION_COMPLETE:
        appointment.status = Appointment.STATUS_COMPLETED
        evento_whatsapp = WhatsAppEventSetting.EVENT_APPOINTMENT_COMPLETED
    else:
        appointment.status = Appointment.STATUS_CANCELLED
        appointment.cancellation_reason = cancellation_reason
        evento_whatsapp = WhatsAppEventSetting.EVENT_APPOINTMENT_CANCELLED

    with capture_emails() as recolhidos:
        if action == ACTION_CONFIRM:
            _emails_da_confirmacao(appointment)
        elif action == ACTION_COMPLETE:
            _emails_da_conclusao(appointment)
        else:
            _emails_do_cancelamento(appointment, cancellation_reason)

    preview.emails = recolhidos

    from notifications.models import MessagingSetting

    if not MessagingSetting.emails_enabled():
        preview.notes.append("O envio de emails está desligado nas configurações.")
        preview.emails = []
    elif not preview.emails and not appointment.customer.email:
        preview.notes.append("A cliente não tem email registado.")

    preview.whatsapp, avisos = whatsapp_dispatch.preview(appointment, evento_whatsapp)
    preview.notes.extend(avisos)

    return preview
