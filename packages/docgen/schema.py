from dataclasses import dataclass

from packages.rag.orchestrator import RagSource


@dataclass(frozen=True, slots=True)
class DocSection:
    title: str
    answer: str
    sources: list[RagSource]
    insufficient_evidence: bool


@dataclass(frozen=True, slots=True)
class GeneratedDoc:
    kind: str
    topic: str
    generated_at: str
    sections: list[DocSection]
