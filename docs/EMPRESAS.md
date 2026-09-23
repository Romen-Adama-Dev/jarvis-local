# Empresas y proyectos: documentación aislada

Jarvis puede llevar a la vez varias empresas (clientes, startups) y sus proyectos sin que
la documentación de una aparezca en las respuestas de otra. La jerarquía es la misma en el
RAG, en OpenProject (`docs/OPENPROJECT.md`) y en el vault de Obsidian:

| Nivel | Qué va aquí | Quién lo ve |
|---|---|---|
| **General** | Guías y metodologías (PMBOK, Scrum…), normas públicas | Todas las consultas |
| **Empresa** | Manuales de procesos, plantillas, normas internas, reglas de negocio | Consultas de esa empresa y de sus proyectos |
| **Proyecto** | Pliegos, actas, riesgos, presupuestos, entregables | Solo consultas de ese proyecto |

Una consulta de *Acme › Migración ERP* busca en ese proyecto, en la documentación de
Acme y en la general; nunca en otra empresa ni en otro proyecto. Sin empresa ni proyecto,
solo en la general.

## Cómo está hecho

* **Una colección de Qdrant con el ámbito en cada fragmento** (`company`, `project`), y
  `company` indexado como *tenant* (`is_tenant`): Qdrant agrupa en disco los fragmentos
  de cada empresa y la búsqueda filtrada rinde como si fueran colecciones separadas, sin
  duplicar el índice. Es la forma de multitenencia que recomienda Qdrant frente a una
  colección por cliente, que no escala y complica la documentación compartida.
* **El filtro lo impone la API** (`apps/api/jarvis_api/scoping.py`): `/v1/rag/query`
  y `/v1/documents/generate` reciben `company`/`project` y
  sustituyen cualquier filtro de ámbito que mande el cliente. El modelo no puede saltárselo.
* **Nombres tolerantes**: "globex" se resuelve a "Globex Corp" y "migracion erp" a
  "Migración ERP" si no hay ambigüedad; un proyecto sin empresa se completa con la de sus
  documentos o, al subir, con el proyecto padre en OpenProject. Si hay dos candidatos,
  la API pide que se aclare.
* **Sitio reservado para lo propio**: en una consulta de empresa o proyecto, sus dos
  mejores fragmentos entran en el contexto aunque el reranker prefiera párrafos de la
  documentación general (que suele ser mucho más larga).
* En PostgreSQL, `documents.doc_metadata` guarda los nombres (`company`, `project`); en
  Qdrant van los identificadores normalizados (`acme-consulting`, `migracion-erp`), los
  mismos que usa OpenProject.

## Desde Telegram

* Al mandar un documento, Jarvis pregunta si va al RAG y si es general, de una empresa o
  de un proyecto (y ofrece los que ya existen).
* "¿Qué documentación tengo?" → empresas, proyectos y número de documentos.
* Las preguntas llevan el ámbito de la conversación: "en Migración ERP de Acme, ¿qué se
  decidió sobre…?". Si no está claro de qué proyecto hablas, pregunta.
* "Mueve la guía a general", "ese pliego es del proyecto X" → cambia el ámbito sin
  reindexar (`PATCH /v1/documents/{id}/scope`).
* Las actas de reunión se indexan en su proyecto; los documentos generados (resumen,
  DAFO, plan) usan solo la documentación del ámbito pedido.

## Actualizar una instalación anterior

Los documentos subidos antes no tenían empresa: pasan a ser **generales**. Después de
actualizar, crea los índices y copia a Qdrant el ámbito de cada documento:

```bash
docker compose exec api python -m apps.api.jarvis_api.sync_scopes
```

y reasigna desde Telegram los que sean de una empresa o un proyecto ("mueve X al proyecto
Y de la empresa Z").

## Reranker y licencias

El reranker por defecto (`BAAI/bge-reranker-base`, MIT) está entrenado en inglés y chino y
ordena peor los textos en español. `jinaai/jina-reranker-v2-base-multilingual` los ordena
bien y además es más rápido en CPU (6 s frente a 8,7 s con 24 candidatos en este
servidor), pero su licencia es **CC-BY-NC-4.0**: solo para uso no comercial (p. ej. el
TFM). Se elige con `RAG_RERANKER_MODEL` en `.env`.

## Documentos en otro idioma

La búsqueda léxica (BM25) no cruza idiomas y el reranker por defecto compara mal una
pregunta en español con un párrafo en inglés: un libro en inglés indexado como
documentación general no llegaba nunca a la respuesta si se preguntaba en español. Con
`RAG_QUERY_TRANSLATION=true` (por defecto), el modelo local traduce la pregunta al inglés
(una llamada corta), se busca con las dos, cada lista se reordena con su propia pregunta y
se queda lo mejor de ambas. La respuesta sigue siendo en español y cita las fuentes de los
dos idiomas. Si la traducción falla, se busca solo con la pregunta original.

## Pendiente

* **Permisos por usuario**: hoy Telegram admite solo al propietario, que ve todas las
  empresas. Con varios usuarios, cada uno debería tener su lista de empresas permitidas y
  la API filtrar por ella.
