"""As cinco secções fixas dão lugar a um texto livre, escrito num editor.

A estrutura era sempre a mesma — o que é, porque acontece, sinais de alerta,
como se trata, cuidados em casa — e isso dava páginas consistentes ao preço de
não caber lá uma tabela de sintomas, uma fotografia a meio ou uma ligação para
outra página. Quem escreve estas páginas sabe o que cada uma precisa.

**Nada do que estava escrito se perde.** As cinco secções são convertidas em
HTML, cada uma com o seu `<h2>`, pela mesma ordem em que apareciam na página.
Quem abrir a página depois desta migração vê exatamente o que via antes — e
passa a poder mudá-la.

A conversão é feita nas duas línguas à parte. Uma tradução a meio continua a
ser uma tradução a meio: o campo inglês só ganha os títulos ingleses das
secções que estavam traduzidas.
"""

from django.db import migrations, models

from appointments.rich_text import limpar

# Os títulos que a página desenhava por cima de cada secção, e que agora ficam
# escritos dentro do texto.
SECCOES = [
    ("what_it_is", "O que é", "What it is"),
    ("why_it_happens", "Porque acontece", "Why it happens"),
    ("warning_signs", "Sinais de alerta", "Warning signs"),
    ("how_we_treat", "Como se trata aqui", "How we treat it"),
    ("home_care", "Cuidados em casa", "Care at home"),
]


def paragrafos(texto):
    """O texto simples partido em parágrafos, como a página o mostrava.

    Era `|linebreaks` que fazia isto: linhas em branco separavam parágrafos.
    Converter sem isso juntava cinco parágrafos num bloco só.
    """

    from django.utils.html import escape

    blocos = [bloco.strip() for bloco in texto.split("\n\n") if bloco.strip()]

    return "".join(
        "<p>" + escape(bloco).replace("\n", "<br>") + "</p>" for bloco in blocos
    )


def montar(condicao, sufixo, indice_do_titulo):
    partes = []

    for campo, titulo_pt, titulo_en in SECCOES:
        texto = getattr(condicao, campo + sufixo, "") or ""

        if not texto.strip():
            continue

        titulo = (titulo_pt, titulo_en)[indice_do_titulo]

        partes.append(f"<h2>{titulo}</h2>")
        partes.append(paragrafos(texto))

    return "".join(partes)


def converter(apps, schema_editor):
    TreatedCondition = apps.get_model("appointments", "TreatedCondition")

    for condicao in TreatedCondition.objects.all():
        # `limpar` também aqui: uma migração não passa pelo `save()` do modelo
        # — usa o modelo histórico —, e o que fica guardado tem de ser seguro
        # venha de onde vier.
        condicao.body = limpar(montar(condicao, "", 0))
        condicao.body_en = limpar(montar(condicao, "_en", 1))

        condicao.save(update_fields=["body", "body_en"])


def desconverter(apps, schema_editor):
    """Não devolve o texto às cinco caixas.

    Podia tentar-se, cortando o HTML pelos `<h2>`. Mas quem escreveu uma
    tabela ou pôs uma fotografia depois desta migração não tem onde a pôr de
    volta, e uma reversão que devolve metade do trabalho é pior do que uma que
    diz que não sabe. O texto fica no `body`; as colunas antigas voltam
    vazias.
    """

    return


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0039_treatedcondition_hero_alt_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="treatedcondition",
            name="body",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Escreva como escreveria num documento. Pode usar títulos, "
                    "listas, tabelas, ligações e imagens."
                ),
                verbose_name="Texto da página",
            ),
        ),
        migrations.AddField(
            model_name="treatedcondition",
            name="body_en",
            field=models.TextField(blank=True, verbose_name="Texto da página (inglês)"),
        ),
        migrations.RunPython(converter, desconverter),
        migrations.RemoveField(model_name="treatedcondition", name="what_it_is"),
        migrations.RemoveField(model_name="treatedcondition", name="what_it_is_en"),
        migrations.RemoveField(model_name="treatedcondition", name="why_it_happens"),
        migrations.RemoveField(model_name="treatedcondition", name="why_it_happens_en"),
        migrations.RemoveField(model_name="treatedcondition", name="warning_signs"),
        migrations.RemoveField(model_name="treatedcondition", name="warning_signs_en"),
        migrations.RemoveField(model_name="treatedcondition", name="how_we_treat"),
        migrations.RemoveField(model_name="treatedcondition", name="how_we_treat_en"),
        migrations.RemoveField(model_name="treatedcondition", name="home_care"),
        migrations.RemoveField(model_name="treatedcondition", name="home_care_en"),
    ]
