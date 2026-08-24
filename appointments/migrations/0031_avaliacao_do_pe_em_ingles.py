"""A versão inglesa do nome do serviço, que ficou para trás.

A migração anterior renomeou "Avaliação em Podologia" para "Avaliação do pé",
mas o nome inglês guardado à parte continuava "Podiatry assessment" — e é esse
que a versão inglesa do site mostra. Metade traduzida é o mesmo que não estar.
"""

from django.db import migrations

DE = "Podiatry assessment"
PARA = "Foot assessment"


def aplicar(apps, schema_editor):
    Service = apps.get_model("appointments", "Service")

    Service.objects.filter(name_en=DE).update(name_en=PARA)


def reverter(apps, schema_editor):
    Service = apps.get_model("appointments", "Service")

    Service.objects.filter(name_en=PARA).update(name_en=DE)


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0030_pedicure_terapeutica"),
    ]

    operations = [
        migrations.RunPython(aplicar, reverter),
    ]
