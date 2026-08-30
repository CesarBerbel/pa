"""O catálogo inglês tem de acompanhar as páginas públicas.

Este teste existe porque o problema que apanha não se vê a olhar: um texto
marcado com `{% translate %}` e sem entrada no catálogo **não rebenta** — sai
em português dentro de uma página inglesa, e continua a sair durante meses até
alguém reparar.

Aconteceu: páginas inteiras foram acrescentadas ao site com o texto todo
marcado e nenhuma tradução escrita, e ninguém deu por isso porque a página
continuava a desenhar-se.

Só as páginas públicas. A área interna é em português por decisão — quem a usa
fala português, e traduzi-la seria trabalho para ninguém.
"""

import os
import re

from django.test import TestCase

TEMPLATES = "templates"
CATALOGO = "locale/en/LC_MESSAGES/django.po"

# A área interna, que não se traduz. É uma lista de prefixos e não uma regra
# esperta: uma regra esperta engana-se em silêncio, e um nome novo que caia no
# lado errado é uma linha a acrescentar aqui.
AREA_INTERNA = (
    "templates/appointments/appointment_",
    "templates/appointments/business_hour",
    "templates/appointments/clinical_note",
    "templates/appointments/condition_admin",
    "templates/appointments/customer_",
    "templates/appointments/before_after_form",
    "templates/appointments/before_after_list",
    "templates/appointments/before_after_confirm",
    "templates/appointments/daily_agenda",
    "templates/appointments/monthly_schedule",
    "templates/appointments/patient_record",
    "templates/appointments/return_visit",
    "templates/appointments/schedule_",
    "templates/appointments/scheduling_",
    "templates/appointments/service_",
    "templates/appointments/visual_schedule",
    "templates/appointments/weekly_schedule",
    "templates/appointments/_agenda",
    "templates/appointments/_send_message",
    "templates/finance/",
    "templates/config/",
    "templates/notifications/",
    "templates/admin/",
    "templates/accounts/passkey",
    "templates/registration/",
    "templates/dashboard.html",
)

MARCA_SIMPLES = re.compile(r"\{%\s*(?:translate|trans)\s+\"([^\"]+)\"")
MARCA_BLOCO = re.compile(
    r"\{%\s*blocktranslate[^%]*%\}(.*?)\{%\s*endblocktranslate\s*%\}",
    re.DOTALL,
)

# Um msgid pode ter aspas escapadas lá dentro — as páginas legais estão cheias
# delas, por causa dos `<a href="...">`. Com `[^"]*` a entrada era cortada ao
# meio e dava por não existir.
ASPAS = re.compile(r'"((?:[^"\\]|\\.)*)"')

BLOCOS_DE_CABECA = re.compile(
    r"\{%\s*block\s+(title|meta_description|meta_keywords|og_title"
    r"|og_description|twitter_title|twitter_description)\s*%\}(.*?)"
    r"\{%\s*endblock\s*%\}",
    re.DOTALL,
)


def e_interna(caminho):
    return any(caminho.replace("\\", "/").startswith(p) for p in AREA_INTERNA)


def templates_publicos():
    for raiz, _, nomes in os.walk(TEMPLATES):
        for nome in nomes:
            if not nome.endswith(".html"):
                continue

            caminho = os.path.join(raiz, nome)

            if not e_interna(caminho):
                yield caminho


def como_msgid(texto):
    """Do texto do template para a forma que o catálogo guarda.

    O `{{ nome }}` do Django é escrito `%(nome)s` no `.po`, e uma forma plural
    entra como duas entradas.
    """

    texto = re.sub(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}", r"%(\1)s", texto)

    return [parte.strip() for parte in re.split(r"\{%\s*plural\s*%\}", texto)]


