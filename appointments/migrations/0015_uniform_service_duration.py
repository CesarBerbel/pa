from django.db import migrations

# Todos os atendimentos passam a ocupar 1 hora na agenda.
#
# A duração deixou de ser mostrada nas páginas públicas, mas o campo continua a
# existir: é ele que define o tamanho do bloco na agenda e a deteção de
# sobreposição entre marcações.

DURACAO_UNIFORME = 60


def uniformizar(apps, schema_editor):
    Service = apps.get_model("appointments", "Service")

    Service.objects.exclude(duration_minutes=DURACAO_UNIFORME).update(
        duration_minutes=DURACAO_UNIFORME,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0014_patient_record"),
    ]

    operations = [
        # Sem reversão: as durações anteriores eram estimativas por serviço e
        # não há valor de referência para onde voltar.
        migrations.RunPython(uniformizar, migrations.RunPython.noop),
    ]
