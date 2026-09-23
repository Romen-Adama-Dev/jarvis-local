import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str
    message: str
    correlation_id: str | None = None
    details: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    version: str


class DependencyStatus(BaseModel):
    name: str
    healthy: bool
    detail: str = ""


class ReadyResponse(BaseModel):
    ready: bool
    dependencies: list[DependencyStatus]


class ModelInfoResponse(BaseModel):
    name: str
    provider: str
    size_bytes: int | None = None
    supports_tools: bool = False


class ModelsResponse(BaseModel):
    models: list[ModelInfoResponse]


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn]
    mode: str = "normal"
    model: str | None = None


class ChatResponse(BaseModel):
    text: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


class SourceRef(BaseModel):
    document_id: str
    filename: str
    page: int | None = None
    section: str | None = None
    chunk_id: str
    score: float


class RagQueryRequest(BaseModel):
    query: str
    # Ámbito: sin empresa solo se busca en la documentación global; con empresa, también
    # en la suya; con proyecto, además en la del proyecto (packages/core/scope.py).
    company: str = ""
    project: str = ""
    # Metodologías del proyecto (packages/core/directives.py): con alguna, solo se ven
    # los documentos de esas metodologías y los que no tienen ninguna.
    methodologies: list[str] = Field(default_factory=list, max_length=10)
    filters: dict = Field(default_factory=dict)
    top_k: int = 8
    conversation_id: uuid.UUID | None = None
    telegram_user_id: int | None = None


class RagQueryResponse(BaseModel):
    answer: str
    sources: list[SourceRef]
    confidence: float
    insufficient_evidence: bool
    warning: str | None = None


class GenerateDocumentRequest(BaseModel):
    kind: str
    topic: str
    format: str = "pdf"
    company: str = ""
    project: str = ""
    methodologies: list[str] = Field(default_factory=list, max_length=10)
    filters: dict = Field(default_factory=dict)
    telegram_user_id: int | None = None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    sha256: str
    size_bytes: int
    page_count: int | None
    doc_metadata: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class ScopeInfo(BaseModel):
    company: str
    project: str
    documents: int


class ProjectListResponse(BaseModel):
    projects: list[str]
    scopes: list[ScopeInfo] = Field(default_factory=list)


class DocumentScopeRequest(BaseModel):
    company: str = ""
    project: str = ""


class DocumentMethodologyRequest(BaseModel):
    # Nombre legible ("Scrum", "PMI"); vacío = sin metodología (lo ve cualquier proyecto).
    methodology: str = Field(default="", max_length=64)


class JobResponse(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    progress: int
    document_id: uuid.UUID | None
    error: str | None
    result: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    jobs: list[JobResponse]


class ConversationCreateRequest(BaseModel):
    telegram_user_id: int
    title: str | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    telegram_user_id: int
    title: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]


class CalendarDraftRequest(BaseModel):
    subject: str
    start: str
    end: str
    attendees: list[str] = Field(default_factory=list)
    body: str = ""
    # Solo CALENDAR_PROVIDER=openproject: proyecto de la reunión (vacío = "Agenda").
    project: str = ""
    location: str = ""
    telegram_user_id: int


class CalendarDraftResponse(BaseModel):
    token: str
    summary: str
    expires_at: float


class EmailDraftRequest(BaseModel):
    to: list[str]
    subject: str
    body: str
    cc: list[str] = Field(default_factory=list)
    # Trabajo de doc-gen terminado cuyo documento se adjunta (ver jarvis_generate_doc).
    attachment_job_id: str | None = None
    telegram_user_id: int


class EmailDraftResponse(BaseModel):
    token: str
    summary: str
    expires_at: float


class CalendarConfirmRequest(BaseModel):
    telegram_user_id: int


class EmailConfirmRequest(BaseModel):
    telegram_user_id: int
