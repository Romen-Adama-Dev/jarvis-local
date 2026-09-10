from packages.docgen.schema import DocSection, GeneratedDoc

_NO_EVIDENCE = "_Sin evidencia suficiente en la documentación indexada._"


def _sources_lines(section: DocSection) -> list[str]:
    if section.insufficient_evidence or not section.sources:
        return [_NO_EVIDENCE]
    lines = []
    for source in section.sources:
        location = f"página {source.page}" if source.page else (source.section or "sin sección")
        lines.append(f"- {source.filename} ({location})")
    return lines


def render_markdown(doc: GeneratedDoc) -> str:
    lines = [
        "---",
        f"title: {doc.topic}",
        "lang: es",
        f"date: {doc.generated_at}",
        "---",
        "",
        f"# {doc.topic}",
        "",
    ]
    for section in doc.sections:
        lines.append(f"## {section.title}")
        lines.append("")
        if section.insufficient_evidence:
            lines.append(_NO_EVIDENCE)
        else:
            lines.append(section.answer)
        lines.append("")
        lines.append("**Fuentes**")
        lines.append("")
        lines.extend(_sources_lines(section))
        lines.append("")
    return "\n".join(lines)
