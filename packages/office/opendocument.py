"""Renderizadores OpenDocument (LibreOffice/OpenOffice) con odfpy: hoja de cálculo
(.ods), texto (.odt) y presentación (.odp)."""

from pathlib import Path
from typing import Any

from odf.draw import Frame, Page, TextBox
from odf.element import Element
from odf.opendocument import (
    OpenDocumentPresentation,
    OpenDocumentSpreadsheet,
    OpenDocumentText,
)
from odf.style import (
    GraphicProperties,
    MasterPage,
    PageLayout,
    PageLayoutProperties,
    ParagraphProperties,
    Style,
    TableCellProperties,
    TableColumnProperties,
    TextProperties,
)
from odf.table import Table, TableCell, TableColumn, TableRow
from odf.text import H, List, ListItem, P, Span

from packages.office.ooxml import display, sheet_names, slides, total_row
from packages.office.spec import (
    Block,
    Cell,
    Formula,
    bold_runs,
    column_letter,
    column_sum,
    formula_for_ods,
    numeric_columns,
    plain,
)


def _styles(doc: Any, *, cell_borders: bool) -> dict[str, Element]:
    bold = Style(name="Negrita", family="text")
    bold.addElement(TextProperties(fontweight="bold"))
    doc.automaticstyles.addElement(bold)
    header = Style(name="Cabecera", family="table-cell")
    header.addElement(TableCellProperties(backgroundcolor="#1f3864", border="0.5pt solid #000000"))
    header.addElement(TextProperties(fontweight="bold", color="#ffffff"))
    doc.automaticstyles.addElement(header)
    cell = Style(name="Celda", family="table-cell")
    if cell_borders:
        cell.addElement(TableCellProperties(border="0.5pt solid #000000"))
    doc.automaticstyles.addElement(cell)
    total = Style(name="Total", family="table-cell")
    total.addElement(TextProperties(fontweight="bold"))
    doc.automaticstyles.addElement(total)
    return {"bold": bold, "header": header, "cell": cell, "total": total}


def _rich_p(text: str, bold: Element, **kwargs) -> Element:
    paragraph = P(**kwargs)
    for chunk, is_bold in bold_runs(text):
        if is_bold:
            paragraph.addElement(Span(stylename=bold, text=chunk))
        else:
            paragraph.addText(chunk)
    return paragraph


def _cell(value: Cell | Formula, style: Element, *, spreadsheet: bool) -> Element:
    if isinstance(value, Formula):
        if spreadsheet:
            return TableCell(stylename=style, formula=formula_for_ods(value), valuetype="float")
        value = value.text
    if isinstance(value, int | float):
        cell = TableCell(stylename=style, valuetype="float", value=value)
        cell.addElement(P(text=str(value).replace(".", ",")))
        return cell
    cell = TableCell(stylename=style, valuetype="string")
    cell.addElement(P(text=plain(value or "")))
    return cell


def _table(block: Block, name: str, styles: dict[str, Element], *, spreadsheet: bool) -> Element:
    table = Table(name=name)
    table.addElement(TableColumn(numbercolumnsrepeated=len(block.columns)))
    header = TableRow()
    for title in block.columns:
        cell = TableCell(stylename=styles["header"], valuetype="string")
        cell.addElement(P(text=title))
        header.addElement(cell)
    table.addElement(header)
    for values in block.rows:
        row = TableRow()
        for value in values:
            row.addElement(_cell(value, styles["cell"], spreadsheet=spreadsheet))
        table.addElement(row)
    if block.total and block.rows:
        numeric = set(numeric_columns(block)) - {0}
        last = len(block.rows) + 1
        row = TableRow()
        row.addElement(_cell("Total", styles["total"], spreadsheet=spreadsheet))
        for col in range(1, len(block.columns)):
            if col not in numeric:
                value: Cell | Formula = None
            elif spreadsheet:
                letter = column_letter(col)
                value = Formula(f"=SUM({letter}2:{letter}{last})")
            else:
                value = column_sum(block, col)
            row.addElement(_cell(value, styles["total"], spreadsheet=spreadsheet))
        table.addElement(row)
    return table


def render_ods(title: str, blocks: list[Block], out_path: Path) -> None:
    doc: Any = OpenDocumentSpreadsheet()
    styles = _styles(doc, cell_borders=False)
    wide = Style(name="ColAncha", family="table-column")
    wide.addElement(TableColumnProperties(columnwidth="4cm"))
    doc.automaticstyles.addElement(wide)
    tables = [b for b in blocks if b.kind == "table"]
    for name, block in zip(sheet_names(blocks), tables, strict=True):
        sheet = _table(block, name, styles, spreadsheet=True)
        for column in sheet.getElementsByType(TableColumn):
            column.setAttribute("stylename", wide)
        doc.spreadsheet.addElement(sheet)
    notes = [b for b in blocks if b.kind != "table"]
    if notes or not tables:
        sheet = Table(name="Notas")
        for line in [title] + [
            plain(t) for b in notes for t in (b.items if b.kind == "bullets" else [b.text])
        ]:
            row = TableRow()
            row.addElement(_cell(line, styles["cell"], spreadsheet=True))
            sheet.addElement(row)
        doc.spreadsheet.addElement(sheet)
    _save(doc, title, out_path)


