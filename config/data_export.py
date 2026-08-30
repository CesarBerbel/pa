"""Levar tudo o que a casa sabe para outro sistema.

Não é uma cópia de segurança. Uma cópia de segurança serve para repor **este**
sistema e só este a entende; isto serve para **sair** dele — para uma folha de
cálculo, para um software de gestão de clínicas, para o programa de
contabilidade de quem faz as contas.

As decisões de formato existem todas por causa disso:

* **CSV**, um ficheiro por entidade, tudo dentro de um `.zip`. É o único
  formato que qualquer sistema lê sem se combinar nada com ninguém.
* **Datas em ISO** (`2026-08-30`, `14:30`). `30/08/2026` e `08/30/2026` são o
  mesmo texto para o computador e dias diferentes para quem os lê, e uma
  importação silenciosamente errada é o pior fim que estes dados podem ter.
* **Números com ponto decimal** (`27.50`) e **vírgula a separar colunas**. É o
  contrário do que o Excel português espera, e é de propósito: o destino é um
  importador, não um ecrã. O `LEIA-ME.txt` explica como abrir no Excel a quem
  quiser abrir no Excel.
* **UTF-8 com BOM**. Sem o BOM, "João" chega ao outro lado como "JoÃ£o" — e
  quem precisa dele é o Excel, que os importadores ignoram-no.
* **Estados nas duas formas**: o código (`completed`) para quem importa, o nome
  (`Concluída`) para quem lê. Só o código obriga a adivinhar; só o nome obriga
  a traduzir de volta.

Cada ficheiro leva a coluna `id`, e quem aponta para ele aponta por esse `id`.
São as chaves desta base de dados: não têm significado lá fora, mas são o que
mantém as marcações ligadas às clientes depois de saírem daqui.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile

from django.utils import timezone

from appointments.models import (
    Appointment,
    ClinicalNote,
    Customer,
    PatientRecord,
    ReturnVisit,
    Service,
)
from finance.models import Expense, Payment

logger = logging.getLogger("config")


def _data(valor):
    return valor.isoformat() if valor else ""


def _momento(valor):
    """Um `datetime` em hora local, sem segundos.

    Guardados em UTC, mostrados em Lisboa. Exportar o UTC em bruto punha as
    marcações da manhã no dia anterior durante o horário de verão.
    """

    if not valor:
        return ""

    return timezone.localtime(valor).strftime("%Y-%m-%d %H:%M")


def _sim_nao(valor):
    return "sim" if valor else "não"


def _quem(utilizador):
    return utilizador.full_name if utilizador else ""


# =============================================================================
# As tabelas
# =============================================================================
#
# Cada função devolve (cabeçalho, linhas). Nenhuma delas sabe o que é um CSV
# nem o que é um pedido HTTP: são consultas, e é isso que as torna testáveis
# linha a linha em vez de por dentro de um ficheiro comprimido.


def clientes():
    cabecalho = [
        "id",
        "nome",
        "email",
        "telefone",
        "idioma",
        "sem_conta_no_site",
        "email_da_conta",
        "criado_em",
    ]

    linhas = [
        [
            cliente.id,
            cliente.full_name,
            cliente.email,
            cliente.phone,
            cliente.language,
            _sim_nao(cliente.is_guest),
            cliente.user.email if cliente.user else "",
            _momento(cliente.created_at),
        ]
        for cliente in Customer.objects.select_related("user").order_by("id")
    ]

    return cabecalho, linhas


def servicos():
    cabecalho = [
        "id",
        "categoria",
        "nome",
        "nome_en",
        "descricao",
        "duracao_minutos",
        "preco",
        "dias_ate_retorno",
        "ativo",
    ]

    linhas = [
        [
            servico.id,
            servico.category.name if servico.category else "",
            servico.name,
            servico.name_en,
            servico.description,
            servico.duration_minutes,
            servico.price,
            servico.return_days,
            _sim_nao(servico.is_active),
        ]
        for servico in Service.objects.select_related("category").order_by("id")
    ]

    return cabecalho, linhas


def marcacoes():
    """As marcações, com o nome da cliente e do serviço já escritos ao lado.

    Repetido de propósito: o `id` é que liga os ficheiros, mas um ficheiro em
    que só se lê `cliente_id: 47` é ilegível para quem o abre para conferir a
    importação — e conferir é o que se faz a seguir a importar.
    """

    cabecalho = [
        "id",
        "referencia",
        "cliente_id",
        "cliente_nome",
        "servico_id",
        "servico_nome",
        "data",
        "hora",
        "estado",
        "estado_codigo",
        "ao_domicilio",
        "morada",
        "fala_ingles",
        "origem",
        "fora_do_horario",
        "observacoes",
        "motivo_de_cancelamento",
        "cancelada_em",
        "criada_em",
        "criada_por",
    ]

    linhas = [
        [
            marcacao.id,
            marcacao.reference_code,
            marcacao.customer_id,
            marcacao.customer.full_name,
            marcacao.service_id,
            marcacao.service.name,
            _data(marcacao.date),
            marcacao.start_time.strftime("%H:%M"),
            marcacao.get_status_display(),
            marcacao.status,
            _sim_nao(marcacao.is_home_visit),
            marcacao.home_address if marcacao.is_home_visit else "",
            _sim_nao(marcacao.customer_speaks_english),
            marcacao.origin,
            _sim_nao(marcacao.outside_schedule),
            marcacao.notes,
            marcacao.cancellation_reason,
            _momento(marcacao.cancelled_at),
            _momento(marcacao.created_at),
            _quem(marcacao.created_by),
        ]
        for marcacao in Appointment.objects.select_related(
            "customer", "service", "created_by"
        ).order_by("id")
    ]

    return cabecalho, linhas


def retornos():
    cabecalho = [
        "id",
        "cliente_id",
        "cliente_nome",
        "servico_nome",
        "marcacao_de_origem_id",
        "data_prevista",
        "estado",
        "estado_codigo",
        "marcacao_agendada_id",
        "notas",
        "criado_em",
    ]

    linhas = [
        [
            retorno.id,
            retorno.customer_id,
            retorno.customer.full_name,
            retorno.service.name if retorno.service else "",
            retorno.origin_id or "",
            _data(retorno.target_date),
            retorno.get_status_display(),
            retorno.status,
            retorno.appointment_id or "",
            retorno.notes,
            _momento(retorno.created_at),
        ]
        for retorno in ReturnVisit.objects.select_related(
            "customer", "service"
        ).order_by("id")
    ]

    return cabecalho, linhas


def pagamentos():
    cabecalho = [
        "id",
        "marcacao_id",
        "cliente_nome",
        "data",
        "valor",
        "metodo",
        "metodo_codigo",
        "percentagem_de_reinvestimento",
        "notas",
    ]

    linhas = [
        [
            pagamento.id,
            pagamento.appointment_id,
            pagamento.appointment.customer.full_name,
            _data(pagamento.paid_on),
            pagamento.amount,
            pagamento.get_method_display(),
            pagamento.method,
            pagamento.reinvestment_percent,
            pagamento.notes,
        ]
        for pagamento in Payment.objects.select_related(
            "appointment__customer"
        ).order_by("id")
    ]

    return cabecalho, linhas


def despesas():
    cabecalho = [
        "id",
        "data",
        "categoria",
        "categoria_codigo",
        "descricao",
        "valor",
        "notas",
    ]

    linhas = [
        [
            despesa.id,
            _data(despesa.spent_on),
            despesa.get_category_display(),
            despesa.category,
            despesa.description,
            despesa.amount,
            despesa.notes,
        ]
        for despesa in Expense.objects.order_by("id")
    ]

    return cabecalho, linhas


def fichas_clinicas():
    cabecalho = [
        "id",
        "cliente_id",
        "cliente_nome",
        "data_de_nascimento",
        "profissao",
        "queixa_principal",
        "diabetes",
        "problemas_circulatorios",
        "problemas_cardiovasculares",
        "hipertensao",
        "neuropatia",
        "problemas_de_coagulacao",
        "doenca_reumatica",
        "doenca_da_tiroide",
        "doenca_renal",
        "problema_de_pele",
        "gravidez",
        "tem_alergias",
        "fumadora",
        "alergias",
        "historico_clinico",
        "medicacao_atual",
        "cirurgias_anteriores",
        "calcado",
        "avaliacao_da_pele",
        "avaliacao_das_unhas",
        "deformidades",
        "avaliacao_vascular",
        "avaliacao_neurologica",
        "avaliacao_da_marcha",
        "risco_podologico",
        "plano_de_tratamento",
        "consentimento_confirmado",
        "observacoes",
        "atualizada_em",
    ]

    linhas = [
        [
            ficha.id,
            ficha.customer_id,
            ficha.customer.full_name,
            _data(ficha.birth_date),
            ficha.profession,
            ficha.main_complaint,
            _sim_nao(ficha.has_diabetes),
            _sim_nao(ficha.has_circulatory_issues),
            _sim_nao(ficha.has_cardiovascular_issues),
            _sim_nao(ficha.has_hypertension),
            _sim_nao(ficha.has_neuropathy),
            _sim_nao(ficha.has_coagulation_issues),
            _sim_nao(ficha.has_rheumatic_disease),
            _sim_nao(ficha.has_thyroid_disease),
            _sim_nao(ficha.has_kidney_disease),
            _sim_nao(ficha.has_skin_condition),
            _sim_nao(ficha.is_pregnant),
            _sim_nao(ficha.has_allergies),
            _sim_nao(ficha.is_smoker),
            ficha.allergies,
            ficha.medical_history,
            ficha.current_medication,
            ficha.previous_surgeries,
            ficha.footwear_notes,
            ficha.skin_assessment,
            ficha.nail_assessment,
            ficha.foot_deformities,
            ficha.vascular_assessment,
            ficha.neurological_assessment,
            ficha.gait_assessment,
            ficha.get_diabetic_foot_risk_display(),
            ficha.treatment_plan,
            _sim_nao(ficha.consent_confirmed),
            ficha.notes,
            _momento(ficha.updated_at),
        ]
        for ficha in PatientRecord.objects.select_related("customer").order_by("id")
    ]

    return cabecalho, linhas


def notas_clinicas():
    cabecalho = [
        "id",
        "marcacao_id",
        "cliente_id",
        "cliente_nome",
        "data_do_atendimento",
        "procedimentos",
        "observacoes",
        "recomendacoes",
        "escrita_por",
        "criada_em",
    ]

    linhas = [
        [
            nota.id,
            nota.appointment_id,
            nota.appointment.customer_id,
            nota.appointment.customer.full_name,
            _data(nota.appointment.date),
            nota.procedures,
            nota.observations,
            nota.recommendations,
            _quem(nota.created_by),
            _momento(nota.created_at),
        ]
        for nota in ClinicalNote.objects.select_related(
            "appointment__customer", "created_by"
        ).order_by("id")
    ]

    return cabecalho, linhas


# O `True` do meio marca o que é clínico, e é isso que decide quem pode levar o
# quê. A separação já existe no sistema — a área interna vê a agenda, só quem
# tem acesso clínico vê a anamnese — e um export que a ignorasse era a porta
# das traseiras dessa regra.
TABELAS = [
    ("clientes.csv", False, clientes),
    ("servicos.csv", False, servicos),
    ("marcacoes.csv", False, marcacoes),
    ("retornos.csv", False, retornos),
    ("pagamentos.csv", False, pagamentos),
    ("despesas.csv", False, despesas),
    ("fichas_clinicas.csv", True, fichas_clinicas),
    ("notas_clinicas.csv", True, notas_clinicas),
]


def tabelas_para(clinico: bool):
    return [tabela for tabela in TABELAS if clinico or not tabela[1]]


def _csv(cabecalho, linhas) -> bytes:
    """Um CSV em memória, em UTF-8 com BOM.

    O `lineterminator` fica explícito porque o valor por omissão do módulo
    `csv` depende de para onde se escreve, e um ficheiro que muda de fim de
    linha conforme a máquina que o gerou é um ficheiro que um dia falha na
    importação sem se perceber porquê.
    """

    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, lineterminator="\r\n")

    escritor.writerow(cabecalho)
    escritor.writerows(linhas)

    return buffer.getvalue().encode("utf-8-sig")


LEIA_ME = """EXPORTAÇÃO DE DADOS — {data}
{sublinhado}

