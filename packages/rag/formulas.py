"""Fórmulas en texto plano. Telegram y el panel no dibujan LaTeX: una respuesta con
`$\\text{SPI} = \\frac{\\text{EV}}{\\text{PV}}$` se lee tal cual, con barras y llaves. El
prompt pide fórmulas en texto (SPI = EV / PV); esto es la red por si el modelo no hace caso.
"""

import re

_SYMBOLS = {
    "times": "×",
    "cdot": "·",
    "div": "÷",
    "geq": "≥",
    "ge": "≥",
    "leq": "≤",
    "le": "≤",
    "neq": "≠",
    "ne": "≠",
    "approx": "≈",
    "pm": "±",
    "to": "→",
    "rightarrow": "→",
    "Rightarrow": "⇒",
    "infty": "∞",
    "sum": "Σ",
    "Delta": "Δ",
    "%": "%",
    "$": "$",
    ",": " ",
    ";": " ",
    " ": " ",
    "quad": " ",
    "qquad": " ",
    "left": "",
    "right": "",
    "displaystyle": "",
}
_WRAPPERS = {"text", "mathrm", "textbf", "mathbf", "textit", "mathit", "operatorname", "mbox"}
_FRACTIONS = {"frac", "dfrac", "tfrac"}
_COMMAND = re.compile(r"\\([A-Za-z]+|.)")
# $$…$$, $…$ (sin espacio junto a los dólares, en una línea), \(…\) y \[…\]
_MATH = re.compile(
    r"\$\$(.+?)\$\$|\$(?!\s)([^$\n]+?)(?<!\s)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]", re.DOTALL
)
# LaTeX suelto, fuera de los dólares
_BARE = re.compile(
    r"\\(?:[dt]?frac|text|mathrm|textbf|mathbf|operatorname)\s*\{|"
    r"\\(?:times|cdot|div|geq|leq|neq|approx|pm|rightarrow|infty)(?![A-Za-z])"
)


def _argument(tex: str, start: int) -> tuple[str, int]:
    """Argumento de un comando: lo que hay entre llaves (anidadas) o un solo carácter."""
    i = start
    while i < len(tex) and tex[i] == " ":
        i += 1
    if i >= len(tex):
        return "", i
    if tex[i] != "{":
        return tex[i], i + 1
    depth = 0
    for j in range(i, len(tex)):
        depth += {"{": 1, "}": -1}.get(tex[j], 0)
        if depth == 0:
            return tex[i + 1 : j], j + 1
    return tex[i + 1 :], len(tex)


def _operand(text: str) -> str:
    text = text.strip()
    return f"({text})" if re.search(r"[\s+\-−×·/]", text) else text


def _command(tex: str, start: int) -> tuple[str, int]:
    """Traduce el comando que empieza en `start` (la barra) y dice dónde acaba."""
    match = _COMMAND.match(tex, start)
    if not match:
        return tex[start], start + 1
    name, end = match.group(1), match.end()
    if name in _FRACTIONS:
        top, end = _argument(tex, end)
        bottom, end = _argument(tex, end)
        return f"{_operand(_formula(top))} / {_operand(_formula(bottom))}", end
    if name in _WRAPPERS:
        inner, end = _argument(tex, end)
        return _formula(inner), end
    return _SYMBOLS.get(name, name), end


def _formula(tex: str) -> str:
    parts, i = [], 0
    while i < len(tex):
        if tex[i] == "\\":
            text, i = _command(tex, i)
            parts.append(text)
        else:
            parts.append(tex[i])
            i += 1
    return re.sub(r"[ \t]+", " ", "".join(parts).replace("{", "").replace("}", "")).strip()


def latex_to_text(text: str) -> str:
    """Pasa a texto plano las fórmulas en LaTeX («$\\frac{EV}{PV}$» → «EV / PV»). Lo que va
    entre dólares sin comandos se deja: «entre $500 y $300» es dinero, no una fórmula."""

    def plain(match: re.Match) -> str:
        tex = next(group for group in match.groups() if group is not None)
        if "\\" not in tex and not re.search(r"[\^_]\{", tex):
            return match.group(0)
        return _formula(tex)

    text = _MATH.sub(plain, text)
    parts, i = [], 0
    for match in _BARE.finditer(text):
        if match.start() < i:
            continue
        converted, end = _command(text, match.start())
        parts += [text[i : match.start()], converted]
        i = end
    return "".join(parts) + text[i:]
