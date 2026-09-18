import html
import os
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

JARVIS_API_URL = os.environ.get("JARVIS_API_URL", "http://127.0.0.1:8000").rstrip("/")
JARVIS_API_INTERNAL_TOKEN = os.environ["JARVIS_API_INTERNAL_TOKEN"]
JARVIS_DATA_ROOT = Path(os.environ.get("JARVIS_DATA_ROOT", "/srv/jarvis"))
# Los documentos generados se copian aquí (dentro del workspace del agente) para que
# OpenClaw pueda adjuntarlos en el chat con una línea `MEDIA:<ruta>`.
JARVIS_OUTBOX_DIR = Path(
    os.environ.get("JARVIS_OUTBOX_DIR", Path.home() / ".openclaw" / "workspace-jarvis" / "outbox")
)
# Debe quedar por debajo de `requestTimeoutMs` del servidor MCP en openclaw.json.
DOCGEN_WAIT_SECONDS = float(os.environ.get("DOCGEN_WAIT_SECONDS", "540"))
_DOCGEN_POLL_SECONDS = 5.0

mcp = FastMCP("jarvis-rag")

_client = httpx.Client(
    base_url=JARVIS_API_URL,
    headers={"Authorization": f"Bearer {JARVIS_API_INTERNAL_TOKEN}"},
    timeout=180.0,
)


def _api_message(response: httpx.Response) -> str | None:
    """Mensaje legible de la API para errores de validación (p. ej. empresa ambigua)."""
    if response.status_code in (404, 409, 422):
        try:
            return response.json().get("message")
        except ValueError:
            return None
    return None


def _company_of(project: str) -> str:
    """Empresa de un proyecto según OpenProject (proyecto padre), si está configurado.
    La API ya la deduce de documentos anteriores; esto cubre proyectos sin documentos."""
    if not project:
        return ""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
        from packages.openproject.client import OpenProjectClient, OpenProjectConfig

        key_file = Path("/run/jarvis/openproject_api_key")
        if not key_file.is_file():
            return ""
        op = OpenProjectClient(
            OpenProjectConfig(
                url=os.environ.get("OPENPROJECT_URL", "http://127.0.0.1:8090"),
                api_key=key_file.read_text().strip(),
            )
        )
        found = op.find_project(project)
        parent = (found["_links"].get("parent") or {}).get("title")
        return parent or ""
    except Exception:  # noqa: BLE001 - OpenProject es opcional: la API decide
        return ""


def _scope(company: str, project: str) -> dict:
    company = company.strip()
    project = project.strip()
    if project and not company:
        company = _company_of(project)
    return {"company": company, "project": project}


def _format_answer(data: dict) -> str:
    if data.get("insufficient_evidence"):
        return data.get("warning") or "No hay evidencia suficiente en la documentación indexada."

    lines = [data["answer"], "", "Fuentes:"]
    for source in data.get("sources", []):
        location = f"pág. {source['page']}" if source.get("page") else (source.get("section") or "")
        lines.append(f"- {source['filename']} ({location}) [confianza {data['confidence']:.2f}]")
    return "\n".join(lines)


@mcp.tool()
def jarvis_ask(query: str, company: str = "", project: str = "") -> str:
    """Consulta la documentación indexada (RAG). Cada empresa y cada proyecto tienen su
    documentación aislada: pasa `company` y/o `project` del contexto de la conversación.
    Con proyecto se busca en ese proyecto, en la documentación de su empresa y en la
    general; solo con empresa, en toda la empresa y la general; sin nada, solo en la
    general (PMBOK, metodologías). Nunca mezcla empresas."""
    response = _client.post("/v1/rag/query", json={"query": query, **_scope(company, project)})
    if message := _api_message(response):
        return message
    response.raise_for_status()
    answer = _format_answer(response.json())
    if not company and not project:
        answer += (
            "\n(Búsqueda solo en la documentación general. Si la pregunta es de una empresa "
            "o un proyecto, repítela con company/project; ver jarvis_list_projects.)"
        )
    return answer


