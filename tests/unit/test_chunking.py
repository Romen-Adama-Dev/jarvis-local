from packages.documents.parsers import ParsedBlock
from packages.rag.chunking import chunk_blocks


def test_single_section_merges_sentences_into_one_chunk():
    blocks = [
        ParsedBlock(text="Frase uno.", page=1, section="Introducción", order=0),
        ParsedBlock(text="Frase dos.", page=1, section="Introducción", order=1),
    ]

    chunks = chunk_blocks(blocks, chunk_size=1000, overlap=0)

    assert len(chunks) == 1
    assert chunks[0].section == "Introducción"
    assert "Frase uno." in chunks[0].text
    assert "Frase dos." in chunks[0].text


def test_section_change_flushes_even_if_it_would_fit_in_one_chunk():
    blocks = [
        ParsedBlock(text="Frase de la sección A.", page=1, section="A", order=0),
        ParsedBlock(text="Frase de la sección B.", page=1, section="B", order=1),
    ]

    chunks = chunk_blocks(blocks, chunk_size=1000, overlap=0)

    assert len(chunks) == 2
    assert chunks[0].section == "A"
    assert chunks[1].section == "B"
    assert "sección B" not in chunks[0].text
    assert "sección A" not in chunks[1].text


def test_none_section_does_not_force_a_flush():
    blocks = [
        ParsedBlock(text="Primer párrafo.", page=1, section=None, order=0),
        ParsedBlock(text="Segundo párrafo.", page=2, section=None, order=1),
    ]

    chunks = chunk_blocks(blocks, chunk_size=1000, overlap=0)

    assert len(chunks) == 1
    assert "Primer párrafo." in chunks[0].text
    assert "Segundo párrafo." in chunks[0].text
