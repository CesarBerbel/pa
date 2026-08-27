"""Semeia as páginas dos problemas tratados, todas por publicar.

O texto vem de `appointments/default_conditions.py` e entra com
`is_published=False`: são afirmações sobre saúde num site assinado por uma
enfermeira, e nenhuma delas deve aparecer antes de ser lida por ela.

**Só cria o que não existe.** Uma migração que sobrescrevesse apagaria o
trabalho de quem reescreveu um parágrafo — e o trabalho de reescrever é
exatamente o que se espera que aconteça a seguir.
"""

from django.db import migrations

from appointments.default_conditions import CONDICOES

CAMPOS = (
    "name",
    "summary",
    "what_it_is",
    "why_it_happens",
    "warning_signs",
    "how_we_treat",
    "home_care",
    "meta_title",
    "meta_description",
    "keywords",
    "display_order",
)


def semear(apps, schema_editor):
    TreatedCondition = apps.get_model("appointments", "TreatedCondition")
    ConditionQuestion = apps.get_model("appointments", "ConditionQuestion")

    for entrada in CONDICOES:
        condicao, criada = TreatedCondition.objects.get_or_create(
            slug=entrada["slug"],
            defaults={campo: entrada.get(campo, "") for campo in CAMPOS}
            | {"is_published": False},
        )

        if not criada:
            continue

        for ordem, pergunta in enumerate(entrada.get("questions", []), start=1):
            ConditionQuestion.objects.create(
                condition=condicao,
                question=pergunta["question"],
                answer=pergunta["answer"],
                display_order=ordem * 10,
            )


def apagar(apps, schema_editor):
    """Só apaga as que continuam por publicar e por tocar.

    Uma que já esteja publicada é uma página que alguém reviu e pôs no ar; um
    rollback da migração não é motivo para a deitar fora.
    """

    TreatedCondition = apps.get_model("appointments", "TreatedCondition")

    slugs = [entrada["slug"] for entrada in CONDICOES]

    TreatedCondition.objects.filter(slug__in=slugs, is_published=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0036_treatedcondition_conditionquestion"),
    ]

    operations = [
        migrations.RunPython(semear, apagar),
    ]