@mcp.tool()
def jarvis_deep(query: str, company: str = "", project: str = "") -> str:
    """Encola una consulta RAG en modo profundo (AirLLM, lenta, para tareas sin urgencia),
    con el mismo aislamiento por empresa/proyecto que jarvis_ask. Devuelve un
    identificador de trabajo; recoge el resultado con jarvis_job_result."""
    response = _client.post("/v1/rag/deep-query", json={"query": query, **_scope(company, project)})
    if response.status_code == 503:
        detail = response.json()
        return detail.get("message") or "El modo profundo (AirLLM) no está disponible."
    response.raise_for_status()
    job = response.json()
    return (
        f"Consulta profunda encolada como trabajo {job['id']} ({job['status']}). "
        "AirLLM es lento por diseño (carga el modelo por capas desde disco): "
        "consulta el resultado en unos minutos con jarvis_job_result."
    )


def _slug(text: str, max_len: int = 40) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "documento"


def _download_generated_document(job_id: str, result: dict) -> Path:
    """Copia el documento generado (vive en el volumen de la API) al outbox del workspace
    del agente, desde donde OpenClaw puede adjuntarlo en el chat."""
    response = _client.get(f"/v1/documents/generated/{job_id}")
    response.raise_for_status()
    kind = result.get("kind") or "documento"
    ext = result.get("format") or "bin"
    JARVIS_OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = JARVIS_OUTBOX_DIR / f"{kind}-{_slug(result.get('topic') or '')}-{job_id[:8]}.{ext}"
    path.write_bytes(response.content)
    return path


def _format_generated_document(job_id: str, result: dict) -> str:
    lines = [
        f"Documento generado (trabajo {job_id}): {result.get('kind')} sobre "
        f"'{result.get('topic')}' en {result.get('format')}.",
    ]
    missing = [s["title"] for s in result.get("sections", []) if s.get("insufficient_evidence")]
    if missing:
        lines.append("Secciones sin evidencia suficiente: " + ", ".join(missing))
    else:
        lines.append("Todas las secciones tienen evidencia en la documentación indexada.")
    try:
        path = _download_generated_document(job_id, result)
    except httpx.HTTPError as exc:
        lines.append(f"No se pudo recuperar el archivo para enviarlo por el chat: {exc}")
        return "\n".join(lines)
    lines += [
        "Para enviar el archivo a Romen por el chat, termina tu respuesta con esta línea "
        "EXACTA, sola en su propia línea, sin comillas, negritas ni bloque de código:",
        f"MEDIA:{path}",
        "Para adjuntarlo a un correo usa "
        f'jarvis_email_draft(..., attachment_job_id="{job_id}").',
    ]
    return "\n".join(lines)


@mcp.tool()
def jarvis_generate_doc(
    kind: str, topic: str, format: str = "pdf", company: str = "", project: str = ""
) -> str:
    """Genera un documento fundamentado en el RAG de Jarvis y lo deja listo para enviarlo
    por el chat o adjuntarlo a un correo. `kind`: "resumen" (resumen de un tema o de un
    documento indexado, p. ej. "Guía del PMBOK 7ª edición"), "dafo" o "plan" (plan de
    coordinación de proyecto). `format`: pdf, docx, pptx o md.

    `company`/`project`: de qué empresa o proyecto sale la información (mismo aislamiento
    que jarvis_ask); vacíos = solo documentación general.

    Tarda unos minutos y espera aquí hasta que el documento está listo. Si la espera se
    agota, devuelve el identificador del trabajo para recogerlo con jarvis_job_result."""
    response = _client.post(
        "/v1/documents/generate",
        json={"kind": kind, "topic": topic, "format": format, **_scope(company, project)},
    )
    if response.status_code == 422:
        detail = response.json()
        return detail.get("message") or "Petición de generación de documento inválida."
    response.raise_for_status()
    job_id = response.json()["id"]

    deadline = time.monotonic() + DOCGEN_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(_DOCGEN_POLL_SECONDS)
        poll = _client.get(f"/v1/jobs/{job_id}")
        poll.raise_for_status()
        job = poll.json()
        if job["status"] == "completed":
            return _format_generated_document(job_id, job.get("result") or {})
        if job["status"] in {"failed", "cancelled"}:
            return f"Trabajo {job_id} {job['status']}: {job.get('error') or 'sin detalle'}"
    return (
        f"El documento sigue generándose (trabajo {job_id}). Dile a Romen que tardará un poco "
        "más y recógelo con jarvis_job_result cuando lo pida."
    )


