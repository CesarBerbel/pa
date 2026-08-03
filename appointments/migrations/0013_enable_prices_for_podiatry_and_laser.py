from django.db import migrations

# Liga a exibição de preços nas duas categorias cuja tabela foi revista.
# As restantes (Manicure, Pedicure, Enfermagem) ficam desligadas de propósito:
# os preços que têm vêm do arranque inicial e ainda não foram confirmados.

CATEGORIES_WITH_PUBLIC_PRICES = ["podologia", "laserterapia"]


def enable_prices(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")

    ServiceCategory.objects.filter(
        slug__in=CATEGORIES_WITH_PUBLIC_PRICES,
    ).update(show_prices=True)


def disable_prices(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")

    ServiceCategory.objects.filter(
        slug__in=CATEGORIES_WITH_PUBLIC_PRICES,
    ).update(show_prices=False)


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0012_servicecategory_show_prices"),
    ]

    operations = [
        migrations.RunPython(enable_prices, disable_prices),
    ]
