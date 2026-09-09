import hashlib
import re
from dataclasses import dataclass

from packages.documents.parsers import ParsedBlock

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

DEFAULT_CHUNK_SIZE_CHARS = 1200
DEFAULT_CHUNK_OVERLAP_CHARS = 150


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    page: int | None
    section: str | None
    content_hash: str


def chunk_blocks(
    blocks: list[ParsedBlock],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer = ""
    buffer_page: int | None = None
    buffer_section: str | None = None

    def flush() -> None:
        nonlocal buffer, buffer_page, buffer_section
        text = buffer.strip()
        if text:
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunks.append(
                Chunk(
                    text=text,
                    page=buffer_page,
                    section=buffer_section,
                    content_hash=content_hash,
                )
            )
        buffer = ""
        buffer_page = None
        buffer_section = None

    for block in blocks:
        if buffer and block.section != buffer_section:
            flush()

        sentences = _SENTENCE_SPLIT_RE.split(block.text) if block.text else [block.text]
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if buffer_page is None:
                buffer_page = block.page
            if buffer_section is None:
                buffer_section = block.section

            candidate = f"{buffer} {sentence}".strip() if buffer else sentence
            if len(candidate) <= chunk_size:
                buffer = candidate
                continue

            if len(sentence) > chunk_size:
                flush()
                for i in range(0, len(sentence), chunk_size):
                    part = sentence[i : i + chunk_size]
                    content_hash = hashlib.sha256(part.encode("utf-8")).hexdigest()
                    chunks.append(
                        Chunk(
                            text=part,
                            page=block.page,
                            section=block.section,
                            content_hash=content_hash,
                        )
                    )
                continue

            tail = buffer[-overlap:] if overlap > 0 else ""
            flush()
            buffer = f"{tail} {sentence}".strip() if tail else sentence
            buffer_page = block.page
            buffer_section = block.section

    flush()
    return chunks
