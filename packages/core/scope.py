"""Ámbito de un documento o de una consulta: global, empresa o proyecto de una empresa.

Es la misma jerarquía que OpenProject (empresa = proyecto raíz, proyecto = hijo) y los
identificadores se normalizan igual (`slugify`), así que "Migración ERP" en el RAG, en el
vault y en OpenProject es `migracion-erp`.

* Global: documentación general (PMBOK, metodologías); la ve cualquier consulta.
* Empresa: manuales, plantillas y normas de una empresa; la ven sus proyectos.
* Proyecto: pliegos, actas, entregables; solo la ve ese proyecto.
"""

import re
import unicodedata
from dataclasses import dataclass

from packages.core.errors import ValidationFailedError

_MAX_NAME = 128


def slugify(text: str) -> str:
    """Identificador estable: minúsculas sin tildes, cifras y guiones (como OpenProject)."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if slug and not slug[0].isalpha():
        slug = f"p-{slug}"
    return slug[:100]


@dataclass(frozen=True, slots=True)
class Scope:
    company: str = ""
    project: str = ""

    @classmethod
    def of(cls, company: str | None = None, project: str | None = None) -> "Scope":
        company = (company or "").strip()[:_MAX_NAME]
        project = (project or "").strip()[:_MAX_NAME]
        if project and not company:
            raise ValidationFailedError(
                f"Falta la empresa del proyecto «{project}»: todo proyecto pertenece a una."
            )
        return cls(company=company, project=project)

    @property
    def company_id(self) -> str:
        return slugify(self.company) if self.company else ""

    @property
    def project_id(self) -> str:
        return slugify(self.project) if self.project else ""

    @property
    def is_global(self) -> bool:
        return not self.company

    def label(self) -> str:
        if self.project:
            return f"{self.company} › {self.project}"
        return self.company or "general"

    def metadata(self) -> dict:
        """Nombres legibles para `documents.doc_metadata`."""
        data = {}
        if self.company:
            data["company"] = self.company
        if self.project:
            data["project"] = self.project
        return data

    def payload(self) -> dict:
        """Identificadores para el payload de Qdrant (vacío = global)."""
        return {"company": self.company_id or None, "project": self.project_id or None}


def scope_from_metadata(metadata: dict | None) -> Scope:
    """Ámbito guardado en `doc_metadata`. Los documentos anteriores a las empresas solo
    tenían `project`: sin empresa se consideran globales."""
    metadata = metadata or {}
    company = str(metadata.get("company") or "").strip()
    project = str(metadata.get("project") or "").strip() if company else ""
    return Scope(company=company, project=project)
