"""O título e a legenda de cada caso passam a ter versão inglesa.

A moldura da página já era traduzida pelo gettext, mas o texto de cada par de
fotografias é escrito na área interna e vive na base de dados — em /en/ saía
em português no meio de uma página inglesa. Um campo por língua, como já
acontece nas categorias, nos serviços e nas páginas de condição, com o
português a servir de recurso quando o inglês fica vazio.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0033_drop_twilio"),
    ]

    operations = [
        migrations.AddField(
            model_name="beforeaftercase",
            name="title_en",
            field=models.CharField(
                blank=True,
                help_text="Usado nas páginas em /en/. Se ficar vazio, mostra o título em português.",
                max_length=140,
                verbose_name="Título da foto (inglês)",
            ),
        ),
        migrations.AddField(
            model_name="beforeaftercase",
            name="caption_en",
            field=models.TextField(
                blank=True,
                help_text="Usada nas páginas em /en/. Se ficar vazia, mostra a legenda em português.",
                verbose_name="Legenda da foto (inglês)",
            ),
        ),
    ]
