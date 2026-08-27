"""Põe a versão inglesa das páginas dos problemas.

Coimbra tem quem procure em inglês, e "ingrown toenail Coimbra" é uma pesquisa
que hoje não leva a lado nenhum desta casa.

**Só preenche o que estiver vazio, campo a campo.** Uma tradução escrita à mão
é uma decisão de quem a escreveu, e uma migração não a desfaz — nem sequer para
a substituir por uma melhor. Isto vale campo a campo e não por página: uma
página com o nome já traduzido e o corpo por traduzir recebe só o corpo.

O endereço não muda: é o mesmo `/o-que-tratamos/unha-encravada/`, servido sob
`/en/`. Um segundo endereço para o mesmo conteúdo dividia em dois o que o
Google já sabe sobre a página.
"""

from django.db import migrations

from appointments.default_conditions_en import CONDICOES_EN
from appointments.rich_text import limpar

CAMPOS = ("name", "summary", "meta_title", "meta_description", "keywords")


def montar_corpo(seccoes):
    """As secções em HTML, com o mesmo desenho da versão portuguesa."""

    from django.utils.html import escape

    partes = []

    for titulo, texto in seccoes:
        partes.append(f"<h2>{escape(titulo)}</h2>")
        partes.append(f"<p>{escape(texto)}</p>")

    return limpar("".join(partes))


def traduzir(apps, schema_editor):
    TreatedCondition = apps.get_model("appointments", "TreatedCondition")

    for slug, ingles in CONDICOES_EN.items():
        condicao = TreatedCondition.objects.filter(slug=slug).first()

        if not condicao:
            continue

        mexeu = []

        for campo in CAMPOS:
            nome_en = f"{campo}_en"

            if not getattr(condicao, nome_en, "").strip():
                setattr(condicao, nome_en, ingles[campo])
                mexeu.append(nome_en)

        if not condicao.body_en.strip():
            condicao.body_en = montar_corpo(ingles["body"])
            mexeu.append("body_en")

        if mexeu:
            condicao.save(update_fields=mexeu)

        # As perguntas seguem a ordem em que foram semeadas. Emparelhar pelo
        # texto português seria mais seguro contra reordenações, mas mais
        # frágil contra o que é de facto provável: alguém reescrever uma
        # pergunta e deixar a ordem quieta.
        perguntas = list(condicao.questions.order_by("display_order", "id"))

        for pergunta, (texto_en, resposta_en) in zip(perguntas, ingles["questions"]):
            campos = []

            if not pergunta.question_en.strip():
                pergunta.question_en = texto_en
                campos.append("question_en")

            if not pergunta.answer_en.strip():
                pergunta.answer_en = resposta_en
                campos.append("answer_en")

            if campos:
                pergunta.save(update_fields=campos)


def apagar(apps, schema_editor):
    """Esvazia os campos ingleses das páginas que esta migração semeou.

    Só as que continuam iguais ao que aqui está: uma tradução reescrita à mão
    depois disto sobrevive à reversão.
    """

    TreatedCondition = apps.get_model("appointments", "TreatedCondition")

    for slug, ingles in CONDICOES_EN.items():
        condicao = TreatedCondition.objects.filter(slug=slug).first()

        if not condicao:
            continue

        for campo in CAMPOS:
            nome_en = f"{campo}_en"

            if getattr(condicao, nome_en, "") == ingles[campo]:
                setattr(condicao, nome_en, "")

        if condicao.body_en == montar_corpo(ingles["body"]):
            condicao.body_en = ""

        condicao.save()


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0041_treatedcondition_hero_alt_en_and_more"),
    ]

    operations = [
        migrations.RunPython(traduzir, apagar),
    ]
