"""O preçário revisto: os valores da tabela que está afixada na clínica.

Três coisas acontecem aqui, e por esta ordem.

**Os preços que mudaram.** Os serviços são acertados pelo nome, não recriados:
`Appointment.service` é `PROTECT`, e apagar para voltar a criar deixaria as
marcações antigas sem sítio para onde apontar.

**As condições que o campo `price` não sabe dizer.** "Desde 40 €" e "entre 15 €
e 20 €" não cabem num `DecimalField`. Como em 0011, o preço guarda o valor mais
baixo — o que a pessoa vê antes de decidir — e a nuance fica escrita na
descrição.

**O ILIB sai, o resto entra.** ILIB e o pacote de 10 sessões deixaram de ser
oferecidos: ficam inativos e não apagados, para que quem os marcou no passado
continue com o histórico intacto. As cinco linhas novas do preçário passam a
serviços marcáveis.

O nome "Laserterapia (sessão)" leva o sufixo pela mesma razão que a Pedicure o
levou em 0030: dentro da categoria Laserterapia, um serviço com o nome da
categoria daria "Laserterapia → Laserterapia" no fluxo de marcação.
"""

from decimal import Decimal

from django.db import migrations

# nome atual -> campos a acertar
ATUALIZACOES = {
    "Pedicure Terapêutica (sessão)": {
        "price": Decimal("40.00"),
    },
    "Pé diabético (avaliação e tratamento)": {
        "price": Decimal("50.00"),
    },
    "Desencravamento de unha (espícula)": {
        "price": Decimal("40.00"),
        "description": (
            "Remoção da espícula da unha encravada, com abordagem conservadora "
            "e orientação preventiva. Desde 40 €, conforme a extensão e o "
            "estado da unha."
        ),
        "description_en": (
            "Removal of the ingrown nail spicule, with a conservative approach "
            "and preventive guidance. From €40, depending on the extent and "
            "condition of the nail."
        ),
    },
    "Tratamento de calo (desbaste e alívio da dor)": {
        "price": Decimal("25.00"),
    },
    "Remoção de calosidades": {
        "price": Decimal("35.00"),
        "description": (
            "Remoção de calosidades e pele espessada, com alívio do desconforto "
            "ao apoiar o pé. Desde 35 €, conforme a área tratada."
        ),
        "description_en": (
            "Removal of calluses and thickened skin, relieving discomfort when "
            "standing. From €35, depending on the area treated."
        ),
    },
    "Tratamento de verruga plantar": {
        "price": Decimal("50.00"),
        "description": (
            "Sessão de terapia fotodinâmica (PDT) para verruga plantar, com "
            "acompanhamento da evolução."
        ),
        "description_en": (
            "Photodynamic therapy (PDT) session for a plantar wart, with "
            "follow-up of its progress."
        ),
    },
    "Penso especializado / Laserterapia": {
        # A laserterapia avulsa passa a ter serviço próprio; este fica só com
        # o tratamento de lesões, que é o que o preçário separa.
        "name": "Tratamento de lesões / penso",
        "name_en": "Wound treatment / dressing",
        "price": Decimal("20.00"),
        "description": (
            "Tratamento de lesões do pé e penso especializado. Desde 20 €, "
            "conforme a área tratada e a complexidade."
        ),
        "description_en": (
            "Foot wound treatment and specialised dressing. From €20, depending "
            "on the area treated and the complexity."
        ),
    },
    "Onicomicose (fungo da unha)": {
        "price": Decimal("35.00"),
        "description": (
            "Desbaste da unha com laserterapia para onicomicose. Valor por "
            "sessão; o número de sessões depende da evolução do tratamento."
        ),
        "description_en": (
            "Nail debridement with laser therapy for onychomycosis. Price per "
            "session; the number of sessions depends on how the treatment "
            "progresses."
        ),
    },
    "Fissuras e lesões da pele": {
        "price": Decimal("30.00"),
        "description": (
            "Tratamento de fissuras com laserterapia. Entre 30 € e 35 € por "
            "sessão, conforme a extensão das fissuras."
        ),
        "description_en": (
            "Fissure treatment with laser therapy. Between €30 and €35 per "
            "session, depending on the extent of the fissures."
        ),
    },
}

# slug da categoria -> (nome, descrição, preço, nome_en, descrição_en)
NOVOS_SERVICOS = {
    "podologia": [
        (
            "Manutenção da órtese",
            "Revisão e ajuste da órtese ungueal já colocada. Entre 15 € e 20 €, "
            "conforme o ajuste necessário.",
            Decimal("15.00"),
            "Nail brace maintenance",
            "Review and adjustment of a nail brace already fitted. Between €15 "
            "and €20, depending on the adjustment needed.",
        ),
        (
            "Verruga plantar – protocolo inicial (5 sessões)",
            "Protocolo inicial de 5 sessões de PDT para verruga plantar, pago "
            "sessão a sessão.",
            Decimal("250.00"),
            "Plantar wart – initial protocol (5 sessions)",
            "Initial protocol of 5 PDT sessions for a plantar wart, paid "
            "session by session.",
        ),
        (
            "Verruga plantar – 5 sessões, pagamento antecipado",
            "As mesmas 5 sessões do protocolo inicial, com pagamento adiantado "
            "e valor mais vantajoso.",
            Decimal("200.00"),
            "Plantar wart – 5 sessions, paid in advance",
            "The same 5 sessions as the initial protocol, paid up front at a "
            "better rate.",
        ),
    ],
    "laserterapia": [
        (
            "Laserterapia (sessão)",
            "Sessão de laserterapia. Entre 20 € e 25 €, conforme a área "
            "tratada.",
            Decimal("20.00"),
            "Laser therapy (session)",
            "Laser therapy session. Between €20 and €25, depending on the area "
            "treated.",
        ),
    ],
}

# Deixaram de ser oferecidos. Inativos e não apagados: o histórico de quem os
# marcou continua ligado ao serviço certo.
DESATIVAR = ["ILIB", "Pacote ILIB (10 sessões)"]

DURACAO_UNIFORME = 60


def aplicar(apps, schema_editor):
    ServiceCategory = apps.get_model("appointments", "ServiceCategory")
    Service = apps.get_model("appointments", "Service")

    for nome, campos in ATUALIZACOES.items():
        Service.objects.filter(name=nome).update(**campos)

    for slug, definicoes in NOVOS_SERVICOS.items():
        categoria = ServiceCategory.objects.filter(slug=slug).first()

        if not categoria:
            continue

        for nome, descricao, preco, nome_en, descricao_en in definicoes:
            Service.objects.get_or_create(
                category=categoria,
                name=nome,
                defaults={
                    "description": descricao,
                    "duration_minutes": DURACAO_UNIFORME,
                    "price": preco,
                    "is_active": True,
                    "name_en": nome_en,
                    "description_en": descricao_en,
                },
            )

    Service.objects.filter(name__in=DESATIVAR).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0043_treatedcondition_hero_image_en"),
    ]

    operations = [
        # Sem reversão, como em 0011: desfazer devolveria uma tabela de preços
        # que já não é praticada e apagaria serviços que podem entretanto ter
        # marcações associadas.
        migrations.RunPython(aplicar, migrations.RunPython.noop),
    ]
