import pytest
from qdrant_client import models

from apps.api.jarvis_api.scoping import resolve_scope, scoped_filters
from packages.core.errors import ValidationFailedError
from packages.core.scope import Scope, scope_from_metadata, slugify
from packages.rag.store import _build_filter, scope_filter


def test_slugify_matches_openproject_identifiers():
    assert slugify("Migración ERP") == "migracion-erp"
    assert slugify("Acme Consulting, S.L.") == "acme-consulting-s-l"
    assert slugify("2026 Plan") == "p-2026-plan"


def test_scope_requires_company_for_project():
    with pytest.raises(ValidationFailedError, match="empresa"):
        Scope.of(project="Migración ERP")
    scope = Scope.of(" Acme Consulting ", "Migración ERP")
    assert scope.metadata() == {"company": "Acme Consulting", "project": "Migración ERP"}
    assert scope.payload() == {"company": "acme-consulting", "project": "migracion-erp"}
    assert scope.label() == "Acme Consulting › Migración ERP"
    assert Scope.of().payload() == {"company": None, "project": None}


def test_legacy_metadata_without_company_is_global():
    assert scope_from_metadata({"project": "core"}).is_global
    assert scope_from_metadata(None).is_global
    assert scope_from_metadata({"company": "Acme", "project": "ERP"}) == Scope("Acme", "ERP")


def _visible(filter_: models.Filter) -> list:
    """Condiciones del `should` de ámbito, en forma comparable."""
    assert isinstance(filter_.should, list)
    return filter_.should


def test_scope_filter_project_sees_project_company_and_global():
    visible = _visible(scope_filter("acme", "erp"))
    assert isinstance(visible[0], models.IsEmptyCondition)  # global
    company_only, project = visible[1], visible[2]
    assert isinstance(company_only, models.Filter) and isinstance(project, models.Filter)
    assert company_only.must[0].match.value == "acme"  # type: ignore[union-attr]
    assert isinstance(company_only.must[1], models.IsEmptyCondition)  # type: ignore[index]
    assert [c.match.value for c in project.must] == ["acme", "erp"]  # type: ignore[union-attr]


def test_scope_filter_company_and_global_only():
    visible = _visible(scope_filter("acme", ""))
    assert len(visible) == 2
    assert visible[1].match.value == "acme"  # type: ignore[union-attr]
    assert len(_visible(scope_filter("", ""))) == 1


def test_build_filter_wraps_scope_with_other_conditions():
    built = _build_filter({"scope": {"company": "acme", "project": ""}, "document_id": "d1"})
    assert built is not None and len(built.must) == 2  # type: ignore[arg-type]
    assert _build_filter({}) is None


def test_scoped_filters_overrides_client_scope():
    filters = scoped_filters({"scope": {"company": "otra"}, "tags": ["x"]}, Scope("Acme", ""))
    assert filters == {"scope": {"company": "acme", "project": ""}, "tags": ["x"]}


class FakeSession:
    def __init__(self, metadata: list[dict]) -> None:
        self.metadata = metadata

    async def execute(self, _stmt):
        rows = self.metadata

        class Result:
            def scalars(self):
                return iter(rows)

        return Result()


async def test_resolve_scope_completes_company_from_documents():
    session = FakeSession(
        [
            {"company": "Acme Consulting", "project": "Migración ERP"},
            {"company": "Globex Corp", "project": "Portal Clientes"},
            {"project": "core"},
        ]
    )
    scope = await resolve_scope(session, "", "migracion erp")  # type: ignore[arg-type]
    assert scope == Scope("Acme Consulting", "Migración ERP")
    scope = await resolve_scope(session, "globex", "portal")  # type: ignore[arg-type]
    assert scope == Scope("Globex Corp", "Portal Clientes")
    new_project = await resolve_scope(session, "Acme", "Proyecto Nuevo")  # type: ignore[arg-type]
    assert new_project == Scope("Acme Consulting", "Proyecto Nuevo")
    with pytest.raises(ValidationFailedError, match="indícala"):
        await resolve_scope(session, "", "Desconocido")  # type: ignore[arg-type]


async def test_resolve_scope_rejects_ambiguous_project():
    session = FakeSession(
        [
            {"company": "Acme", "project": "Portal"},
            {"company": "Globex", "project": "Portal"},
        ]
    )
    with pytest.raises(ValidationFailedError, match="varias empresas"):
        await resolve_scope(session, "", "Portal")  # type: ignore[arg-type]


async def test_resolve_scope_rejects_ambiguous_company():
    session = FakeSession([{"company": "Acme Iberia"}, {"company": "Acme France"}])
    with pytest.raises(ValidationFailedError, match="ambiguo"):
        await resolve_scope(session, "Acme", "")  # type: ignore[arg-type]


def _chunk(point_id: str, company: str | None = None):
    from packages.rag.store import RetrievedChunk

    return RetrievedChunk(point_id, "d", point_id, "f", None, None, "t", 0.5, company)


def test_scoped_chunks_get_reserved_slots():
    from packages.rag.orchestrator import _reserve_scoped

    reranked = [_chunk(p) for p in "abcd"]
    candidates = [_chunk("x", "globex"), *reranked, _chunk("y", "globex"), _chunk("z", "globex")]
    out = _reserve_scoped(reranked, candidates, limit=2)
    assert [c.point_id for c in out] == ["a", "x", "y", "b"]
    already = [_chunk("x", "globex"), _chunk("a"), _chunk("y", "globex")]
    assert _reserve_scoped(already, candidates, limit=2) == already


def test_own_only_filter_excludes_global():
    visible = _visible(scope_filter("acme", "erp", own_only=True))
    assert len(visible) == 2
    assert not any(isinstance(c, models.IsEmptyCondition) for c in visible)
    # Sin empresa no hay "propio": sigue viendo lo general.
    assert len(_visible(scope_filter("", "", own_only=True))) == 1


def test_scope_rejects_names_without_latin_letters():
    with pytest.raises(ValidationFailedError, match="empresa"):
        Scope.of("Рога и копыта")
    with pytest.raises(ValidationFailedError, match="proyecto"):
        Scope.of("Acme", "проект")


def test_legacy_company_with_empty_slug_is_not_global():
    scope = scope_from_metadata({"company": "Рога и копыта"})
    assert not scope.is_global
    assert scope.payload()["company"]
    assert scope.payload()["company"] != Scope("Otra").payload()["company"]
