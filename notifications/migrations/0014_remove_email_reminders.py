"""Apaga as regras e o modelo de email dos lembretes antes da marcação.

O envio de lembretes por email (1 dia antes e 2 horas antes) deixou de existir.
Ficam de pé as outras ações — pedido criado, marcação confirmada, marcação
cancelada — e os seguimentos pós-atendimento, que são outra coisa.

Tem de correr antes da migração que passa a exigir uma regra única por ação:
as duas regras de lembrete partilham o mesmo `event_type` e, deixadas na base
de dados, fariam a nova restrição falhar por cima de dados que já lá estavam.

O histórico do que foi enviado não se toca. Os campos `reminder_*_sent_at` das
marcações e os registos em `AppointmentReminderLog` continuam onde estavam:
apagá-los seria perder a prova de um aviso que a cliente recebeu mesmo.
"""

from django.db import migrations

CHAVE_DO_MODELO = "appointment_reminder"
ACAO_DO_LEMBRETE = "appointment_reminder"


def apagar_lembretes(apps, schema_editor):
    EmailEventSetting = apps.get_model("notifications", "EmailEventSetting")
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")

    # As regras primeiro: `email_template` é PROTECT, e apagar o modelo com
    # uma regra ainda a apontar-lhe rebentava a migração.
    EmailEventSetting.objects.filter(event_type=ACAO_DO_LEMBRETE).delete()

    EmailTemplate.objects.filter(key=CHAVE_DO_MODELO).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0013_whatsapp_appointment_link"),
    ]

    operations = [
        # Sem inverso: repor as regras traria de volta configuração de um
        # envio que já não tem código nenhum atrás dela.
        migrations.RunPython(apagar_lembretes, migrations.RunPython.noop),
    ]