@mcp.tool()
def jarvis_job_result(job_id: str) -> str:
    """Recoge el estado o el resultado de un trabajo (consulta profunda, indexación,
    documento generado). Si es un documento generado, lo deja listo para enviarlo."""
    response = _client.get(f"/v1/jobs/{job_id}")
    response.raise_for_status()
    job = response.json()
    status = job["status"]
    if status == "failed":
        return f"Trabajo {job_id} FALLÓ: {job.get('error') or 'sin detalle'}"
    if status != "completed":
        return (
            f"Trabajo {job_id}: {status} ({job.get('progress', 0)}%). Vuelve a consultar más tarde."
        )
    result = job.get("result") or {}
    if job.get("job_type") == "deep_query" and "answer" in result:
        return _format_answer(result)
    if job.get("job_type") == "generate_document" and "storage_path" in result:
        return _format_generated_document(job_id, result)
    if job.get("job_type") == "meeting_minutes" and "minutes" in result:
        return _format_meeting_minutes(job_id, result)
    return f"Trabajo {job_id} completado: {result}"


@mcp.tool()
def jarvis_status() -> str:
    """Consulta la salud de Jarvis API y sus dependencias (Postgres, Redis, Qdrant,
    Ollama, AirLLM)."""
    health = _client.get("/health").json()
    ready = _client.get("/ready").json()
    lines = [f"API: {health['status']} (v{health['version']})", f"Listo: {ready['ready']}"]
    for dep in ready["dependencies"]:
        marker = "OK" if dep["healthy"] else "FALLO"
        lines.append(f"- {dep['name']}: {marker} {dep.get('detail', '')}".rstrip())
    return "\n".join(lines)


@mcp.tool()
def jarvis_models() -> str:
    """Lista los modelos de inferencia locales disponibles."""
    response = _client.get("/v1/models")
    response.raise_for_status()
    models = response.json()["models"]
    if not models:
        return "No hay modelos disponibles todavía."
    return "\n".join(
        f"- {m['name']} ({m['provider']}, tools={m['supports_tools']})" for m in models
    )


@mcp.tool()
def jarvis_disk() -> str:
    """Consulta el espacio de disco usado por Jarvis en /srv/jarvis."""
    usage = shutil.disk_usage(JARVIS_DATA_ROOT)
    gib = 1024**3
    return (
        f"{JARVIS_DATA_ROOT}: {usage.used / gib:.1f} GiB usados de "
        f"{usage.total / gib:.1f} GiB ({usage.used / usage.total * 100:.0f}%), "
        f"{usage.free / gib:.1f} GiB libres."
    )


UPLOAD_ALLOWED_ROOTS = (
    Path.home() / ".openclaw" / "workspace-jarvis" / "media",
    Path.home() / ".openclaw" / "media",
    Path.home() / "jarvis-inbox",
    JARVIS_DATA_ROOT / "documents",
)
UPLOAD_ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".html", ".csv", ".xlsx"}
UPLOAD_MAX_BYTES = 50 * 1024 * 1024


def _safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _resolve_upload_path(file_path: str) -> Path | None:
    """Acepta una ruta o solo el nombre del adjunto. OpenClaw guarda los adjuntos como
    `[input-]<nombre saneado y a veces truncado>---<uuid>.<ext>`, así que un nombre se
    resuelve al archivo más reciente cuyo nombre guardado sea prefijo del pedido."""
    candidate = Path(file_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    wanted = Path(html.unescape(file_path))
    wanted_stem = _safe_stem(wanted.stem)
    wanted_suffix = wanted.suffix.lower()
    matches: list[Path] = []
    for root in UPLOAD_ALLOWED_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob(f"*{wanted_suffix}"):
            stored = path.stem.removeprefix("input-").split("---", 1)[0]
            truncated_match = len(stored) >= 8 and wanted_stem.startswith(stored)
            if stored and (stored == wanted_stem or truncated_match):
                matches.append(path)
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime).resolve()


