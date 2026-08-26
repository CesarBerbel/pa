"""A antecedência do lembrete muda de sítio: do interruptor geral para o modelo.

Estava em *Envio de mensagens*, ao lado dos interruptores dos canais, e é lá
que ninguém a procura: quem vai afinar o lembrete vai ao lembrete. Passa a
viver no modelo da mensagem, ao pé do texto — é a mesma decisão, o que se diz e
quando se diz.

O valor que lá estivesse acompanha a mudança. É pouco provável que alguém lhe
tenha mexido — a definição existiu durante uma tarde — mas copiá-lo custa três
linhas e evita repor um número à mão.
"""

from django.db import migrations, models

CHAVE = "appointment_reminder"


def levar_as_horas(apps, schema_editor):
    MessagingSetting = apps.get_model("notifications", "MessagingSetting")
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")

    definicao = MessagingSetting.objects.first()

    if not definicao:
        return

    EmailTemplate.objects.filter(key=CHAVE).update(
        reminder_hours_before=definicao.reminder_hours_before
    )


def trazer_as_horas(apps, schema_editor):
    MessagingSetting = apps.get_model("notifications", "MessagingSetting")
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")

    modelo = EmailTemplate.objects.filter(key=CHAVE).first()

    if modelo:
        MessagingSetting.objects.update(
            reminder_hours_before=modelo.reminder_hours_before
        )


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0031_seed_reminder_messages"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailtemplate",
            name="reminder_hours_before",
            field=models.PositiveIntegerField(
                default=24,
                help_text="Quantas horas antes da marcação sai o lembrete. Zero desliga-o. Só tem efeito no modelo do lembrete.",
                verbose_name="Antecedência (horas)",
            ),
        ),
        # Copiar antes de apagar, senão o valor ia com o campo.
        migrations.RunPython(levar_as_horas, trazer_as_horas),
        migrations.RemoveField(
            model_name="messagingsetting",
            name="reminder_hours_before",
        ),
    ]
