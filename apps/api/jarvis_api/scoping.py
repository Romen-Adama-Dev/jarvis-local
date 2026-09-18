"""Ámbito (empresa/proyecto) de las peticiones: se resuelve aquí y se impone siempre en
el filtro de búsqueda, para que ninguna consulta vea documentos de otra empresa."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.models import Document
from packages.core.errors import ValidationFailedError
from packages.core.scope import Scope, scope_from_metadata, slugify


async def known_scopes(session: AsyncSession) -> dict[Scope, int]:
    """Ámbitos con documentos y cuántos tiene cada uno."""
    rows = (
        await session.execute(select(Document.doc_metadata).where(Document.deleted_at.is_(None)))
    ).scalars()
    counts: dict[Scope, int] = {}
    for metadata in rows:
        scope = scope_from_metadata(metadata)
        counts[scope] = counts.get(scope, 0) + 1
    return counts


def _closest(name: str, known: set[str], what: str) -> str:
    """Nombre conocido que corresponde a `name`: igual al normalizarlo o, si no, el único
    que lo contiene ("Globex" → "Globex Corp"). Sin coincidencias se deja tal cual (una
    empresa o un proyecto nuevos al subir un documento)."""
    wanted = slugify(name)
    exact = [k for k in known if slugify(k) == wanted]
    if exact:
        return exact[0]
    partial = sorted(k for k in known if wanted and wanted in slugify(k))
    if len(partial) == 1:
        return partial[0]
    if partial:
        raise ValidationFailedError(f"{what} «{name}» es ambiguo: {', '.join(partial)}.")
    return name


async def resolve_scope(session: AsyncSession, company: str | None, project: str | None) -> Scope:
    """Normaliza empresa y proyecto contra los ya conocidos, y un proyecto sin empresa se
    completa con la empresa de sus documentos si es única."""
    company = (company or "").strip()
    project = (project or "").strip()
    scopes = await known_scopes(session) if (company or project) else {}
    if company:
        company = _closest(company, {s.company for s in scopes if s.company}, "La empresa")
    if project and company:
        in_company = {s.project for s in scopes if s.project and s.company == company}
        project = _closest(project, in_company, "El proyecto")
    if project and not company:
        project = _closest(project, {s.project for s in scopes if s.project}, "El proyecto")
        owners = {s.company for s in scopes if s.project == project}
        if len(owners) == 1:
            company = owners.pop()
        elif owners:
            names = ", ".join(sorted(owners))
            raise ValidationFailedError(
                f"El proyecto «{project}» existe en varias empresas ({names}): indica cuál."
            )
        else:
            raise ValidationFailedError(
                f"No conozco la empresa del proyecto «{project}»: indícala."
            )
    return Scope.of(company, project)


def scoped_filters(filters: dict | None, scope: Scope) -> dict:
    """Filtros de búsqueda con el ámbito impuesto (sustituye cualquier `scope` recibido)."""
    return {
        **(filters or {}),
        "scope": {"company": scope.company_id, "project": scope.project_id},
    }
