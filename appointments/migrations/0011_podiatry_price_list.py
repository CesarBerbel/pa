import unicodedata
from decimal import Decimal

from django.db import migrations

# Tabela de preços de Podologia e criação da categoria Laserterapia.
#
# Os quatro serviços de Podologia que já existiam são renomeados e reavaliados
# em vez de recriados, para que as marcações antigas continuem ligadas ao
# serviço certo (Appointment.service usa on_delete=PROTECT).
#
# Condições como "desde", "por sessão" ou a dedução da avaliação ficam na
# descrição: o campo price é um valor único e não comporta essa nuance.

# nome normalizado atual -> (nome, descrição, preço, nome_en, descrição_en)
RENAMED_SERVICES = {
    "avaliacao podologica": (
        "Avaliação em Podologia",
        "Consulta de avaliação dos pés, com identificação de necessidades e "
        "definição do plano de cuidado. O valor é deduzido caso realize "
        "tratamento no mesmo dia.",
        Decimal("15.00"),
        "Podiatry assessment",
        "Foot assessment consultation, identifying needs and defining a care "
        "plan. The fee is deducted if you have treatment on the same day.",
    ),
    "calosidades e hiperqueratoses": (
        "Remoção de calosidades",
        "Remoção de calosidades e pele espessada, com alívio do desconforto ao "
        "apoiar o pé.",
        Decimal("20.00"),
        "Callus removal",
        "Removal of calluses and thickened skin, relieving discomfort when "
        "standing.",
    ),
    "unha encravada": (
        "Desencravamento de unha (espícula)",
        "Remoção da espícula da unha encravada, com abordagem conservadora e "
        "orientação preventiva.",
        Decimal("25.00"),
        "Ingrown toenail removal (spicule)",
        "Removal of the ingrown nail spicule, with a conservative approach and "
        "preventive guidance.",
    ),
    "tratamento de pes diabeticos": (
        "Pé diabético (avaliação e tratamento)",
        "Avaliação e tratamento do pé diabético, com atenção reforçada a zonas "
        "de pressão, sensibilidade e integridade da pele.",
        Decimal("40.00"),
        "Diabetic foot (assessment and treatment)",
        "Diabetic foot assessment and treatment, with extra attention to "
        "pressure points, sensitivity and skin integrity.",
    ),
}

# (nome, descrição, duração, preço, nome_en, descrição_en)
NEW_PODIATRY_SERVICES = [
    (
        "Pedicure Terapêutica",
        "Pedicure com finalidade clínica, focada em conforto, higiene e " "prevenção.",
        50,
        Decimal("35.00"),
        "Therapeutic pedicure",
        "Clinical pedicure focused on comfort, hygiene and prevention.",
    ),
    (
        "Tratamento de calo (desbaste e alívio da dor)",
        "Desbaste do calo com alívio imediato da dor e orientação para evitar a "
        "recorrência.",
        40,
        Decimal("30.00"),
        "Corn treatment (debridement and pain relief)",
        "Corn debridement with immediate pain relief and guidance to prevent "
        "recurrence.",
    ),
    (
        "Tratamento de calo + Pedicure Terapêutica",
        "Tratamento de calo combinado com pedicure terapêutica na mesma sessão.",
        75,
        Decimal("50.00"),
        "Corn treatment + therapeutic pedicure",
        "Corn treatment combined with a therapeutic pedicure in the same " "session.",
    ),
    (
        "Colocação de órtese ungueal",
        "Aplicação de órtese na unha para correção da curvatura e alívio da "
        "pressão.",
        30,
        Decimal("25.00"),
        "Nail brace fitting",
        "Fitting of a nail brace to correct curvature and relieve pressure.",
    ),
    (
        "Tratamento de verruga plantar",
        "Tratamento de verruga plantar, com acompanhamento da evolução.",
        45,
        Decimal("35.00"),
        "Plantar wart treatment",
        "Plantar wart treatment, with follow-up of its progress.",
    ),
    (
        "Penso especializado / Laserterapia",
        "Penso especializado ou aplicação de laserterapia. Valor a partir de "
        "20 €, conforme a área tratada e a complexidade.",
        30,
        Decimal("20.00"),
        "Specialised dressing / Laser therapy",
        "Specialised dressing or laser therapy application. From €20, depending "
        "on the area treated and the complexity.",
    ),
]

