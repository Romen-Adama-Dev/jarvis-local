# Glosario de gestión de proyectos

El vocabulario común de Jarvis: unos 450 términos de dirección de proyectos con su
equivalencia oficial español ↔ inglés, sus siglas, una definición breve y su fuente. Está
en `packages/glossary/glosario.md`, en tablas Markdown legibles, una por ámbito:

| Ámbito | Términos | De dónde salen los nombres |
|---|---|---|
| Dirección de proyectos | ~355 | Glosario y siglas de la *Guía del PMBOK* 7.ª ed. en español (los nombres oficiales del PMI), el *APM Glossary* y la lista de AgileSeekers |
| Ágil | 12 | *Manifiesto Ágil*, PMBOK, APM |
| Scrum | 20 | *La Guía de Scrum* 2020, traducción oficial al español europeo |
| Kanban | 12 | *La Guía Kanban* (diciembre de 2020), glosario de su traducción oficial |
| Lean | 20 | *Lean Lexicon* del Lean Enterprise Institute |
| Cascada (predictivo) | 7 | APM, AgileSeekers |
| PRINCE2 y términos británicos | 21 | APM, PRINCE2 |

## Para qué lo usa Jarvis

1. **Traducir la consulta del RAG.** La documentación en inglés (como el libro de
   formularios de Snyder) se busca también con la pregunta traducida (`docs/EMPRESAS.md`).
   Si la pregunta contiene términos del glosario, el modelo recibe sus equivalencias
   oficiales ("Registro de incidentes = Issue log") y no traduce palabra por palabra. Con
   las 20 consultas de `docs/benchmarks/casos/traduccion.json`, los términos correctos
   pasan de **35/39 a 39/39**, sin coste de tiempo (~0,27 s).
2. **Responder al momento.** `jarvis_glosario` (skill `jarvis-rag`) da la definición, la
   equivalencia, las siglas y la fuente de un término sin pasar por el RAG: "¿qué es la
   holgura?", "¿cómo se dice *pila del producto* en inglés?", "¿qué significa SPI?".
3. **En Obsidian.** La rama *📚 Conocimiento › 📖 Glosario* tiene una nota por ámbito con
   su tabla, así que también lo encuentran `memory_search` y `wiki_search`.

Las palabras demasiado generales ("proyecto", "riesgo", "plan"…), los términos que se
escriben igual en los dos idiomas ("Sprint", "Kanban") y los nombres que comparten dos
términos ("entrega": *release* o *handover*) no se pasan como pista de traducción. Las
siglas solo cuentan escritas en mayúsculas ("SPI", no "spi").

## Derechos y fuentes

Los **nombres** de los términos y sus equivalencias son los de las fuentes oficiales; las
**definiciones son propias**, redactadas para Jarvis, porque los glosarios del PMI, APM y
AgileSeekers tienen derechos de autor y este repositorio es público. Las guías de Scrum
(CC BY-SA 4.0) y Kanban (CC BY 4.0) se citan como fuente de sus términos. La tabla de
fuentes completa está al principio de `glosario.md`.

## Añadir o corregir un término

Edita la tabla de su ámbito en `packages/glossary/glosario.md` (una fila: `Español |
English | Siglas | Definición | Fuentes`; los sinónimos van separados por `;`, el primero
es el preferido). `tests/unit/test_glossary.py` comprueba que cada fila tenga definición y
una fuente conocida, y que ningún término esté dos veces. Para un ámbito nuevo, añade una
sección `## Nombre`: saldrá sola como nota nueva en Obsidian.
