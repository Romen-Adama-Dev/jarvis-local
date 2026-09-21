from packages.core.errors import ValidationFailedError

SECTION_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "dafo": [
        (
            "Fortalezas",
            "¿Cuáles son las fortalezas de '{topic}' según la documentación indexada?",
        ),
        (
            "Debilidades",
            "¿Cuáles son las debilidades de '{topic}' según la documentación indexada?",
        ),
        (
            "Oportunidades",
            "¿Cuáles son las oportunidades de '{topic}' según la documentación indexada?",
        ),
        (
            "Amenazas",
            "¿Cuáles son las amenazas de '{topic}' según la documentación indexada?",
        ),
    ],
    "plan": [
        (
            "Objetivo y alcance",
            "¿Cuál es el objetivo y el alcance de '{topic}' según la documentación indexada?",
        ),
        (
            "Hitos y cronograma",
            "¿Cuáles son los hitos y el cronograma de '{topic}' según la documentación "
            "indexada?",
        ),
        (
            "Riesgos identificados",
            "¿Qué riesgos se han identificado para '{topic}' según la documentación " "indexada?",
        ),
        (
            "Responsables y stakeholders",
            "¿Quiénes son los responsables y stakeholders de '{topic}' según la "
            "documentación indexada?",
        ),
    ],
    "resumen": [
        (
            "Visión general",
            "¿De qué trata '{topic}' y cuál es su propósito según la documentación indexada?",
        ),
        (
            "Conceptos y principios clave",
            "¿Cuáles son los conceptos y principios clave de '{topic}' según la "
            "documentación indexada?",
        ),
        (
            "Estructura y contenidos principales",
            "¿Cuáles son las partes, dominios, procesos o fases principales de '{topic}' "
            "según la documentación indexada?",
        ),
        (
            "Aplicación práctica",
            "¿Qué recomendaciones prácticas se desprenden de '{topic}' según la "
            "documentación indexada?",
        ),
    ],
}


def build_sections_plan(kind: str, topic: str) -> list[tuple[str, str]]:
    template = SECTION_TEMPLATES.get(kind)
    if template is None:
        valid = ", ".join(sorted(SECTION_TEMPLATES))
        raise ValidationFailedError(
            f"Tipo de documento desconocido: '{kind}'. Tipos válidos: {valid}."
        )
    return [(title, question.format(topic=topic)) for title, question in template]
