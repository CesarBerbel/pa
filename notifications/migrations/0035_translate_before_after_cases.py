"""As traduções inglesas dos casos que já estão publicados.

Os quatro casos foram escritos em português na área interna, e a página em
/en/ mostrava-os assim. Aqui ficam as versões inglesas dos títulos e das
legendas, identificadas pelo título normalizado — sem acentos e sem
maiúsculas, para que a correspondência não dependa de como o texto foi
escrito na base de produção.

Nada é sobrescrito: só preenche campos vazios, para não apagar uma tradução
escrita entretanto na área interna.
"""

import unicodedata

from django.db import migrations

TRANSLATIONS = {
    "calo com nucleo": (
        "Callus with a core",
        "She arrived in pain, uncomfortable in her shoes and struggling to "
        "walk. She left the appointment with relief, more comfort and "
        "confidence at every step 🦶✨",
    ),
    "onicomicose": (
        "Nail fungal infection",
        "Treatment is still under way, with a specific product to carry the "
        "care on at home. 🦶✨\r\n\r\nNeed the product? Ask us for more "
        "information.",
    ),
    "podoprofilaxia e onicomicose": (
        "Preventive foot care and nail fungal infection",
        "Looking after your feet is a man's business too! Podiatry helps "
        "prevent problems, treat changes in the nails and keep feet healthy "
        "and comfortable 🦶✨",
    ),
    "unha encravada": (
        "Ingrown toenail",
        "After 8 months living with the problem and never having had the right "
        "treatment, the client finally sought help. With the right care, we "
        "reached more comfort, relief and wellbeing 🦶✨",
    ),
}


def normalize(value):
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return without_accents.lower().strip()


def apply_translations(apps, schema_editor):
    BeforeAfterCase = apps.get_model("notifications", "BeforeAfterCase")

    for case in BeforeAfterCase.objects.all():
        translation = TRANSLATIONS.get(normalize(case.title))

        if not translation:
            continue

        title_en, caption_en = translation
        update_fields = []

        if not case.title_en:
            case.title_en = title_en
            update_fields.append("title_en")

        if not case.caption_en:
            case.caption_en = caption_en
            update_fields.append("caption_en")

        if update_fields:
            case.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0034_before_after_english_text"),
    ]

    operations = [
        # Sem reversão: limpar os campos apagaria também traduções escritas
        # depois na área interna.
        migrations.RunPython(apply_translations, migrations.RunPython.noop),
    ]