LASER_CATEGORY = {
    "slug": "laserterapia",
    "name": "Laserterapia",
    "description": "Tratamentos com laser para unhas, pele e circulação.",
    "name_en": "Laser therapy",
    "description_en": "Laser treatments for nails, skin and circulation.",
    # Fica logo a seguir a Podologia (10) e antes de Manicure (20).
    "display_order": 15,
}

LASER_SERVICES = [
    (
        "Onicomicose (fungo da unha)",
        "Laserterapia para onicomicose. Valor por sessão; o número de sessões "
        "depende da evolução do tratamento.",
        30,
        Decimal("30.00"),
        "Onychomycosis (nail fungus)",
        "Laser therapy for onychomycosis. Price per session; the number of "
        "sessions depends on how the treatment progresses.",
    ),
    (
        "Fissuras e lesões da pele",
        "Laserterapia para fissuras e lesões da pele. Valor por sessão.",
        30,
        Decimal("25.00"),
        "Skin fissures and lesions",
        "Laser therapy for skin fissures and lesions. Price per session.",
    ),
    (
        "ILIB",
        "Sessão de ILIB, irradiação sanguínea por laser. Valor por sessão.",
        45,
        Decimal("30.00"),
        "ILIB",
        "ILIB session, intravascular laser irradiation of blood. Price per " "session.",
    ),
    (
        "Pacote ILIB (10 sessões)",
        "Pacote de 10 sessões de ILIB, com valor mais vantajoso do que as "
        "sessões avulsas.",
        45,
        Decimal("270.00"),
        "ILIB package (10 sessions)",
        "Package of 10 ILIB sessions, at a better rate than individual " "sessions.",
    ),
]


def normalize(value):
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return without_accents.lower().strip()


def ensure_service(Service, category, definition):
    name, description, duration, price, name_en, description_en = definition

    service, created = Service.objects.get_or_create(
        category=category,
        name=name,
        defaults={
            "description": description,
            "duration_minutes": duration,
            "price": price,
            "is_active": True,
            "name_en": name_en,
            "description_en": description_en,
        },
    )

    if created:
        return

    # Já existia: acerta o preço e as traduções sem tocar na duração, que pode
    # ter sido ajustada à mão no admin.
    service.description = description
    service.price = price
    service.name_en = name_en
    service.description_en = description_en
    service.is_active = True
    service.save(
        update_fields=[
            "description",
            "price",
            "name_en",
            "description_en",
            "is_active",
        ]
    )


def apply_price_list(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")
    Service = apps.get_model("appointments", "Service")

    podiatry = ServiceCategory.objects.filter(slug="podologia").first()

    if podiatry:
        for service in Service.objects.filter(category=podiatry):
            definition = RENAMED_SERVICES.get(normalize(service.name))

            if not definition:
                continue

            name, description, price, name_en, description_en = definition

            service.name = name
            service.description = description
            service.price = price
            service.name_en = name_en
            service.description_en = description_en
            service.is_active = True
            service.save(
                update_fields=[
                    "name",
                    "description",
                    "price",
                    "name_en",
                    "description_en",
                    "is_active",
                ]
            )

        for definition in NEW_PODIATRY_SERVICES:
            ensure_service(Service, podiatry, definition)

    laser, _created = ServiceCategory.objects.get_or_create(
        slug=LASER_CATEGORY["slug"],
        defaults={
            "name": LASER_CATEGORY["name"],
            "description": LASER_CATEGORY["description"],
            "name_en": LASER_CATEGORY["name_en"],
            "description_en": LASER_CATEGORY["description_en"],
            "display_order": LASER_CATEGORY["display_order"],
            "is_active": True,
            "is_coming_soon": False,
        },
    )

    for definition in LASER_SERVICES:
        ensure_service(Service, laser, definition)


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0010_translate_service_catalog"),
    ]

    operations = [
        # Sem reversão: desfazer devolveria preços antigos e apagaria serviços
        # que podem entretanto ter marcações associadas.
        migrations.RunPython(apply_price_list, migrations.RunPython.noop),
    ]
