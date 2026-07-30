import unicodedata

from django.db import migrations

# Traduções do catálogo público para inglês.
#
# As categorias são identificadas pelo slug e os serviços pelo par
# (slug da categoria, nome normalizado). A normalização remove acentos e
# maiúsculas para que a correspondência não dependa de como o texto foi
# escrito na base de produção.
#
# Nada é sobrescrito: só preenche campos vazios, para não apagar traduções
# escritas à mão no admin.

CATEGORY_TRANSLATIONS = {
    "podologia": (
        "Podiatry",
        "Technical care for foot health, comfort and prevention.",
    ),
    "manicure": (
        "Manicure",
        "Cosmetic and technical care for hands and nails.",
    ),
    "pedicure": (
        "Pedicure",
        "Cosmetic and comfort care for feet and nails.",
    ),
    "enfermagem": (
        "Nursing",
        "Nursing support and basic home care.",
    ),
}

SERVICE_TRANSLATIONS = {
    ("podologia", "avaliacao podologica"): (
        "Podiatric assessment",
        "Initial consultation to assess the feet, identify needs and define the "
        "most suitable care.",
    ),
    ("podologia", "calosidades e hiperqueratoses"): (
        "Calluses and hyperkeratosis",
        "Treatment of calluses, thickened skin and the discomfort linked to "
        "plantar pressure.",
    ),
    ("podologia", "tratamento de pes diabeticos"): (
        "Diabetic foot treatment",
        "Assessment and preventive care for diabetic feet, with extra attention "
        "to pressure points, sensitivity and skin integrity.",
    ),
    ("podologia", "unha encravada"): (
        "Ingrown toenail",
        "Technical care for ingrown toenails, with a conservative approach and "
        "preventive guidance.",
    ),
    ("manicure", "cuticula russa"): (
        "Russian cuticle",
        "Detailed cuticle finishing technique for a clean and delicate result.",
    ),
    ("manicure", "manicure simples"): (
        "Basic manicure",
        "Basic fingernail care, including preparation, finishing and hydration.",
    ),
    ("manicure", "unha em gel"): (
        "Gel nails",
        "Gel nail application with a careful finish and maintenance guidance.",
    ),
    ("manicure", "verniz gel maos"): (
        "Gel polish for hands",
        "Gel polish applied to the hands with professional preparation and "
        "finishing.",
    ),
    ("pedicure", "corte de unhas dos pes"): (
        "Toenail trimming",
        "Trimming and finishing of the toenails, suited to regular maintenance.",
    ),
    ("pedicure", "hidratacao profunda dos pes"): (
        "Deep foot hydration",
        "Care focused on hydration, comfort and improving the appearance of the "
        "skin on the feet.",
    ),
    ("pedicure", "pedicure com verniz gel"): (
        "Pedicure with gel polish",
        "Pedicure with gel polish application and a long-lasting finish.",
    ),
    ("pedicure", "pedicure simples"): (
        "Basic pedicure",
        "Cosmetic care for the feet and nails, with a delicate and comfortable "
        "finish.",
    ),
    ("enfermagem", "administracao de medicacao a idosos"): (
        "Medication administration for older adults",
        "Organised support with administering prescribed medication to older "
        "adults.",
    ),
    ("enfermagem", "avaliacao de sinais vitais"): (
        "Vital signs assessment",
        "Measurement and recording of vital signs such as blood pressure, heart "
        "rate and temperature.",
    ),
    ("enfermagem", "cuidados de higiene e conforto a idosos"): (
        "Hygiene and comfort care for older adults",
        "Basic support for the wellbeing, comfort and hygiene routine of older "
        "adults.",
    ),
    ("enfermagem", "troca de penso"): (
        "Dressing change",
        "Support with simple dressing changes, with hygiene, care and "
        "appropriate guidance.",
    ),
}


def normalize(value):
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return without_accents.lower().strip()


def apply_translations(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")
    Service = apps.get_model("appointments", "Service")

    for category in ServiceCategory.objects.all():
        translation = CATEGORY_TRANSLATIONS.get(category.slug)

        if not translation:
            continue

        name_en, description_en = translation
        update_fields = []

        if not category.name_en:
            category.name_en = name_en
            update_fields.append("name_en")

        if not category.description_en:
            category.description_en = description_en
            update_fields.append("description_en")

        if update_fields:
            category.save(update_fields=update_fields)

    for service in Service.objects.select_related("category").all():
        key = (service.category.slug, normalize(service.name))
        translation = SERVICE_TRANSLATIONS.get(key)

        if not translation:
            continue

        name_en, description_en = translation
        update_fields = []

        if not service.name_en:
            service.name_en = name_en
            update_fields.append("name_en")

        if not service.description_en:
            service.description_en = description_en
            update_fields.append("description_en")

        if update_fields:
            service.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0009_service_description_en_service_name_en_and_more"),
    ]

    operations = [
        # Sem reversão: limpar os campos apagaria também traduções escritas
        # depois no admin.
        migrations.RunPython(apply_translations, migrations.RunPython.noop),
    ]
