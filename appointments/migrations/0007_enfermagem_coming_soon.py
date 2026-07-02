from django.db import migrations


def mark_enfermagem_as_coming_soon(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")
    ServiceCategory.objects.filter(slug="enfermagem").update(is_coming_soon=True)


def unmark_enfermagem_as_coming_soon(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")
    ServiceCategory.objects.filter(slug="enfermagem").update(is_coming_soon=False)


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0006_servicecategory_is_coming_soon"),
    ]

    operations = [
        migrations.RunPython(
            mark_enfermagem_as_coming_soon,
            unmark_enfermagem_as_coming_soon,
        ),
    ]
