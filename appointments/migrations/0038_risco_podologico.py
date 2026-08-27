"""A página do pé diabético passa a chamar-se Risco Podológico.

O card da página inicial sempre lhe chamou "Risco Podológico" e a página
chamava-lhe "Pé diabético": o mesmo assunto com dois nomes no mesmo site.

**O endereço e o título ficam como estavam.** É deliberado e é a parte que
importa: `pe-diabetico` e "Pé diabético: cuidados e vigilância em Coimbra" são
o que as pessoas escrevem no Google e são os dois sítios onde o Google o lê. O
nome muda onde as pessoas leem — o título da página, o índice, o caminho, os
cards. O termo procurado fica onde é procurado; o termo da casa fica onde é
lido.

**Só mexe no que continua como foi semeado.** Um campo reescrito à mão é uma
decisão de quem o reescreveu, e uma migração não a desfaz.
"""

from django.db import migrations

ANTIGO_NOME = "Pé diabético"
NOVO_NOME = "Risco Podológico"

ANTIGA_DEFINICAO = (
    '"Pé diabético" é o conjunto de alterações que a diabetes pode '
    "provocar nos pés ao longo do tempo — perda de sensibilidade, "
    "pior circulação, pele mais seca, maior risco de infeção. Não é "
    "uma doença que se apanha de um dia para o outro: é um risco que "
    "se acompanha, e que se acompanha bem."
)

NOVA_DEFINICAO = (
    "Risco podológico é o nome que se dá à probabilidade de um pé "
    "vir a ter uma complicação — uma ferida que não fecha, uma "
    "infeção, uma lesão que passou despercebida. A diabetes é a causa "
    "mais frequente, por afetar ao mesmo tempo a sensibilidade e a "
    "circulação, mas não é a única. Não é uma doença que se apanha de "
    "um dia para o outro: é um risco que se avalia e se acompanha."
)

ANTIGA_DESCRICAO = (
    "Na diabetes, um pequeno problema no pé deixa de ser pequeno. "
    "Saiba o que vigiar, com que frequência, e em que consiste a "
    "consulta de pé diabético em Coimbra."
)

NOVA_DESCRICAO = ANTIGA_DESCRICAO.replace(
    "consulta de pé diabético", "consulta de risco podológico"
)


def renomear(
    apps,
    schema_editor,
    de,
    para,
    definicao_de,
    definicao_para,
    descricao_de,
    descricao_para,
):
    TreatedCondition = apps.get_model("appointments", "TreatedCondition")

    condicao = TreatedCondition.objects.filter(slug="pe-diabetico").first()

    if not condicao:
        return

    if condicao.name == de:
        condicao.name = para

    if condicao.what_it_is == definicao_de:
        condicao.what_it_is = definicao_para

    if condicao.meta_description == descricao_de:
        condicao.meta_description = descricao_para

    condicao.save()


def para_a_frente(apps, schema_editor):
    renomear(
        apps,
        schema_editor,
        ANTIGO_NOME,
        NOVO_NOME,
        ANTIGA_DEFINICAO,
        NOVA_DEFINICAO,
        ANTIGA_DESCRICAO,
        NOVA_DESCRICAO,
    )


def para_tras(apps, schema_editor):
    renomear(
        apps,
        schema_editor,
        NOVO_NOME,
        ANTIGO_NOME,
        NOVA_DEFINICAO,
        ANTIGA_DEFINICAO,
        NOVA_DESCRICAO,
        ANTIGA_DESCRICAO,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0037_seed_treated_conditions"),
    ]

    operations = [
        migrations.RunPython(para_a_frente, para_tras),
    ]
