"""Tira a Manicure e a Pedicure da página inicial.

A página inicial passou a posicionar a casa como podologia: o título, os dois
primeiros cabeçalhos e os cartões dos problemas falam disso. Manicure e
pedicure ao lado diluíam a mensagem para quem chega à procura de um problema
nos pés.

Nada deixa de ser oferecido nem de ser marcável: as duas continuam na página
de serviços, na agenda e nos preços. O que muda é onde aparecem.

Reversível pelo interruptor de cada categoria, sem precisar de deploy.
"""

from django.db import migrations

FORA_DA_PAGINA_INICIAL = ["manicure", "pedicure"]


def esconder(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")

    ServiceCategory.objects.filter(slug__in=FORA_DA_PAGINA_INICIAL).update(
        show_on_homepage=False
    )


def mostrar(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")

    ServiceCategory.objects.filter(slug__in=FORA_DA_PAGINA_INICIAL).update(
        show_on_homepage=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0028_category_show_on_homepage"),
    ]

    operations = [
        migrations.RunPython(esconder, mostrar),
    ]
