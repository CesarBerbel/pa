"""Extração e compilação de traduções sem depender do GNU gettext.

O projeto corre em Windows, onde `xgettext`/`msgfmt` normalmente não existem, e
por isso `manage.py makemessages` e `compilemessages` falham. Estas duas
funções cobrem o que o projeto precisa:

    python scripts/i18n_tools.py extract    # atualiza locale/<lang>/LC_MESSAGES/django.po
    python scripts/i18n_tools.py compile    # gera o django.mo lido pelo Django

`extract` preserva as traduções já escritas e marca como obsoletas as que
deixaram de aparecer no código. `compile` escreve o formato .mo binário
documentado pelo GNU gettext.
"""

from __future__ import annotations

import array
import re
import struct
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALE_DIR = BASE_DIR / "locale"

# Idiomas gerados. O português é o idioma de origem e não precisa de catálogo.
TARGET_LANGUAGES = ["en"]

SCAN_DIRECTORIES = [
    BASE_DIR / "templates",
    BASE_DIR / "accounts",
    BASE_DIR / "appointments",
    BASE_DIR / "config",
    BASE_DIR / "notifications",
]

SCAN_SUFFIXES = {".html", ".py"}

EXCLUDED_PARTS = {"__pycache__", "migrations", ".venv", "node_modules"}

TEMPLATE_TAG_PATTERN = re.compile(
    r"{%\s*(?:translate|trans)\s+(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')",
)

PYTHON_CALL_PATTERN = re.compile(
    r"(?:gettext_lazy|gettext|pgettext|_)\(\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')",
)

PO_HEADER = """msgid ""
msgstr ""
"Project-Id-Version: pa\\n"
"Report-Msgid-Bugs-To: \\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Language: {language}\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"
"""


def unquote_literal(literal: str) -> str:
    # Converte o literal tal como aparece no ficheiro para o texto real.
    body = literal[1:-1]
    return body.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")


def escape_for_po(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def iter_source_files():
    for directory in SCAN_DIRECTORIES:
        if not directory.exists():
            continue

        for path in sorted(directory.rglob("*")):
            if path.suffix not in SCAN_SUFFIXES:
                continue

            if EXCLUDED_PARTS.intersection(path.parts):
                continue

            yield path


def collect_messages() -> dict[str, list[str]]:
    # Devolve {texto_original: [referencias ficheiro:linha]}.
    messages: dict[str, list[str]] = {}

    for path in iter_source_files():
        relative = path.relative_to(BASE_DIR).as_posix()
        pattern = (
            TEMPLATE_TAG_PATTERN if path.suffix == ".html" else PYTHON_CALL_PATTERN
        )

        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for match in pattern.finditer(line):
                text = unquote_literal(match.group(1))

                if not text.strip():
                    continue

                messages.setdefault(text, []).append(f"{relative}:{number}")

    return messages


def parse_po(path: Path) -> dict[str, str]:
    # Leitura tolerante: só precisamos dos pares msgid/msgstr já traduzidos.
    if not path.exists():
        return {}

    catalog: dict[str, str] = {}
    current_key = None
    current_target: list[str] = []
    collecting = None

    def flush():
        if current_key is not None and collecting == "msgstr":
            catalog[current_key] = "".join(current_target)

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if line.startswith("#") or not line:
            continue

        if line.startswith("msgid "):
            flush()
            current_key = unquote_literal(line[len("msgid ") :].strip())
            current_target = []
            collecting = "msgid"
        elif line.startswith("msgstr "):
            current_target = [unquote_literal(line[len("msgstr ") :].strip())]
            collecting = "msgstr"
        elif line.startswith('"') and collecting:
            chunk = unquote_literal(line)
            if collecting == "msgid":
                current_key = (current_key or "") + chunk
            else:
                current_target.append(chunk)

    flush()
    catalog.pop("", None)

    return catalog


def write_po(path: Path, language: str, messages: dict[str, list[str]], existing):
    lines = [PO_HEADER.format(language=language)]

    for text in sorted(messages):
        for reference in messages[text]:
            lines.append(f"#: {reference}")

        translation = existing.get(text, "")
        lines.append(f'msgid "{escape_for_po(text)}"')
        lines.append(f'msgstr "{escape_for_po(translation)}"')
        lines.append("")

    obsolete = sorted(set(existing) - set(messages))

    if obsolete:
        lines.append("# Entradas que já não aparecem no código:")
        for text in obsolete:
            lines.append(f'#~ msgid "{escape_for_po(text)}"')
            lines.append(f'#~ msgstr "{escape_for_po(existing[text])}"')
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_mo(catalog: dict[str, str], language: str) -> bytes:
    # Formato .mo do GNU gettext. A entrada de msgid vazio carrega os cabeçalhos
    # e é o que informa o charset ao runtime.
    headers = (
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        f"Language: {language}\n"
        "Plural-Forms: nplurals=2; plural=(n != 1);\n"
    )

    entries = {b"": headers.encode("utf-8")}

    for text, translation in catalog.items():
        if translation:
            entries[text.encode("utf-8")] = translation.encode("utf-8")

    keys = sorted(entries)
    offsets = []
    ids = b""
    targets = b""

    for key in keys:
        value = entries[key]
        offsets.append((len(ids), len(key), len(targets), len(value)))
        ids += key + b"\x00"
        targets += value + b"\x00"

    key_table_start = 7 * 4 + 16 * len(keys)
    value_table_start = key_table_start + len(ids)

    key_offsets = []
    value_offsets = []

    for id_offset, id_length, target_offset, target_length in offsets:
        key_offsets += [id_length, id_offset + key_table_start]
        value_offsets += [target_length, target_offset + value_table_start]

    output = struct.pack(
        "Iiiiiii",
        0x950412DE,  # número mágico
        0,  # revisão do formato
        len(keys),
        7 * 4,  # início da tabela de originais
        7 * 4 + len(keys) * 8,  # início da tabela de traduções
        0,  # tamanho da tabela de hash
        0,  # posição da tabela de hash
    )
    output += array.array("i", key_offsets + value_offsets).tobytes()
    output += ids
    output += targets

    return output


def command_extract() -> int:
    messages = collect_messages()

    for language in TARGET_LANGUAGES:
        po_path = LOCALE_DIR / language / "LC_MESSAGES" / "django.po"
        existing = parse_po(po_path)
        write_po(po_path, language, messages, existing)

        traduzidas = sum(1 for text in messages if existing.get(text))
        print(
            f"{po_path.relative_to(BASE_DIR)}: "
            f"{len(messages)} entradas, {traduzidas} traduzidas, "
            f"{len(messages) - traduzidas} por traduzir"
        )

    return 0


def command_compile() -> int:
    for language in TARGET_LANGUAGES:
        po_path = LOCALE_DIR / language / "LC_MESSAGES" / "django.po"

        if not po_path.exists():
            print(f"{po_path.relative_to(BASE_DIR)}: não existe, correr extract antes")
            return 1

        catalog = parse_po(po_path)
        mo_path = po_path.with_suffix(".mo")
        mo_path.write_bytes(build_mo(catalog, language))

        traduzidas = sum(1 for value in catalog.values() if value)
        print(f"{mo_path.relative_to(BASE_DIR)}: {traduzidas} traduções compiladas")

    return 0


def main(argv: list[str]) -> int:
    comandos = {"extract": command_extract, "compile": command_compile}

    if len(argv) != 2 or argv[1] not in comandos:
        print(__doc__)
        return 1

    return comandos[argv[1]]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
