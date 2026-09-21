"""Contenido de un documento ofimático, común a todos los formatos.

El modelo (o el código que exporta datos) describe el documento como una lista de bloques
sencillos y cada renderizador decide cómo se ven en Excel, Word, PowerPoint u ODF:

* ``{"type": "heading", "text": "...", "level": 1}``: en presentaciones, un título de
  nivel 1 abre una diapositiva nueva.
* ``{"type": "paragraph", "text": "texto con **negrita**"}``
* ``{"type": "bullets", "items": ["...", "..."]}``
* ``{"type": "table", "name": "Tareas", "columns": [...], "rows": [[...], ...],
  "total": false}``: en hojas de cálculo cada tabla es una hoja; ``total`` añade una
  fila con la suma de las columnas numéricas.
"""

import re
from dataclasses import dataclass, field

from packages.core.errors import ValidationFailedError

FORMATS = ("xlsx", "docx", "pptx", "ods", "odt", "odp")
SPREADSHEETS = ("xlsx", "ods")

# Límites para que una petición mal formada no deje sin memoria al servidor MCP.
MAX_BLOCKS = 300
MAX_TEXT = 20_000
MAX_COLUMNS = 50
MAX_ROWS = 10_000

Cell = str | int | float | None

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_INT = re.compile(r"-?\d{1,15}")
_DECIMAL = re.compile(r"-?\d{1,15}[.,]\d{1,10}")
# Fórmulas aceptadas: aritmética, rangos y funciones, sin referencias externas (`!`, `[`),
# DDE (`|`) ni cadenas; lo demás que empiece por `=` se guarda como texto literal.
_SAFE_FORMULA = re.compile(r"=[A-Za-z0-9_:+\-*/(),.;$<>= %]{1,500}")


@dataclass(frozen=True, slots=True)
class Formula:
    """Fórmula de hoja de cálculo en notación A1 (``=SUM(B2:B5)``)."""

    text: str


@dataclass(frozen=True, slots=True)
class Block:
    kind: str
    text: str = ""
    level: int = 1
    items: list[str] = field(default_factory=list)
    name: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[Cell | Formula]] = field(default_factory=list)
    total: bool = False


def bold_runs(text: str) -> list[tuple[str, bool]]:
    """Parte ``texto **negrita** más`` en tramos (texto, es_negrita)."""
    runs: list[tuple[str, bool]] = []
    pos = 0
    for match in _BOLD.finditer(text):
        if match.start() > pos:
            runs.append((text[pos : match.start()], False))
        runs.append((match.group(1), True))
        pos = match.end()
    if pos < len(text):
        runs.append((text[pos:], False))
    return runs or [("", False)]


def plain(text: str) -> str:
    return _BOLD.sub(r"\1", text)


def coerce_cell(value: object, *, allow_formulas: bool) -> Cell | Formula:
    """Números como números (también ``"12,5"``), fórmulas seguras como `Formula` y el
    resto como texto. Con ``allow_formulas=False`` (datos de fuera, p. ej. OpenProject)
    nada se interpreta como fórmula."""
    if value is None or isinstance(value, bool):
        return None if value is None else ("Sí" if value else "No")
    if isinstance(value, int | float):
        return value
    text = str(value).strip()[:MAX_TEXT]
    if _INT.fullmatch(text):
        return int(text)
    if _DECIMAL.fullmatch(text):
        return float(text.replace(",", "."))
    if allow_formulas and _SAFE_FORMULA.fullmatch(text) and '"' not in text:
        return Formula(text)
    return text


def _text(raw: dict, key: str) -> str:
    value = raw.get(key, "")
    if not isinstance(value, str | int | float):
        raise ValidationFailedError(f"«{key}» debe ser texto.")
    return str(value)[:MAX_TEXT]


def parse_blocks(raw_blocks: object, *, allow_formulas: bool = True) -> list[Block]:
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise ValidationFailedError("El documento necesita al menos un bloque de contenido.")
    if len(raw_blocks) > MAX_BLOCKS:
        raise ValidationFailedError(f"Demasiados bloques (máximo {MAX_BLOCKS}).")
    blocks: list[Block] = []
    for index, raw in enumerate(raw_blocks, start=1):
        if not isinstance(raw, dict):
            raise ValidationFailedError(f"El bloque {index} no es un objeto.")
        kind = str(raw.get("type", "")).strip().lower()
        if kind == "heading":
            level = raw.get("level", 1)
            level = level if isinstance(level, int) and 1 <= level <= 3 else 1
            blocks.append(Block("heading", text=_text(raw, "text"), level=level))
        elif kind == "paragraph":
            blocks.append(Block("paragraph", text=_text(raw, "text")))
        elif kind == "bullets":
            items = raw.get("items")
            if not isinstance(items, list) or not items:
                raise ValidationFailedError(f"El bloque {index} (bullets) necesita «items».")
            blocks.append(Block("bullets", items=[str(i)[:MAX_TEXT] for i in items[:MAX_ROWS]]))
        elif kind == "table":
            blocks.append(_parse_table(raw, index, allow_formulas=allow_formulas))
        else:
            raise ValidationFailedError(
                f"Tipo de bloque desconocido en el bloque {index}: «{kind}». "
                "Usa heading, paragraph, bullets o table."
            )
    return blocks


def _parse_table(raw: dict, index: int, *, allow_formulas: bool) -> Block:
    columns = raw.get("columns")
    rows = raw.get("rows")
    if not isinstance(columns, list) or not columns or len(columns) > MAX_COLUMNS:
        raise ValidationFailedError(
            f"El bloque {index} (table) necesita «columns» (entre 1 y {MAX_COLUMNS})."
        )
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValidationFailedError(f"El bloque {index} (table) necesita «rows» (máx. {MAX_ROWS}).")
    width = len(columns)
    parsed_rows: list[list[Cell | Formula]] = []
    for row in rows:
        cells = row if isinstance(row, list) else [row]
        cells = (list(cells) + [None] * width)[:width]
        parsed_rows.append([coerce_cell(c, allow_formulas=allow_formulas) for c in cells])
    return Block(
        "table",
        name=_text(raw, "name")[:31],
        columns=[str(c)[:200] for c in columns],
        rows=parsed_rows,
        total=bool(raw.get("total", False)),
    )


def numeric_columns(block: Block) -> list[int]:
    """Columnas cuyas celdas con valor son todas numéricas (candidatas a total)."""
    result = []
    for col in range(len(block.columns)):
        values = [row[col] for row in block.rows if row[col] not in (None, "")]
        if values and all(isinstance(v, int | float) for v in values):
            result.append(col)
    return result


def column_sum(block: Block, col: int) -> int | float:
    return sum(v for row in block.rows if isinstance(v := row[col], int | float))


def formula_for_ods(formula: Formula) -> str:
    """``=SUM(B2:B5)`` → ``of:=SUM([.B2:.B5])`` (OpenFormula, separador `;`)."""
    body = formula.text[1:].replace(",", ";")
    body = re.sub(
        r"(\$?[A-Z]{1,3}\$?\d{1,7})(?::(\$?[A-Z]{1,3}\$?\d{1,7}))?",
        lambda m: f"[.{m.group(1)}" + (f":.{m.group(2)}]" if m.group(2) else "]"),
        body,
    )
    return f"of:={body}"


def column_letter(index: int) -> str:
    """0 → A, 25 → Z, 26 → AA."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