Um ficheiro por entidade, em CSV, para levar estes dados para outro sistema.

O QUE ESTÁ AQUI
{indice}

COMO OS FICHEIROS SE LIGAM
    Cada ficheiro tem uma coluna "id". As colunas que acabam em "_id"
    apontam para o "id" de outro ficheiro:

        marcacoes.cliente_id        -> clientes.id
        marcacoes.servico_id        -> servicos.id
        pagamentos.marcacao_id      -> marcacoes.id
        retornos.cliente_id         -> clientes.id
        retornos.marcacao_de_origem_id  -> marcacoes.id
        retornos.marcacao_agendada_id   -> marcacoes.id
        fichas_clinicas.cliente_id  -> clientes.id
        notas_clinicas.marcacao_id  -> marcacoes.id

    Importe primeiro clientes e servicos, que as marcacoes precisam dos
    dois. Depois marcacoes. Só depois pagamentos, retornos e notas
    clinicas.

O FORMATO
    Codificacao   UTF-8 com BOM
    Separador     virgula
    Datas         AAAA-MM-DD          (ex.: 2026-08-30)
    Horas         HH:MM em 24 horas   (ex.: 14:30)
    Data e hora   AAAA-MM-DD HH:MM, na hora de Portugal continental
    Numeros       ponto decimal       (ex.: 27.50)
    Valores       em euros

    Os estados vem em duas colunas: "estado" com o nome que se le e
    "estado_codigo" com o valor guardado. Para importar, use o codigo.

