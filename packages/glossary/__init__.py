"""Glosario de gestión de proyectos español ↔ inglés (docs/GLOSARIO.md).

Los datos están en `glosario.md`, en tablas Markdown legibles (una por ámbito: dirección
de proyectos, ágil, Scrum, Kanban, Lean, cascada, PRINCE2), con la equivalencia oficial de
cada término y su fuente. Este módulo los carga y:

* `find_in` encuentra los términos que aparecen en un texto (sin tildes ni mayúsculas;
  las siglas, solo escritas en mayúsculas);
* `translation_hints` da las equivalencias que el RAG pasa al modelo al traducir la
  consulta al inglés, para que use la terminología oficial y no una traducción literal;
* `lookup` busca un término por su nombre en español, en inglés o por sus siglas
  (herramienta `jarvis_glosario`).
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

GLOSSARY = Path(__file__).with_name("glosario.md")
SOURCES = {
    "PMI": "PMI, Guía del PMBOK 7.ª ed.",
    "APM": "APM Glossary",
    "AS": "AgileSeekers",
    "SG": "La Guía de Scrum 2020",
    "KG": "La Guía Kanban 2020",
    "LEI": "Lean Enterprise Institute, Lean Lexicon",
    "AM": "Manifiesto Ágil",
    "P2": "PRINCE2",
    "SN": "Snyder, A Project Manager's Book of Forms",
}
# Palabras sueltas tan generales que como pista de traducción no aportan nada.
GENERIC = {
    "proyecto", "plan", "riesgo", "valor", "cambio", "producto", "informe", "registro",
    "metodo", "rol", "resultado", "calidad", "alcance", "objetivo", "programa", "contrato",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class Term:
    es: tuple[str, ...]  # el primero es el preferido; el resto, sinónimos
    en: tuple[str, ...]
    acronyms: tuple[str, ...]
    definition: str
    sources: tuple[str, ...]
    area: str  # ámbito: la sección del glosario

    @property
    def name(self) -> str:
        return self.es[0]

    @property
    def english(self) -> str:
        return self.en[0]


def _key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9&]+", " ", text).strip()


def _split(cell: str, sep: str = ";") -> tuple[str, ...]:
    return tuple(part.strip() for part in cell.split(sep) if part.strip())


@cache
def load(path: Path = GLOSSARY) -> tuple[Term, ...]:
    terms, area = [], ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            area = line[3:].strip()
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not area or len(cells) != 5 or cells[0] in ("Español", "") or set(cells[0]) <= set("-"):
            continue
        es, en, acronyms, definition, sources = cells
        terms.append(
            Term(
                es=_split(es),
                en=_split(en),
                acronyms=tuple(a for part in _split(acronyms) for a in _split(part, "/")),
                definition=definition,
                sources=_split(sources, ","),
                area=area,
            )
        )
    return tuple(terms)


@cache
def _names() -> tuple[tuple[str, Term], ...]:
    """(nombre normalizado, término) de todos los nombres en español, del más largo al más
    corto, sin los que comparten dos términos distintos (p. ej. «entrega»)."""
    seen: dict[str, Term | None] = {}
    for term in load():
        for name in term.es:
            key = _key(name)
            seen[key] = term if seen.get(key, term) == term else None
    pairs = [(key, term) for key, term in seen.items() if term is not None]
    return tuple(sorted(pairs, key=lambda kv: -len(kv[0])))


def find_in(text: str) -> list[Term]:
    """Términos del glosario que aparecen en un texto en español, los más largos primero
    («acta de constitución del proyecto» antes que «acta de constitución»)."""
    normalized = f" {_key(text)} "
    found: list[Term] = []
    for key, term in _names():
        needle = f" {key} "
        if needle in normalized and term not in found:
            found.append(term)
            normalized = normalized.replace(needle, " | ")  # que no cuente también lo corto
    acronyms = set(re.findall(r"\b[A-Z][A-Z0-9&]{1,6}\b", text))
    for term in load():
        if term not in found and acronyms & set(term.acronyms):
            found.append(term)
    return found


def translation_hints(text: str, limit: int = 8) -> str:
    """Equivalencias para traducir `text` al inglés con la terminología oficial; vacío si
    no aparece ningún término útil."""
    hints = []
    for term in find_in(text):
        if len(term.es) == 1 and _key(term.name) in GENERIC:
            continue
        if _key(term.name) == _key(term.english):
            continue  # Scrum, Kanban, Sprint…: se escriben igual
        hints.append(f"{term.name} = {term.english}")
        if len(hints) == limit:
            break
    return "; ".join(hints)


def lookup(query: str, limit: int = 3) -> list[Term]:
    """Términos por nombre en español o en inglés, sinónimo o siglas; si no hay uno exacto,
    los que lo contienen y, por último, los de nombre parecido."""
    wanted = _key(query)
    if not wanted:
        return []
    terms = load()

    def names(term: Term) -> list[str]:
        return [_key(n) for n in (*term.es, *term.en, *term.acronyms)]

    exact = [t for t in terms if wanted in names(t)]
    if exact:
        return exact[:limit]
    partial = [t for t in terms if any(wanted in n for n in names(t))]
    if partial:
        return sorted(partial, key=lambda t: min(len(n) for n in names(t) if wanted in n))[:limit]
    every = {n: t for t in terms for n in names(t)}
    close = difflib.get_close_matches(wanted, list(every), n=limit, cutoff=0.75)
    return list(dict.fromkeys(every[n] for n in close))


def describe(term: Term) -> str:
    """El término en una línea legible para el usuario."""
    acronyms = f" ({', '.join(term.acronyms)})" if term.acronyms else ""
    synonyms = [*term.es[1:], *term.en[1:]]
    also = f" También: {', '.join(synonyms)}." if synonyms else ""
    sources = ", ".join(SOURCES.get(s, s) for s in term.sources)
    return (
        f"**{term.name}** — *{term.english}*{acronyms} · {term.area}\n"
        f"{term.definition}{also}\nFuente: {sources}."
    )