@mcp.tool()
def jarvis_upload(file_path: str, company: str = "", project: str = "") -> str:
    """Sube un documento al RAG de Jarvis para indexarlo. `file_path` puede ser la ruta
    completa o simplemente el nombre del adjunto tal como aparece en
    `<file name="...">` (p. ej. "PMBOK-7Ed.pdf"). Antes de llamarla, pregunta siempre
    al usuario (1) si el documento debe añadirse al RAG, y (2) si es documentación
    general, de una empresa o de un proyecto (usa jarvis_list_projects para ofrecerle
    los existentes). General: sin company ni project. Empresa: solo `company`.
    Proyecto: `project` (y `company` si se sabe). Devuelve el trabajo de indexación;
    consulta su progreso con jarvis_jobs."""
    path = _resolve_upload_path(file_path)
    if path is None:
        return f"No encuentro ningún adjunto recibido con el nombre: {file_path}"
    if not any(path.is_relative_to(root) for root in UPLOAD_ALLOWED_ROOTS):
        allowed = ", ".join(str(r) for r in UPLOAD_ALLOWED_ROOTS)
        return f"Ruta no autorizada para subida. Directorios permitidos: {allowed}"
    if not path.is_file():
        return f"No existe el archivo: {path}"
    if path.suffix.lower() not in UPLOAD_ALLOWED_SUFFIXES:
        supported = ", ".join(sorted(UPLOAD_ALLOWED_SUFFIXES))
        return f"Tipo no soportado ({path.suffix}). Soportados: {supported}"
    if path.stat().st_size > UPLOAD_MAX_BYTES:
        return f"Archivo demasiado grande ({path.stat().st_size / 1024**2:.0f} MiB > 50 MiB)."

    params = {k: v for k, v in _scope(company, project).items() if v}
    with path.open("rb") as fh:
        response = _client.post("/v1/documents", params=params, files={"file": (path.name, fh)})
    if response.status_code == 409:
        return f"El documento {path.name} ya está indexado (duplicado por hash)."
    if message := _api_message(response):
        return message
    response.raise_for_status()
    job = response.json()
    if params.get("project"):
        project_note = f" (proyecto: {params.get('company')} › {params['project']})"
    elif params.get("company"):
        project_note = f" (empresa: {params['company']})"
    else:
        project_note = " (documentación general)"
    return (
        f"Documento {path.name} aceptado{project_note}. Trabajo de indexación {job['id']} "
        f"({job['status']}). Sigue el progreso con jarvis_jobs."
    )


@mcp.tool()
def jarvis_list_projects() -> str:
    """Empresas y proyectos con documentación en el RAG (y cuántos documentos tiene cada
    uno), para ofrecérselos al usuario al subir un documento o al preguntar."""
    response = _client.get("/v1/documents/projects")
    response.raise_for_status()
    scopes = response.json().get("scopes", [])
    if not scopes:
        return "Todavía no hay documentos indexados."
    lines = ["Documentación por ámbito:"]
    for scope in scopes:
        if not scope["company"]:
            name = "General (visible desde cualquier empresa)"
        elif not scope["project"]:
            name = f"{scope['company']} (toda la empresa)"
        else:
            name = f"{scope['company']} › {scope['project']}"
        lines.append(f"- {name}: {scope['documents']} documentos")
    return "\n".join(lines)


@mcp.tool()
def jarvis_move_document(document: str, company: str = "", project: str = "") -> str:
    """Cambia un documento ya indexado de ámbito sin reindexarlo: a una empresa (solo
    `company`), a un proyecto (`project`, y `company` si se sabe) o a la documentación
    general (ambos vacíos). `document` es el nombre del archivo o parte de él."""
    listing = _client.get("/v1/documents")
    listing.raise_for_status()
    wanted = document.lower()
    matches = [d for d in listing.json()["documents"] if wanted in d["filename"].lower()]
    if not matches:
        return f"No hay ningún documento indexado que se llame «{document}»."
    if len(matches) > 1:
        names = ", ".join(d["filename"] for d in matches[:10])
        return f"Hay varios documentos que encajan con «{document}»: {names}. Sé más preciso."
    response = _client.patch(
        f"/v1/documents/{matches[0]['id']}/scope", json=_scope(company, project)
    )
    if message := _api_message(response):
        return message
    response.raise_for_status()
    meta = response.json().get("doc_metadata") or {}
    where = " › ".join(x for x in (meta.get("company"), meta.get("project")) if x) or "general"
    return f"{matches[0]['filename']} ahora pertenece a: {where}."


@mcp.tool()
def jarvis_jobs() -> str:
    """Lista los trabajos de indexación/inferencia activos o recientes."""
    response = _client.get("/v1/jobs")
    response.raise_for_status()
    jobs = response.json()["jobs"]
    active = [j for j in jobs if j["status"] not in {"completed", "failed", "cancelled"}]
    if not active:
        return "No hay trabajos activos."
    return "\n".join(
        f"- {j['id']} [{j['job_type']}] {j['status']} ({j['progress']}%)" for j in active
    )


@mcp.tool()
def jarvis_cancel_job(job_id: str) -> str:
    """Cancela un trabajo por su identificador."""
    response = _client.post(f"/v1/jobs/{job_id}/cancel")
    response.raise_for_status()
    job = response.json()
    return f"Trabajo {job['id']} -> {job['status']}"


