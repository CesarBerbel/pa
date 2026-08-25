"""A morada do domicílio passa de uma caixa de texto a campos.

Escrita à mão numa caixa só, chegava "Rua das Flores 12" — sem código postal
nem localidade — e quem lá ia descobria-o à porta. Em campos, o que falta
vê-se, e o autocompletar da Google preenche-os de uma vez.

O que estivesse escrito na caixa antiga passa para a rua: é o campo que a
substitui, e ninguém perde o que já tinha escrito.
"""

from django.db import migrations, models


def morada_para_a_rua(apps, schema_editor):
    Appointment = apps.get_model("appointments", "Appointment")

    for marcacao in Appointment.objects.exclude(home_address="").only(
        "id", "home_address"
    ):
        Appointment.objects.filter(pk=marcacao.pk).update(
            home_street=marcacao.home_address.strip()[:255]
        )


def a_rua_para_a_morada(apps, schema_editor):
    Appointment = apps.get_model("appointments", "Appointment")

    for marcacao in Appointment.objects.exclude(home_street="").only(
        "id", "home_street"
    ):
        Appointment.objects.filter(pk=marcacao.pk).update(
            home_address=marcacao.home_street
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "appointments",
            "0032_appointment_home_address_appointment_home_directions_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="home_country",
            field=models.CharField(blank=True, max_length=120, verbose_name="País"),
        ),
        migrations.AddField(
            model_name="appointment",
            name="home_district",
            field=models.CharField(blank=True, max_length=120, verbose_name="Distrito"),
        ),
        migrations.AddField(
            model_name="appointment",
            name="home_floor",
            field=models.CharField(
                blank=True,
                help_text="3.º Dto, R/C esquerdo, Lote 4 — o que estiver na porta.",
                max_length=60,
                verbose_name="Andar ou fração",
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="home_locality",
            field=models.CharField(
                blank=True, max_length=120, verbose_name="Localidade"
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="home_municipality",
            field=models.CharField(blank=True, max_length=120, verbose_name="Concelho"),
        ),
        migrations.AddField(
            model_name="appointment",
            name="home_number",
            field=models.CharField(blank=True, max_length=30, verbose_name="Número"),
        ),
        migrations.AddField(
            model_name="appointment",
            name="home_postal_code",
            field=models.CharField(
                blank=True, max_length=20, verbose_name="Código postal"
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="home_street",
            field=models.CharField(
                blank=True,
                help_text="Obrigatória num atendimento em domicílio.",
                max_length=255,
                verbose_name="Rua",
            ),
        ),
        migrations.RunPython(morada_para_a_rua, a_rua_para_a_morada),
        migrations.RemoveField(
            model_name="appointment",
            name="home_address",
        ),
    ]