class PublicPagesAreFullyTranslatedTests(TestCase):
    def catalogo(self, com_plurais=True):
        """As entradas do `.po`.

        `com_plurais` desliga as linhas `msgid_plural`. Elas contam para saber
        se um texto está traduzido, mas não são chaves do catálogo compilado —
        lá dentro um plural vive sob o singular, indexado pela forma.
        """

        s = open(CATALOGO, encoding="utf-8").read()
        entradas = set()

        marca = r"^msgid(?:_plural)? " if com_plurais else r"^msgid "

        for m in re.finditer(
            marca + r"((?:" + ASPAS.pattern + r"\s*)+)",
            s,
            re.MULTILINE,
        ):
            partes = ASPAS.findall(m.group(1))
            entradas.add("".join(partes).replace('\\"', '"'))

        return entradas

    def marcados(self):
        encontrados = {}

        for caminho in templates_publicos():
            texto = open(caminho, encoding="utf-8").read()

            for m in MARCA_SIMPLES.finditer(texto):
                for parte in como_msgid(m.group(1)):
                    encontrados.setdefault(parte, set()).add(caminho)

            for m in MARCA_BLOCO.finditer(texto):
                for parte in como_msgid(m.group(1).strip()):
                    encontrados.setdefault(parte, set()).add(caminho)

        return encontrados

    def test_every_marked_string_has_an_english_translation(self):
        catalogo = self.catalogo()

        em_falta = {
            texto: ficheiros
            for texto, ficheiros in self.marcados().items()
            if texto not in catalogo
        }

        if em_falta:
            linhas = [
                f"  {texto[:70]!r}\n      {', '.join(sorted(ficheiros))}"
                for texto, ficheiros in sorted(em_falta.items())
            ]

            self.fail(
                f"{len(em_falta)} texto(s) marcados para tradução sem entrada "
                f"no catálogo inglês.\n\n"
                + "\n".join(linhas)
                + "\n\nAcrescente-os a "
                + CATALOGO
                + " e recompile o .mo."
            )

    def test_no_public_title_is_written_by_hand(self):
        """O separador do browser e o resultado no Google contam.

        São a primeira coisa que quem procura em inglês vê da página — muitas
        vezes antes de lhe tocar — e eram a parte que ficava em português sem
        ninguém reparar, porque não se lê a página para os ver.
        """

        por_marcar = []

        for caminho in templates_publicos():
            texto = open(caminho, encoding="utf-8").read()

            for m in BLOCOS_DE_CABECA.finditer(texto):
                conteudo = m.group(2).strip()

                if not conteudo:
                    continue

                # Traduzido, ou vindo de uma variável: os dois estão bem.
                if "translate" in conteudo or conteudo.startswith("{{"):
                    continue

                por_marcar.append(f"  {caminho} [{m.group(1)}]: {conteudo[:60]}")

        if por_marcar:
            self.fail(
                "Títulos ou meta tags públicos escritos à mão, sem "
                "{% translate %}:\n\n" + "\n".join(sorted(por_marcar))
            )

    def test_the_compiled_catalogue_is_not_behind_the_source(self):
        """O `.po` é o que se edita; o `.mo` é o que o site lê.

        Editar um e esquecer o outro é o erro silencioso desta dupla: o
        catálogo diz uma coisa e a página mostra outra, e não há nada no ecrã
        que o denuncie.
        """

        import gettext

        with open("locale/en/LC_MESSAGES/django.mo", "rb") as ficheiro:
            compilado = gettext.GNUTranslations(ficheiro)._catalog

        fonte = self.catalogo(com_plurais=False)

        # Um plural não vive no catálogo compilado sob o seu msgid: vive sob
        # `(msgid, forma)`. Procurá-lo pela string dava-o por desaparecido.
        def esta_la(texto):
            return texto in compilado or (texto, 0) in compilado

        # O cabeçalho fica de fora: é metadados, não uma frase.
        em_falta = [texto for texto in fonte if texto and not esta_la(texto)]

        self.assertEqual(
            em_falta[:5],
            [],
            f"{len(em_falta)} entradas estão no .po e não no .mo compilado. "
            "Recompile as traduções.",
        )
