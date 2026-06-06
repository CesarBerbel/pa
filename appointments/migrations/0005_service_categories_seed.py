from datetime import date, time
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion

CATEGORY_DATA = [
    {
        "name": "Podologia",
        "slug": "podologia",
        "description": "Cuidados técnicos para saúde, conforto e prevenção dos pés.",
        "display_order": 10,
    },
    {
        "name": "Manicure",
        "slug": "manicure",
        "description": "Cuidados estéticos e técnicos para mãos e unhas.",
        "display_order": 20,
    },
    {
        "name": "Pedicure",
        "slug": "pedicure",
        "description": "Cuidados estéticos e de conforto para pés e unhas.",
        "display_order": 30,
    },
    {
        "name": "Enfermagem",
        "slug": "enfermagem",
        "description": "Apoio de enfermagem e cuidados domiciliários básicos.",
        "display_order": 40,
    },
]

SERVICE_DATA = [
    {
        "category_slug": "podologia",
        "name": "Tratamento de pés diabéticos",
        "description": "Avaliação e cuidado preventivo de pés diabéticos, com atenção reforçada a zonas de pressão, sensibilidade e integridade da pele.",
        "duration_minutes": 60,
        "price": Decimal("45.00"),
    },
    {
        "category_slug": "podologia",
        "name": "Calosidades e hiperqueratoses",
        "description": "Tratamento de calosidades, pele espessada e desconforto associado ao apoio plantar.",
        "duration_minutes": 45,
        "price": Decimal("35.00"),
    },
    {
        "category_slug": "podologia",
        "name": "Unha encravada",
        "description": "Cuidado técnico da unha encravada, com abordagem conservadora e orientação preventiva.",
        "duration_minutes": 45,
        "price": Decimal("35.00"),
    },
    {
        "category_slug": "podologia",
        "name": "Avaliação podológica",
        "description": "Consulta inicial para avaliação dos pés, identificação de necessidades e definição do cuidado mais adequado.",
        "duration_minutes": 30,
        "price": Decimal("25.00"),
    },
    {
        "category_slug": "manicure",
        "name": "Unha em gel",
        "description": "Aplicação de unhas em gel com acabamento cuidado e orientação de manutenção.",
        "duration_minutes": 90,
        "price": Decimal("35.00"),
    },
    {
        "category_slug": "manicure",
        "name": "Manicure simples",
        "description": "Cuidado básico das unhas das mãos, incluindo preparação, acabamento e hidratação.",
        "duration_minutes": 45,
        "price": Decimal("18.00"),
    },
    {
        "category_slug": "manicure",
        "name": "Cutícula russa",
        "description": "Técnica de acabamento detalhado da cutícula para resultado limpo e delicado.",
        "duration_minutes": 60,
        "price": Decimal("25.00"),
    },
    {
        "category_slug": "manicure",
        "name": "Verniz gel mãos",
        "description": "Aplicação de verniz gel nas mãos com preparação e acabamento profissional.",
        "duration_minutes": 60,
        "price": Decimal("25.00"),
    },
    {
        "category_slug": "pedicure",
        "name": "Pedicure simples",
        "description": "Cuidado estético dos pés e unhas, com acabamento delicado e confortável.",
        "duration_minutes": 50,
        "price": Decimal("22.00"),
    },
    {
        "category_slug": "pedicure",
        "name": "Corte de unhas dos pés",
        "description": "Corte e acabamento das unhas dos pés, indicado para manutenção regular.",
        "duration_minutes": 30,
        "price": Decimal("15.00"),
    },
    {
        "category_slug": "pedicure",
        "name": "Pedicure com verniz gel",
        "description": "Pedicure com aplicação de verniz gel e acabamento duradouro.",
        "duration_minutes": 75,
        "price": Decimal("30.00"),
    },
    {
        "category_slug": "pedicure",
        "name": "Hidratação profunda dos pés",
        "description": "Cuidado focado em hidratação, conforto e melhoria do aspeto da pele dos pés.",
        "duration_minutes": 40,
        "price": Decimal("20.00"),
    },
    {
        "category_slug": "enfermagem",
        "name": "Troca de penso",
        "description": "Apoio na troca de penso simples, com higiene, cuidado e orientação adequada.",
        "duration_minutes": 30,
        "price": Decimal("25.00"),
    },
    {
        "category_slug": "enfermagem",
        "name": "Administração de medicação a idosos",
        "description": "Apoio organizado à administração de medicação prescrita a idosos.",
        "duration_minutes": 30,
        "price": Decimal("20.00"),
    },
    {
        "category_slug": "enfermagem",
        "name": "Cuidados de higiene e conforto a idosos",
        "description": "Apoio básico ao bem-estar, conforto e rotina de higiene de idosos.",
        "duration_minutes": 60,
        "price": Decimal("35.00"),
    },
    {
        "category_slug": "enfermagem",
        "name": "Avaliação de sinais vitais",
        "description": "Medição e registo de sinais vitais, como tensão arterial, frequência cardíaca e temperatura.",
        "duration_minutes": 30,
        "price": Decimal("20.00"),
    },
]