def render_odt(title: str, blocks: list[Block], out_path: Path) -> None:
    doc: Any = OpenDocumentText()
    styles = _styles(doc, cell_borders=True)
    heading_styles = {}
    for level, size in ((0, "20pt"), (1, "16pt"), (2, "14pt"), (3, "12pt")):
        style = Style(name=f"Titulo{level}", family="paragraph")
        style.addElement(TextProperties(fontweight="bold", fontsize=size))
        style.addElement(ParagraphProperties(margintop="0.3cm", marginbottom="0.2cm"))
        doc.automaticstyles.addElement(style)
        heading_styles[level] = style
    doc.text.addElement(H(outlinelevel=1, stylename=heading_styles[0], text=title))
    table_index = 0
    for block in blocks:
        if block.kind == "heading":
            doc.text.addElement(
                H(
                    outlinelevel=block.level + 1,
                    stylename=heading_styles[block.level],
                    text=plain(block.text),
                )
            )
        elif block.kind == "paragraph":
            doc.text.addElement(_rich_p(block.text, styles["bold"]))
        elif block.kind == "bullets":
            items = List()
            for item in block.items:
                entry = ListItem()
                entry.addElement(_rich_p(f"• {item}", styles["bold"]))
                items.addElement(entry)
            doc.text.addElement(items)
        elif block.kind == "table":
            table_index += 1
            if block.name:
                doc.text.addElement(_rich_p(f"**{block.name}**", styles["bold"]))
            name = f"Tabla{table_index}"
            doc.text.addElement(_table(block, name, styles, spreadsheet=False))
            doc.text.addElement(P())
    _save(doc, title, out_path)


def render_odp(title: str, blocks: list[Block], out_path: Path) -> None:
    doc: Any = OpenDocumentPresentation()
    styles = _styles(doc, cell_borders=True)
    layout = PageLayout(name="Diapositiva")
    layout.addElement(
        PageLayoutProperties(
            margin="0cm", pagewidth="28cm", pageheight="15.75cm", printorientation="landscape"
        )
    )
    doc.automaticstyles.addElement(layout)
    master = MasterPage(name="Normal", pagelayoutname=layout)
    doc.masterstyles.addElement(master)
    frame_style = Style(name="Marco", family="presentation")
    frame_style.addElement(GraphicProperties(fill="none", stroke="none"))
    doc.automaticstyles.addElement(frame_style)
    title_style = Style(name="TituloDiapo", family="paragraph")
    title_style.addElement(TextProperties(fontsize="32pt", fontweight="bold"))
    doc.automaticstyles.addElement(title_style)
    body_style = Style(name="Cuerpo", family="paragraph")
    body_style.addElement(TextProperties(fontsize="20pt"))
    body_style.addElement(ParagraphProperties(marginbottom="0.2cm"))
    doc.automaticstyles.addElement(body_style)

    def add_slide(slide_title: str, lines: list[Element], index: int) -> None:
        page = Page(name=f"Diapositiva{index}", masterpagename=master)
        heading = Frame(stylename=frame_style, width="26cm", height="2.5cm", x="1cm", y="0.6cm")
        box = TextBox()
        box.addElement(P(stylename=title_style, text=slide_title))
        heading.addElement(box)
        page.addElement(heading)
        if lines:
            content = Frame(
                stylename=frame_style, width="26cm", height="11.5cm", x="1cm", y="3.4cm"
            )
            box = TextBox()
            for line in lines:
                box.addElement(line)
            content.addElement(box)
            page.addElement(content)
        doc.presentation.addElement(page)

    add_slide(title, [], 1)
    index = 1
    for slide_title, content in slides(blocks):
        index += 1
        lines: list[Element] = []
        for block in content:
            if block.kind == "table":
                # Las tablas van como texto tabulado: Impress no garantiza tablas ODF
                # nativas creadas fuera de LibreOffice.
                header = "**" + " · ".join(block.columns) + "**"
                lines.append(_rich_p(header, styles["bold"], stylename=body_style))
                rows = [list(r) for r in block.rows]
                if block.total and rows:
                    rows.append(total_row(block, set(numeric_columns(block))))
                for values in rows[:12]:
                    text_line = " · ".join(plain(display(v)) for v in values)
                    lines.append(P(stylename=body_style, text=text_line))
                if len(rows) > 12:
                    lines.append(P(stylename=body_style, text=f"(+{len(rows) - 12} filas más)"))
                continue
            texts = block.items if block.kind == "bullets" else [block.text]
            prefix = "• " if block.kind == "bullets" else ""
            for text in texts:
                line = _rich_p(prefix + text, styles["bold"], stylename=body_style)
                lines.append(line)
        add_slide(slide_title, lines, index)
    _save(doc, title, out_path)


def _save(doc: Any, title: str, out_path: Path) -> None:
    from odf.dc import Title

    doc.meta.addElement(Title(text=title))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