# --- Actas de reunión ---------------------------------------------------------------------

AUDIO_SUFFIXES = {".ogg", ".oga", ".opus", ".mp3", ".m4a", ".mp4", ".wav", ".webm", ".flac", ".aac"}
# Además de los adjuntos de Telegram: el vault de Obsidian (la grabadora de audio de
# Obsidian guarda ahí y LiveSync lo trae al servidor) para reuniones de más de 20 MB,
# el límite de descarga de los bots de Telegram.
JARVIS_VAULT_DIR = Path(
    os.environ.get("JARVIS_VAULT_DIR", Path.home() / ".openclaw" / "wiki" / "main")
)
MEETING_AUDIO_ROOTS = (*UPLOAD_ALLOWED_ROOTS, JARVIS_VAULT_DIR)
MEETING_WAIT_SECONDS = DOCGEN_WAIT_SECONDS


def _resolve_audio(file_path: str) -> Path | None:
    """Ruta, nombre del adjunto o, si viene vacío, el audio más reciente (últimas 24 h)."""
    if file_path:
        candidate = Path(file_path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        wanted = Path(html.unescape(file_path))
        wanted_stem = _safe_stem(wanted.stem)
        matches = [
            path
            for root in MEETING_AUDIO_ROOTS
            if root.is_dir()
            for path in root.rglob("*")
            if path.suffix.lower() in AUDIO_SUFFIXES
            and (
                path.name == wanted.name
                or path.stem.removeprefix("input-").split("---", 1)[0] == wanted_stem
            )
        ]
    else:
        cutoff = time.time() - 24 * 3600
        matches = [
            path
            for root in MEETING_AUDIO_ROOTS
            if root.is_dir()
            for path in root.rglob("*")
            if path.suffix.lower() in AUDIO_SUFFIXES and path.stat().st_mtime >= cutoff
        ]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime).resolve()


def _save_minutes_in_vault(job_id: str, result: dict) -> str:
    """Acta en el vault (memoria del proyecto, visible en Obsidian) e indexada en el RAG."""
    minutes = result["minutes"]
    project = result.get("project") or ""
    project_dir = _slug(project) if project else "reuniones"
    folder = JARVIS_VAULT_DIR / "sources" / "proyectos" / project_dir / "actas"
    target = folder / f"{minutes['fecha']}-{_slug(minutes['titulo'])}.md"
    notes = []
    if not target.exists():
        response = _client.get(f"/v1/meetings/{job_id}/markdown")
        response.raise_for_status()
        folder.mkdir(parents=True, exist_ok=True)
        body = response.text
        # Marca de fuente en bruto: el compilador del wiki no la reescribe (docs/MEMORY.md).
        body = body.replace("---\n\n", "---\n\n<!-- openclaw:wiki:raw-source -->\n\n", 1)
        target.write_text(body, encoding="utf-8")
        rel = target.relative_to(JARVIS_VAULT_DIR)
        notes.append(f"Acta guardada en Obsidian: {rel}")
        params = {k: v for k, v in _scope(result.get("company") or "", project).items() if v}
        with target.open("rb") as fh:
            upload = _client.post(
                "/v1/documents", params=params, files={"file": (target.name, fh, "text/markdown")}
            )
        if upload.status_code >= 400:
            notes.append(f"No se indexó en el RAG: {_api_message(upload) or upload.status_code}")
        else:
            scope = f" (proyecto {project})" if project else ""
            notes.append(f"Acta indexada en el RAG{scope}.")
    return "\n".join(notes)


