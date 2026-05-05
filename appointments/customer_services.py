import re

from django.core.exceptions import ValidationError

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
        raise ValidationError("Informe um telefone válido do Brasil ou de Portugal.")

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


def find_or_create_customer(name, phone, email, user=None):
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)

    # Caso exista usuário (signup)
    if user is not None:
        customer = find_customer_by_email_or_phone(
            email=normalized_email,
            phone=normalized_phone,
        )

        if customer:
            # Vincula o usuário ao cliente existente
            customer.user = user
            customer.is_guest = False
            customer.full_name = name
            customer.phone = normalized_phone or phone
            customer.email = normalized_email
            customer.save(
                update_fields=[
                    "user",
                    "is_guest",
                    "full_name",
                    "phone",
                    "email",
                    "updated_at",
                ]
            )
            return customer

        # Se não encontrou, cria novo
        return Customer.objects.create(
            user=user,
            is_guest=False,
            full_name=name,
            phone=normalized_phone or phone,
            email=normalized_email,
        )

    # Fluxo de guest (sem usuário)
    return Customer.objects.create(
        user=None,
        is_guest=True,
        full_name=name,
        phone=normalized_phone or phone,
        email=normalized_email,
    )
