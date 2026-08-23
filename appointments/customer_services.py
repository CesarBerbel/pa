import re

from django.core.exceptions import ValidationError
from django.utils.translation import get_language

from appointments.models import Customer


def normalize_email(email):
    # Normalize email for consistent lookup and storage.
    if not email:
        return ""

    return email.strip().lower()


def normalize_phone(phone):
    # Normalize phone numbers for Brazil and Portugal.
    if not phone:
        return ""

    digits = re.sub(r"\D", "", phone)

    if digits.startswith("55") and len(digits) in [12, 13]:
        return f"+{digits}"

    if digits.startswith("351") and len(digits) == 12:
        return f"+{digits}"

    if len(digits) == 9:
        return f"+351{digits}"

    if len(digits) in [10, 11]:
        return f"+55{digits}"

    return ""


def validate_phone_for_brazil_or_portugal(phone):
    # Validate phone numbers accepted for Brazil and Portugal.
    normalized_phone = normalize_phone(phone)

    if not normalized_phone:
        raise ValidationError("Indique um telefone válido do Brasil ou de Portugal.")

    digits = re.sub(r"\D", "", normalized_phone)

    is_brazil_phone = digits.startswith("55") and len(digits) in [12, 13]
    is_portugal_phone = digits.startswith("351") and len(digits) == 12

    if not is_brazil_phone and not is_portugal_phone:
        raise ValidationError("O telefone deve ser válido para Brasil ou Portugal.")

    return normalized_phone


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