def _format_meeting_minutes(job_id: str, result: dict) -> str:
    m = result["minutes"]
    lines = [
        f"Acta lista (trabajo {job_id}): «{m['titulo']}», {m['fecha']}, "
        f"grabación de {result.get('duration', '?')}.",
        f"Resumen: {m['resumen']}",
    ]
    if m.get("decisiones"):
        lines.append("Decisiones: " + " | ".join(m["decisiones"]))
    if m.get("acciones"):
        lines.append(f"Acciones ({len(m['acciones'])}):")
        for n, a in enumerate(m["acciones"], start=1):
            who = a.get("responsable") or "sin responsable"
            when = a.get("fecha_limite") or "sin fecha"
            lines.append(f"  {n}. {a['tarea']} — {who}, {when}")
    if m.get("riesgos"):
        lines.append(f"Riesgos ({len(m['riesgos'])}):")
        for n, r in enumerate(m["riesgos"], start=1):
            lines.append(
                f"  {n}. {r['riesgo']} (prob. {r.get('probabilidad') or '?'}, "
                f"impacto {r.get('impacto') or '?'}; mitigación: {r.get('mitigacion') or '—'})"
            )
    if m.get("proxima_reunion"):
        lines.append(f"Próxima reunión: {m['proxima_reunion']}")
    try:
        saved = _save_minutes_in_vault(job_id, result)
        if saved:
            lines.append(saved)
    except (httpx.HTTPError, OSError) as exc:
        lines.append(f"No se pudo guardar el acta en Obsidian/RAG: {exc}")
    try:
        path = _download_generated_document(
            job_id, {"kind": "acta", "topic": m["titulo"], "format": result.get("format", "pdf")}
        )
        lines += [
            "Escribe a Romen en tu respuesta el resumen, las decisiones, las acciones y los "
            "riesgos de arriba (no digas 'ver arriba': él no ve este texto).",
            "Para enviar el acta a Romen, termina tu respuesta con esta línea EXACTA, sola en "
            "su propia línea, sin comillas, negritas ni bloque de código:",
            f"MEDIA:{path}",
        ]
    except httpx.HTTPError as exc:
        lines.append(f"No se pudo recuperar el archivo del acta: {exc}")
    if m.get("acciones") or m.get("riesgos"):
        lines.append(
            "Pregunta a Romen si quiere crear estas acciones y riesgos en OpenProject; si dice "
            f'que sí, llama a jarvis-pm__pm_import_minutes(project, job_id="{job_id}").'
        )
    lines.append(
        f'Para enviarla por correo: jarvis_email_draft(..., attachment_job_id="{job_id}").'
    )
    return "\n".join(lines)


@mcp.tool()
def jarvis_meeting_minutes(
    file_path: str = "",
    project: str = "",
    company: str = "",
    title: str = "",
    meeting_date: str = "",
    format: str = "pdf",
) -> str:
    """Hace el acta de una reunión a partir de su grabación: transcribe el audio (también
    de varias horas), extrae resumen, decisiones, acciones con responsable y fecha, y
    riesgos, y devuelve el acta en `format` (pdf, docx o md). La guarda también en
    Obsidian y en el RAG del proyecto.

    `file_path`: nombre del audio adjunto en Telegram, ruta o nombre de un audio del vault
    de Obsidian o de ~/jarvis-inbox; vacío = el audio más reciente recibido.
    `project`: proyecto al que pertenece (pregúntalo si no se sabe) y `company`, su
    empresa, si se sabe. `meeting_date`:
    AAAA-MM-DD, por defecto hoy. Tarda unos minutos y espera aquí; si se agota la espera
    devuelve el trabajo para recogerlo con jarvis_job_result."""
    path = _resolve_audio(file_path)
    if path is None:
        where = f"con el nombre {file_path}" if file_path else "en las últimas 24 horas"
        return (
            f"No encuentro ninguna grabación {where}. Envíala por Telegram (hasta 20 MB) o "
            "guárdala en el vault de Obsidian o en ~/jarvis-inbox."
        )
    if not any(path.is_relative_to(root) for root in MEETING_AUDIO_ROOTS):
        return "Ruta no autorizada para grabaciones."
    params = {
        **_scope(company, project),
        "title": title,
        "meeting_date": meeting_date,
        "format": format,
    }
    with path.open("rb") as fh:
        response = _client.post(
            "/v1/meetings",
            params={k: v for k, v in params.items() if v},
            files={"file": (path.name, fh)},
            timeout=600.0,
        )
    if response.status_code == 422:
        return response.json().get("message") or "Petición de acta inválida."
    response.raise_for_status()
    job_id = response.json()["id"]

    deadline = time.monotonic() + MEETING_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(_DOCGEN_POLL_SECONDS)
        poll = _client.get(f"/v1/jobs/{job_id}")
        poll.raise_for_status()
        job = poll.json()
        if job["status"] == "completed":
            return _format_meeting_minutes(job_id, job.get("result") or {})
        if job["status"] in {"failed", "cancelled"}:
            return f"Trabajo {job_id} {job['status']}: {job.get('error') or 'sin detalle'}"
    return (
        f"El acta sigue preparándose (trabajo {job_id}, {path.name}). Dile a Romen que la "
        "grabación es larga y recógela con jarvis_job_result cuando la pida."
    )


if __name__ == "__main__":
    mcp.run()
