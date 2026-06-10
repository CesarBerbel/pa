from datetime import time
from decimal import Decimal

from appointments.models import BusinessHour, Service, ServiceCategory


def get_test_service_category(
    *,
    name="Podologia",
    slug="podologia",
    description="Categoria usada pelos testes automatizados.",
    display_order=10,
):
    # Reuse seeded categories from migrations when they already exist.
    category, _created = ServiceCategory.objects.get_or_create(
        slug=slug,
        defaults={
            "name": name,
            "description": description,
            "display_order": display_order,
            "is_active": True,
        },
    )
    return category


def create_test_service(
    *,
    category=None,
    name="Podologia",
    description="Serviço usado pelos testes automatizados.",
    duration_minutes=60,
    price=Decimal("50.00"),
    is_active=True,
):
    # Service.category is mandatory in the current production model.
    # Tests must create realistic services attached to a category.
    if category is None:
        category = get_test_service_category()

    return Service.objects.create(
        category=category,
        name=name,
        description=description,
        duration_minutes=duration_minutes,
        price=price,
        is_active=is_active,
    )


def ensure_test_business_hour(
    *,
    weekday,
    start_time=time(9, 0),
    end_time=time(18, 0),
    is_active=True,
):
    # BusinessHour.weekday is unique and migrations seed all weekdays.
    # Tests must update/reuse the row instead of inserting duplicates.
    business_hour, _created = BusinessHour.objects.update_or_create(
        weekday=weekday,
        defaults={
            "start_time": start_time,
            "end_time": end_time,
            "is_active": is_active,
        },
    )
    return business_hour
