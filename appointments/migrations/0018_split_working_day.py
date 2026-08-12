from datetime import time

from django.db import migrations

# Divide o dia de trabalho em dois períodos e desativa o bloqueio de almoço.
#
# Antes, o dia era 08:00–20:00 com um bloqueio recorrente das 13:00 às 14:00.
# A pausa passa a estar implícita no horário de trabalho: 08:00–12:00 e
# 14:00–18:00. Uma coisa a manter em vez de duas que têm de concordar entre si.

MANHA = (time(8, 0), time(12, 0))
TARDE = (time(14, 0), time(18, 0))


def dividir_dia(apps, schema_editor):
    BusinessHour = apps.get_model("appointments", "BusinessHour")
    ScheduleBlock = apps.get_model("appointments", "ScheduleBlock")

    BusinessHour.objects.all().update(
        start_time=MANHA[0],
        end_time=MANHA[1],
        second_start_time=TARDE[0],
        second_end_time=TARDE[1],
    )

    # O bloqueio deixa de fazer sentido: a pausa já não é horário de trabalho.
    # Fica desativado em vez de apagado, para o histórico não perder a razão
    # pela qual antigas marcações foram recusadas àquela hora.
    ScheduleBlock.objects.filter(
        is_recurring=True,
        title__iexact="Almoço",
    ).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0017_business_hour_second_period"),
    ]

    operations = [
        # Sem reversão: voltar atrás reporia um horário que já não corresponde
        # ao praticado e reativaria um bloqueio redundante.
        migrations.RunPython(dividir_dia, migrations.RunPython.noop),
    ]
