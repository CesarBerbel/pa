"""As mensagens para quem marcou na versão inglesa do site.

Só as que a cliente lê. Os avisos à profissional não estão aqui e não terão
versão inglesa: quem os lê é sempre a mesma pessoa, e fala português.

Um campo inglês vazio não é um erro — é "por traduzir", e nesse caso sai o
português. Por isso este ficheiro pode crescer aos poucos sem partir nada.

O texto não é uma tradução palavra a palavra do português. Uma marcação
confirmada diz-se de outra maneira em inglês, e o que interessa é que a
pessoa perceba o que tem de fazer, não que as duas versões tenham o mesmo
número de linhas.
"""

from notifications.default_email_templates import ROTULOS_EN, _html

RODAPE_EN = "Priscila Arantes — Nurse and Podologist\nCoimbra, Portugal"

MORADA_EN = "Galeria Avenida, Av. Sá da Bandeira 33, Loja 108, 3000-351 Coimbra"


def _html_en(**kwargs):
    return _html(rotulos=ROTULOS_EN, **kwargs)


# Chave do modelo -> a versão inglesa dos três campos.
EMAIL_TEMPLATES_EN = {
    "appointment_created": {
        "subject": "We have received your booking request",
        "body_text": (
            "Hello {{ customer_name }},\n\n"
            "We have received your booking request. We still need to check the "
            "diary: as soon as that is done, you will get a confirmation by "
            "email.\n\n"
            "Service: {{ service_name }}\n"
            "Date: {{ appointment_date }}\n"
            "Time: {{ appointment_time }}\n"
            "Reference: {{ reference_code }}\n\n"
            "You can follow or cancel the request here:\n{{ magic_link }}\n\n"
            "Kind regards,\n"
            f"{RODAPE_EN}"
        ),
        "body_html": _html_en(
            titulo="We have your request",
            saudacao="Hello {{ customer_name }},",
            corpo=(
                "Your booking request has arrived. We still need to check the "
                "diary — as soon as that is done, you will get a confirmation "
                "by email."
            ),
            acao=("Follow the request", "{{ magic_link }}"),
        ),
    },
    "appointment_confirmed": {
        "subject": "Your appointment is confirmed — {{ appointment_date }}",
        "body_text": (
            "Hello {{ customer_name }},\n\n"
            "Your request is confirmed. We look forward to seeing you.\n\n"
            "Service: {{ service_name }}\n"
            "Date: {{ appointment_date }}\n"
            "Time: {{ appointment_time }}\n"
            "Reference: {{ reference_code }}\n\n"
            f"Where: {MORADA_EN}\n\n"
            "See the appointment details:\n{{ magic_link }}\n\n"
            "If you cannot come, please let us know in advance so the slot can "
            "go to someone else:\n{{ cancellation_link }}\n\n"
            "Kind regards,\n"
            f"{RODAPE_EN}"
        ),
        "body_html": _html_en(
            titulo="Your appointment is confirmed",
            saudacao="Hello {{ customer_name }},",
            corpo="Your request is confirmed. We look forward to seeing you.",
            aviso=(
                f"Where: {MORADA_EN}. If you cannot come, please let us know in "
                "advance so the slot can go to someone else."
            ),
            acao=("See the appointment", "{{ magic_link }}"),
        ),
    },
    "appointment_confirmed_internal": {
        "subject": "Your appointment is booked — {{ appointment_date }}",
        "body_text": (
            "Hello {{ customer_name }},\n\n"
            "This is a record of the appointment we arranged. Keep this email "
            "as your confirmation.\n\n"
            "Service: {{ service_name }}\n"
            "Date: {{ appointment_date }}\n"
            "Time: {{ appointment_time }}\n"
            "Reference: {{ reference_code }}\n\n"
            f"Where: {MORADA_EN}\n\n"
            "See the appointment details:\n{{ magic_link }}\n\n"
            "If you need to change or cancel it, just reply to this email or "
            "use this link:\n{{ cancellation_link }}\n\n"
            "Kind regards,\n"
            f"{RODAPE_EN}"
        ),
        "body_html": _html_en(
            titulo="Your appointment is booked",
            saudacao="Hello {{ customer_name }},",
            corpo=(
                "This is a record of the appointment we arranged. Keep this "
                "email as your confirmation."
            ),
            aviso=(
                f"Where: {MORADA_EN}. To change or cancel, reply to this email "
                "or use the link below."
            ),
            acao=("See the appointment", "{{ magic_link }}"),
        ),
    },
    "appointment_cancelled": {
        "subject": "Appointment cancelled — {{ service_name }}",
        "body_text": (
            "Hello {{ customer_name }},\n\n"
            "Your appointment has been cancelled and the slot is free again.\n\n"
            "Service: {{ service_name }}\n"
            "Date: {{ appointment_date }}\n"
            "Time: {{ appointment_time }}\n"
            "Reference: {{ reference_code }}\n"
            "{% if cancellation_reason %}\n"
            "Reason: {{ cancellation_reason }}\n"
            "{% endif %}\n"
            "Whenever you would like to book again, just reply to this email — "
            "we would be glad to see you.\n\n"
            "Kind regards,\n"
            f"{RODAPE_EN}"
        ),
        "body_html": _html_en(
            titulo="Appointment cancelled",
            saudacao="Hello {{ customer_name }},",
            corpo=(
                "Your appointment has been cancelled and the slot is free "
                "again."
            ),
            aviso=(
                "{% if cancellation_reason %}Reason: {{ cancellation_reason }}"
                "{% endif %}"
            ),
            acao=("Book another time", "{{ booking_link }}"),
        ),
    },
    "appointment_completed": {
        "subject": "Thank you for your visit",
        "body_text": (
            "Hello {{ customer_name }},\n\n"
            "Thank you for coming in today. It was a pleasure to see you.\n\n"
            "Service: {{ service_name }}\n"
            "Date: {{ appointment_date }}\n"
            "Reference: {{ reference_code }}\n\n"
            "If anything about the care over the next few days is unclear, "
            "reply to this email — we are glad to help.\n\n"
            "When it is time to come back, you can book here:\n"
            "{{ booking_link }}\n\n"
            "Kind regards,\n"
            f"{RODAPE_EN}"
        ),
        "body_html": _html_en(
            titulo="Thank you for your visit",
            saudacao="Hello {{ customer_name }},",
            corpo=(
                "Thank you for coming in today. If anything about the care "
                "over the next few days is unclear, reply to this email — we "
                "are glad to help."
            ),
            acao=("Book your next visit", "{{ booking_link }}"),
        ),
    },
    "service_followup": {
        "subject": "How have things been since your {{ service_name }}?",
        "body_text": (
            "Hello {{ customer_name }},\n\n"
            "It has been {{ days_after }} days since your {{ service_name }} "
            "on {{ appointment_date }}. We are writing simply to ask how "
            "things have been.\n\n"
            "If you notice pain, redness, swelling or any change that worries "
            "you, reply to this email or get in touch: it is always better to "
            "ask early than to wait.\n\n"
            "When it is time to come back, you can book here:\n"
            "{{ booking_link }}\n\n"
            "Kind regards,\n"
            f"{RODAPE_EN}"
        ),
        "body_html": _html_en(
            titulo="How have things been?",
            saudacao="Hello {{ customer_name }},",
            corpo=(
                "It has been {{ days_after }} days since your "
                "{{ service_name }}. If you notice pain, redness, swelling or "
                "any change that worries you, reply to this email or get in "
                "touch: it is always better to ask early than to wait."
            ),
            detalhes=False,
            acao=("Book your next visit", "{{ booking_link }}"),
        ),
    },
    "service_manual": {
        "subject": "Aftercare for your {{ service_name }}",
        "body_text": (
            "Hello {{ customer_name }},\n\n"
            "Here is the aftercare advice from your {{ service_name }} on "
            "{{ appointment_date }}, written down so you have it to hand.\n\n"
            "General advice:\n"
            "- keep the area clean and dry;\n"
            "- wear comfortable shoes that do not press;\n"
            "- do not remove dressings or scabs before the time you were "
            "given;\n"
            "- if there is pain, heat, redness or pus, contact us.\n\n"
            "This is general advice. If you were given specific instructions "
            "during your appointment, those are the ones that apply.\n\n"
            "Any questions, just reply to this email.\n\n"
            "Kind regards,\n"
            f"{RODAPE_EN}"
        ),
        "body_html": _html_en(
            titulo="Aftercare",
            saudacao="Hello {{ customer_name }},",
            corpo=(
                "Here is the aftercare advice from your {{ service_name }}, "
                "written down so you have it to hand: keep the area clean and "
                "dry, wear comfortable shoes that do not press, do not remove "
                "dressings or scabs before the time you were given, and "
                "contact us if there is pain, heat, redness or pus."
            ),
            detalhes=False,
            aviso=(
                "This is general advice. If you were given specific "
                "instructions during your appointment, those are the ones that "
                "apply."
            ),
        ),
    },
}