PARA ABRIR NO EXCEL
    Nao faca duplo clique: o Excel portugues espera ponto e virgula e vai
    juntar tudo numa coluna so. Use Dados > Obter dados > De ficheiro >
    De texto/CSV, e escolha a virgula como separador.

PROTECAO DE DADOS
    Estes ficheiros tem nomes, contactos e moradas de pessoas
    identificaveis{clinico}. Guarde-os cifrados, envie-os por um canal
    seguro e apague-os quando a migracao estiver conferida.
"""


def _leia_me(nomes, clinico: bool) -> bytes:
    hoje = timezone.localdate().isoformat()

    indice = "\n".join(f"    {nome}" for nome in nomes)

    if clinico:
        aviso = (
            ", e ainda dados de saude: as fichas clinicas e as notas de "
            "evolucao, que sao dados de categoria especial"
        )
    else:
        aviso = ". Os dados clinicos nao foram incluidos nesta exportacao"

    texto = LEIA_ME.format(
        data=hoje,
        sublinhado="=" * (len(hoje) + 24),
        indice=indice,
        clinico=aviso,
    )

    return texto.encode("utf-8")


def construir(clinico: bool = False) -> bytes:
    """O `.zip` inteiro, em memória.

    Em memória e não em disco porque é para descarregar e não para guardar: um
    ficheiro temporário no servidor com a lista de clientes toda é exatamente
    o que não se quer deixar para trás.

    E cabe: são ficheiros de texto de uma clínica de uma pessoa. Se um dia esta
    função ficar pesada, é sinal de que passou a haver dados a mais para a
    fazer assim — e aí escreve-se em streaming para um ficheiro temporário.
    """

    tabelas = tabelas_para(clinico)

    saida = io.BytesIO()

    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as ficheiro_zip:
        for nome, _, funcao in tabelas:
            cabecalho, linhas = funcao()
            ficheiro_zip.writestr(nome, _csv(cabecalho, linhas))

        ficheiro_zip.writestr(
            "LEIA-ME.txt", _leia_me([tabela[0] for tabela in tabelas], clinico)
        )

    return saida.getvalue()


def nome_do_ficheiro() -> str:
    return f"exportacao-{timezone.localdate().isoformat()}.zip"


def registar(utilizador, clinico: bool) -> None:
    """Deixar rasto de quem levou os dados, e quando.

    Uma exportação tira tudo o que há sobre pessoas identificáveis e sai do
    sistema sem deixar marca nos registos normais, que são por marcação e por
    ficha. Este aviso é a única prova de que aconteceu.
    """

    logger.warning(
        "Exportação de dados por %s — dados clínicos incluídos: %s",
        getattr(utilizador, "email", "desconhecido"),
        "sim" if clinico else "não",
    )
