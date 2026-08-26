import re

from django.core.exceptions import ValidationError
from django.utils.translation import get_language

from appointments.models import Customer


def normalize_email(email):
    # Normalize email for consistent lookup and storage.
    if not email:
        return ""

    return email.strip().lower()


# Os limites da norma E.164: o número inteiro, indicativo incluído, tem entre
# oito e quinze dígitos. É o que se pode verificar sem uma lista de regras por
# país — que muda todos os meses e que ninguém aqui vai manter. O indicativo,
# esse, vem de uma lista e é sempre real.
MINIMO_DE_DIGITOS = 8
MAXIMO_DE_DIGITOS = 15


def normalize_phone(phone):
    """O número em E.164: `+`, indicativo do país, e o resto.

    É a forma que o WhatsApp espera, e a única em que dois números
    iguais se parecem. Aceita o mundo inteiro: antes, um número que não fosse
    de Portugal nem do Brasil não passava daqui.

    Um número sem indicativo é lido como português — é a clínica onde está, e
    era assim que os números guardados antes disto foram escritos. Quem tem um
    número de outro sítio escolhe o país no formulário, e nesse caso o
    indicativo já vem no que chega aqui.
    """

    if not phone:
        return ""

    texto = phone.strip()
    digitos = re.sub(r"\D", "", texto)

    if not digitos:
        return ""

    # `00` é como se marca o internacional a partir de quase toda a Europa, e é
    # como muita gente escreve o próprio número.
    if not texto.startswith("+") and digitos.startswith("00"):
        digitos = digitos[2:]
        texto = f"+{digitos}"

    if texto.startswith("+"):
        if not MINIMO_DE_DIGITOS <= len(digitos) <= MAXIMO_DE_DIGITOS:
            return ""

        return f"+{digitos}"

    # Sem indicativo: os formatos antigos, que continuam a chegar de código
    # escrito antes de haver seletor de país.
    if len(digitos) == 9:
        return f"+351{digitos}"

    if len(digitos) in (10, 11):
        return f"+55{digitos}"

    return ""


def validate_phone(phone):
    """Recusa o que não é telefone nenhum, e aceita o resto do mundo.

    O que se verifica é a forma, não a existência: sem uma lista de regras por
    país não há como saber se um número de Nairobi existe, e uma lista dessas
    envelhece sozinha. O indicativo é que é garantido — vem da lista de países
    do seletor.
    """

    numero = normalize_phone(phone)

    if not numero:
        raise ValidationError("Indique um telefone válido, com o indicativo do país.")

    return numero


def find_customer_by_email_or_phone(email="", phone=""):
    # Find an existing customer by email first, then by normalized phone.
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)

    if normalized_email:
        customer = (
            Customer.objects.filter(
                email__iexact=normalized_email,
            )
            .order_by("id")
            .first()
        )

        if customer:
            return customer

    if normalized_phone:
        for customer in Customer.objects.exclude(phone="").order_by("id"):
            if normalize_phone(customer.phone) == normalized_phone:
                return customer

    return None


def current_language():
    """A língua da página onde a pessoa está, normalizada.

    É o que decide em que língua ela vai receber as mensagens. Quem marca em
    /en/ recebe inglês; quem marca em português recebe português.
    """

    codigo = (get_language() or "").lower()

    return "en" if codigo.startswith("en") else "pt-pt"


def update_customer_contact_details(customer, name="", phone="", email="", user=None):
    # Refresh contact details of an existing customer without erasing stored data
    # and without downgrading a registered customer back to guest.
    update_fields = []

    if name and customer.full_name != name:
        customer.full_name = name
        update_fields.append("full_name")

    if phone and customer.phone != phone:
        customer.phone = phone
        update_fields.append("phone")

    if email and customer.email != email:
        customer.email = email
        update_fields.append("email")

    # A língua acompanha a última marcação: quem marcou em português e volta a
    # marcar na versão inglesa está a dizer em que língua quer ser tratado.
    lingua = current_language()

    if customer.language != lingua:
        customer.language = lingua
        update_fields.append("language")

    if user is not None:
        if customer.user_id != user.pk:
            customer.user = user
            update_fields.append("user")

        if customer.is_guest:
            customer.is_guest = False
            update_fields.append("is_guest")

    if update_fields:
        update_fields.append("updated_at")
        customer.save(update_fields=update_fields)

    return customer


def find_or_create_customer(name, phone, email, user=None):
    # Reuse an existing customer whenever the email or phone is already known.
    # Public bookings run without a user, so skipping this lookup would create a
    # duplicate customer record on every booking made by the same person.
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)

    customer = find_customer_by_email_or_phone(
        email=normalized_email,
        phone=normalized_phone,
    )

    if customer:
        return update_customer_contact_details(
            customer=customer,
            name=name,
            phone=normalized_phone or phone,
            email=normalized_email,
            user=user,
        )

    return Customer.objects.create(
        user=user,
        is_guest=user is None,
        full_name=name,
        phone=normalized_phone or phone,
        email=normalized_email,
        language=current_language(),
    )