# (acontecimento, destinatário) -> o texto do WhatsApp em inglês.
WHATSAPP_MESSAGES_EN = {
    ("appointment_requested", "customer"): (
        "Hello {{ customer_name }}, we have received your booking request for "
        "{{ service_name }} on {{ appointment_date }} at "
        "{{ appointment_time }}. We still need to check the diary — we will "
        "let you know here as soon as it is done. Your reference is "
        "{{ reference_code }} and you can follow or cancel the appointment at "
        "{{ appointment_link }}."
    ),
    ("appointment_confirmed", "customer"): (
        "Hello {{ customer_name }}, your request is confirmed: "
        "{{ service_name }} on {{ appointment_date }} at "
        "{{ appointment_time }}. We will be waiting for you at "
        f"{MORADA_EN}. "
        "Keep the reference {{ reference_code }}; at {{ appointment_link }} "
        "you can check or cancel the appointment. If you cannot come, please "
        "tell us in advance so the slot can go to someone else."
    ),
    ("appointment_confirmed_internal", "customer"): (
        "Hello {{ customer_name }}, your appointment for {{ service_name }} on "
        "{{ appointment_date }} at {{ appointment_time }} is booked, as we "
        f"arranged. We will be waiting for you at {MORADA_EN}. "
        "Keep the reference {{ reference_code }}; at {{ appointment_link }} "
        "you can check or cancel it if you need to."
    ),
    ("appointment_cancelled", "customer"): (
        "Hello {{ customer_name }}, your appointment for {{ service_name }} on "
        "{{ appointment_date }} at {{ appointment_time }} has been cancelled "
        "and the slot is free again. Reason: {{ cancellation_reason }}. The "
        "reference was {{ reference_code }}. Whenever you would like to book "
        "again, choose a time at {{ booking_link }} or reply to this message — "
        "we would be glad to see you."
    ),
    ("appointment_completed", "customer"): (
        "Hello {{ customer_name }}, thank you for your visit. If anything "
        "about the care after your {{ service_name }} is unclear, reply to "
        "this message — we are glad to help. When it is time to come back, you "
        "can choose a time at {{ booking_link }}, whenever suits you."
    ),
}
