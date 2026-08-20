"""Troca o interruptor único por um interruptor por canal.

O WhatsApp e o email avariam por razões diferentes: o WhatsApp perde a ligação,
o fornecedor bloqueia, o número muda — e nada disso é razão para a cliente
deixar de receber a confirmação por email. Com um interruptor só, desligar por
causa de um lado calava o outro sem motivo.

Os dois canais herdam o estado do interruptor antigo, para que ligar esta
versão não mude o que estava a sair.
"""

from django.db import migrations, models


def herdar_estado(apps, schema_editor):
    MessagingSetting = apps.get_model("notifications", "MessagingSetting")

    for definicao in MessagingSetting.objects.all():
        MessagingSetting.objects.filter(pk=definicao.pk).update(
            send_emails=definicao.is_enabled,
            send_whatsapp=definicao.is_enabled,
        )


def voltar_ao_interruptor_unico(apps, schema_editor):
    """Desligado num canal é desligado no interruptor único.

    Perde-se informação a voltar atrás — é o preço de um campo que passou a
    dois — e a escolha é a conservadora: se algum canal estava calado, o
    interruptor volta desligado em vez de assumir que podia falar.
    """

    MessagingSetting = apps.get_model("notifications", "MessagingSetting")

    for definicao in MessagingSetting.objects.all():
        MessagingSetting.objects.filter(pk=definicao.pk).update(
            is_enabled=definicao.send_emails and definicao.send_whatsapp,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0019_alter_emaileventsetting_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="messagingsetting",
            name="send_emails",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Confirmações, cancelamentos, seguimentos e envios manuais "
                    "por email. Desligado, as marcações continuam a funcionar."
                ),
                verbose_name="Enviar emails",
            ),
        ),
        migrations.AddField(
            model_name="messagingsetting",
            name="send_whatsapp",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Todas as regras de WhatsApp, incluindo os envios manuais e "
                    "os de teste. Desligado, as marcações continuam a funcionar."
                ),
                verbose_name="Enviar mensagens de WhatsApp",
            ),
        ),
        migrations.RunPython(herdar_estado, voltar_ao_interruptor_unico),
        migrations.RemoveField(
            model_name="messagingsetting",
            name="is_enabled",
        ),
    ]
