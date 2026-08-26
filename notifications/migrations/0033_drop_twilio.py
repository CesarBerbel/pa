"""A Twilio sai do projeto, e com ela os campos que só a ela serviam.

O `provider` tinha dois valores e ficou com um; o Content SID, o texto para
aprovação da Meta e as posições numeradas eram o modelo aprovado que só aquele
caminho exigia. O que fica é o texto livre, que é o que o número da clínica
envia.

O histórico de envios não é tocado: as linhas antigas continuam a dizer que
saíram pela Twilio, porque saíram. Um histórico que deixa de saber ler o que
lá está não é um histórico.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0032_reminder_hours_on_template"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="whatsappeventsetting",
            name="content_sid",
        ),
        migrations.RemoveField(
            model_name="whatsappeventsetting",
            name="content_sid_en",
        ),
        migrations.RemoveField(
            model_name="whatsappeventsetting",
            name="content_variables",
        ),
        migrations.RemoveField(
            model_name="whatsappeventsetting",
            name="meta_template_body",
        ),
        migrations.RemoveField(
            model_name="whatsappeventsetting",
            name="provider",
        ),
        migrations.AlterField(
            model_name="whatsappeventsetting",
            name="body_template",
            field=models.TextField(
                blank=True,
                help_text="Texto livre, com as mesmas variáveis dos emails.",
                verbose_name="Mensagem",
            ),
        ),
        migrations.AlterField(
            model_name="whatsappmessagelog",
            name="delivery_status",
            field=models.CharField(
                blank=True,
                help_text="Estado final da entrega, quando o fornecedor o devolve.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="whatsappmessagelog",
            name="provider",
            field=models.CharField(
                choices=[
                    ("cloud_api", "WhatsApp Cloud API"),
                    ("twilio", "Twilio (retirado)"),
                    ("baileys", "Baileys"),
                ],
                default="cloud_api",
                max_length=20,
            ),
        ),
    ]
