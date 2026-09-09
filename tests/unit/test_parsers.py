from packages.documents import parsers
from packages.documents.parsers import _looks_like_heading


def test_numbered_heading_is_detected():
    assert _looks_like_heading("1.2 Purpose of the PMBOK Guide")
    assert _looks_like_heading("3. INTRODUCTION")


def test_all_caps_short_title_is_detected():
    assert _looks_like_heading("PART 1: GUIDE")


def test_regular_sentence_is_not_a_heading():
    assert not _looks_like_heading("El proyecto debe cumplir con el alcance definido.")


def test_long_line_is_never_a_heading_even_if_all_caps():
    assert not _looks_like_heading("A" * 120)


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakePdfReader:
    def __init__(self, _stream: object) -> None:
        self.pages = [
            _FakePage("1.1 INTRODUCTION\n\nEste es el contenido de la sección uno."),
            _FakePage("1.2 Purpose\n\nEste es el contenido de la sección dos."),
        ]


def test_parse_pdf_assigns_detected_headings_as_section(monkeypatch):
    monkeypatch.setattr(parsers, "PdfReader", _FakePdfReader)

    document = parsers._parse_pdf(b"fake-pdf-bytes", "libro.pdf")

    sections = [block.section for block in document.blocks]
    texts = [block.text for block in document.blocks]

    assert sections == ["1.1 INTRODUCTION", "1.2 Purpose"]
    assert texts == [
        "Este es el contenido de la sección uno.",
        "Este es el contenido de la sección dos.",
    ]
