import pytest

from packages.rag.formulas import latex_to_text


@pytest.mark.parametrize(
    ("latex", "plain"),
    [
        (
            r"Fórmula: $\text{SPI} = \frac{\text{EV}}{\text{PV}}$ (Valor Ganado / Planificado)",
            "Fórmula: SPI = EV / PV (Valor Ganado / Planificado)",
        ),
        (r"$\text{SPI} > 1$: el proyecto va adelantado.", "SPI > 1: el proyecto va adelantado."),
        (r"$$\text{CV} = \text{EV} - \text{AC}$$", "CV = EV - AC"),
        (r"\(\frac{\text{EV} - \text{PV}}{\text{PV}} \times 100\)", "(EV - PV) / PV × 100"),
        (r"\[\text{EAC} = \frac{\text{BAC}}{\text{CPI}}\]", "EAC = BAC / CPI"),
        (r"$\text{SPI} \geq 0{,}95$ y $\text{CPI} \leq 1$", "SPI ≥ 0,95 y CPI ≤ 1"),
        (r"$\frac{\text{Valor Ganado}}{\text{Coste Real}}$", "(Valor Ganado) / (Coste Real)"),
    ],
)
def test_formulas_are_written_as_plain_text(latex, plain):
    assert latex_to_text(latex) == plain


def test_bare_latex_without_dollars_is_converted_too():
    assert latex_to_text(r"El CPI es \frac{EV}{AC} \times 100") == "El CPI es EV / AC × 100"


def test_money_and_normal_text_are_left_alone():
    for text in (
        "El presupuesto está entre $500 y $300 por licencia.",
        "SPI = EV / PV = 0,92: vamos un 8 % por detrás.",
        "Usa {proyecto} en la plantilla.",
        "",
    ):
        assert latex_to_text(text) == text