LEGACY_CATEGORY_SERVICE_NAMES = {
    "podologia": "Avaliação podológica",
    "manicure": "Manicure simples",
    "pedicure": "Pedicure simples",
}


def create_categories(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")

    for category_data in CATEGORY_DATA:
        ServiceCategory.objects.update_or_create(
            slug=category_data["slug"],
            defaults=category_data,
        )


def seed_services_hours_and_lunch(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")
    Service = apps.get_model("appointments", "Service")
    BusinessHour = apps.get_model("appointments", "BusinessHour")
    ScheduleBlock = apps.get_model("appointments", "ScheduleBlock")

    categories = {
        category.slug: category
        for category in ServiceCategory.objects.filter(
            slug__in=[item["slug"] for item in CATEGORY_DATA]
        )
    }

    podologia = categories["podologia"]

    for service in Service.objects.filter(category__isnull=True):
        normalized_name = service.name.strip().lower()
        replacement_name = LEGACY_CATEGORY_SERVICE_NAMES.get(normalized_name)

        service.category = podologia

        if replacement_name:
            service.name = replacement_name

        service.save(update_fields=["category", "name"])

    for service_data in SERVICE_DATA:
        category = categories[service_data["category_slug"]]
        Service.objects.update_or_create(
            category=category,
            name=service_data["name"],
            defaults={
                "description": service_data["description"],
                "duration_minutes": service_data["duration_minutes"],
                "price": service_data["price"],
                "is_active": True,
            },
        )

    for weekday in range(7):
        BusinessHour.objects.update_or_create(
            weekday=weekday,
            defaults={
                "start_time": time(8, 0),
                "end_time": time(20, 0),
                "is_active": True,
            },
        )

    ScheduleBlock.objects.update_or_create(
        title="Almoço",
        block_type="break",
        date=date(2026, 1, 1),
        defaults={
            "start_time": time(13, 0),
            "end_time": time(14, 0),
            "is_full_day": False,
            "is_recurring": True,
            "recurring_weekdays": "0,1,2,3,4,5,6",
            "recurrence_end_date": None,
            "is_active": True,
            "notes": "Bloqueio automático criado para a pausa de almoço diária.",
        },
    )


def reverse_seed(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")
    ScheduleBlock = apps.get_model("appointments", "ScheduleBlock")

    ScheduleBlock.objects.filter(title="Almoço", block_type="break").delete()
    ServiceCategory.objects.filter(
        slug__in=[item["slug"] for item in CATEGORY_DATA]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0004_remove_appointment_appt_date_start_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceCategory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, unique=True)),
                ("slug", models.SlugField(max_length=140, unique=True)),
                ("description", models.TextField(blank=True)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Categoria de serviço",
                "verbose_name_plural": "Categorias de serviço",
                "ordering": ["display_order", "name"],
            },
        ),
        migrations.AddField(
            model_name="service",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="services",
                to="appointments.servicecategory",
            ),
        ),
        migrations.RunPython(create_categories, migrations.RunPython.noop),
        migrations.RunPython(seed_services_hours_and_lunch, reverse_seed),
        migrations.AlterField(
            model_name="service",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="services",
                to="appointments.servicecategory",
            ),
        ),
        migrations.AlterModelOptions(
            name="service",
            options={
                "ordering": ["category__display_order", "category__name", "name"],
                "verbose_name": "Serviço",
                "verbose_name_plural": "Serviços",
            },
        ),
    ]
