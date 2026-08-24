"""Substitui "Podologia" por "Pedicure Terapêutica" no que se vê.

Em Portugal, podologia é um título com formação e regulamentação próprias. A
formação em Podologia foi feita no Brasil; em Portugal a formação é em
Pedicure Terapêutica. Chamar-lhe outra coisa no site seria afirmar uma
qualificação que não é a desta casa.

**O `slug` não muda.** Continua `podologia` porque é ele que está nos
endereços, nas ligações já indexadas pelo Google e na condição que escolhe o
ícone da categoria. Renomear o que se lê e manter o que se navega é o que
permite fazer isto sem partir nada.

**A colisão de nomes.** A categoria passa a chamar-se "Pedicure Terapêutica" e
já continha um serviço com esse nome exato — no fluxo de marcação daria
"Pedicure Terapêutica → Pedicure Terapêutica". O serviço passa a "Pedicure
Terapêutica (sessão)", que é o que distingue a sessão avulsa da área toda.

**Só se toca no que nunca foi editado à mão**, pela mesma prova das migrações
anteriores: um nome reescrito na área interna é uma decisão de quem gere a
clínica e vale mais do que o texto de fábrica.
"""

from django.db import migrations

CATEGORIA = {
    "slug": "podologia",
    "de": "Podologia",
    "para": "Pedicure Terapêutica",
    "de_en": "Podiatry",
    "para_en": "Therapeutic Pedicure",
}

SERVICOS = [
    ("Avaliação em Podologia", "Avaliação do pé"),
    ("Pedicure Terapêutica", "Pedicure Terapêutica (sessão)"),
]

ASSINATURAS = [
    ("Enfermeira e Podóloga", "Enfermeira | Pedicure Terapêutica"),
    ("Nurse and Podologist", "Nurse | Therapeutic Pedicure"),
]

CAMPOS_DE_TEXTO = [
    "subject",
    "body_text",
    "body_html",
    "subject_en",
    "body_text_en",
    "body_html_en",
]


def aplicar(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")
    Service = apps.get_model("appointments", "Service")
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")

    categoria = ServiceCategory.objects.filter(slug=CATEGORIA["slug"]).first()

    if categoria and categoria.name == CATEGORIA["de"]:
        campos = {"name": CATEGORIA["para"]}

        if categoria.name_en == CATEGORIA["de_en"]:
            campos["name_en"] = CATEGORIA["para_en"]

        ServiceCategory.objects.filter(pk=categoria.pk).update(**campos)

    for de, para in SERVICOS:
        Service.objects.filter(name=de, category__slug=CATEGORIA["slug"]).update(
            name=para
        )

    # As assinaturas estão dentro do texto de cada modelo, já guardado na base:
    # mudar o ficheiro de origem não toca no que lá está.
    for modelo in EmailTemplate.objects.all():
        campos = {}

        for campo in CAMPOS_DE_TEXTO:
            valor = getattr(modelo, campo, "") or ""
            novo = valor

            for de, para in ASSINATURAS:
                novo = novo.replace(de, para)

            if novo != valor:
                campos[campo] = novo

        if campos:
            EmailTemplate.objects.filter(pk=modelo.pk).update(**campos)


def reverter(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")
    Service = apps.get_model("appointments", "Service")
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")

    ServiceCategory.objects.filter(
        slug=CATEGORIA["slug"], name=CATEGORIA["para"]
    ).update(name=CATEGORIA["de"], name_en=CATEGORIA["de_en"])

    for de, para in SERVICOS:
        Service.objects.filter(name=para, category__slug=CATEGORIA["slug"]).update(
            name=de
        )

    for modelo in EmailTemplate.objects.all():
        campos = {}

        for campo in CAMPOS_DE_TEXTO:
            valor = getattr(modelo, campo, "") or ""
            novo = valor

            for de, para in ASSINATURAS:
                novo = novo.replace(para, de)

            if novo != valor:
                campos[campo] = novo

        if campos:
            EmailTemplate.objects.filter(pk=modelo.pk).update(**campos)


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0029_hide_manicure_pedicure_from_homepage"),
        ("notifications", "0025_beforeaftercase_after_focus_x_and_more"),
    ]

    operations = [
        migrations.RunPython(aplicar, reverter),
    ]
