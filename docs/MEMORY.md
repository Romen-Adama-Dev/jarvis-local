# Memoria evolutiva (Obsidian)

Capa de memoria persistente y editable a mano por el propietario, distinta
del RAG (`docs/ARCHITECTURE.md`, Qdrant): el RAG responde sobre el **corpus
documental** (PMBOK, actas, requisitos subidos); esta memoria guarda lo que
**Jarvis aprende con el uso** — decisiones de proyecto, riesgos, preferencias
del propietario, resúmenes de sesión — como notas Markdown compatibles con
[Obsidian](https://obsidian.md).

## No hace falta construirlo: ya viene con OpenClaw

Investigando la implementación se descubrió que **OpenClaw ya trae de fábrica**
justo esto, como dos plugins bundled:

* **`memory-core`** (activado por defecto) — el motor de memoria: notas de
  sesión (`~/.openclaw/workspace-jarvis/memory/YYYY-MM-DD.md`), `MEMORY.md`
  curada, y un pipeline de consolidación ("dreaming": promueve recuerdos de
  corto plazo a `MEMORY.md` con `openclaw memory promote`, búsqueda con
  embeddings, `openclaw memory search`). Ya documentado parcialmente en
  `integrations/openclaw/workspace/AGENTS.md`.
* **`memory-wiki`** (bundled, deshabilitado por defecto — activado en esta
  rama) — compilador de wiki persistente **Obsidian-friendly**: renderiza
  frontmatter, `[[wikilinks]]`, backlinks y dashboards; en modo `bridge`
  importa los artefactos públicos de `memory-core` (notas de sesión, memoria
  curada) al mismo vault. Expone las herramientas MCP `wiki_search`,
  `wiki_get`, `wiki_apply`, `wiki_lint`, `wiki_status` y el CLI `openclaw wiki`.

Por eso este documento ya no describe una skill MCP nueva (como se planteó al
principio): sería reinventar algo que el propio agente ya trae, mejor hecho
(pipeline de consolidación con LLM, índice de búsqueda, backlinks
automáticos). El trabajo real es **activarlo y configurarlo bien**.

## Configuración aplicada (`integrations/openclaw/config/openclaw.template.json`)

```jsonc
"plugins": {
  "entries": {
    "memory-wiki": {
      "enabled": true,
      "config": {
        "vaultMode": "bridge",              // importa los artefactos de memory-core
        "vault": { "scope": "global", "renderMode": "obsidian" },
        "obsidian": { "enabled": true, "useOfficialCli": false },
        "bridge": {
          "enabled": true,
          "readMemoryArtifacts": true,
          "indexDailyNotes": true,
          "indexMemoryRoot": true,
          "followMemoryEvents": true
        },
        "search": { "corpus": "all" },       // busca en wiki + memoria
        "render": {
          "preserveHumanBlocks": true,        // no pisa lo que edites a mano
          "createBacklinks": true,
          "createDashboards": true
        }
      }
    }
  },
  "allow": ["searxng", "memory-wiki"]
}
```

`useOfficialCli: false` porque este servidor no corre la app de escritorio de
Obsidian (es un CLI que se conecta a la app en ejecución, ver
`~/.npm-global/lib/node_modules/openclaw/skills/obsidian/SKILL.md`): sin
Obsidian abierto en la propia VM, `memory-wiki` sigue funcionando escribiendo
Markdown plano directamente — el CLI oficial solo aporta atajos (búsqueda,
propiedades, tareas) cuando hay una instancia de Obsidian corriendo al lado.

`wiki_apply`, `wiki_get`, `wiki_lint`, `wiki_search`, `wiki_status` se añaden
también a `tools.sandbox.alsoAllow` en la plantilla (por si en el futuro se
activa sandbox; hoy `sandbox.mode` sigue en `"off"`, ver `docs/OPENCLAW.md`).

## Dónde vive el vault y qué hay dentro

`~/.openclaw/wiki/main/` (creado automáticamente por el plugin al activarse):

```
wiki/main/
├── AGENTS.md          # instrucciones del propio plugin para el agente
├── WIKI.md            # metadatos del vault (modo, render, corpus)
├── index.md
├── sources/           # capa de evidencia: notas en bruto (las escribimos aquí)
├── entities/          # páginas de síntesis auto-compiladas (personas, sistemas...)
├── concepts/
├── syntheses/         # páginas de resumen gestionadas (`wiki apply synthesis`)
├── reports/           # auditorías auto-generadas (contradicciones, huecos, huérfanos...)
└── _attachments/
```

`sources/` es la capa de evidencia sin gestionar por el compilador si la nota
lleva el marcador `<!-- openclaw:wiki:raw-source -->` cerca del principio —
así es como Jarvis anota conocimiento de PM sin que el compilador la
reescriba. `entities/`, `concepts/` y `syntheses/` son la capa sintetizada
que el propio plugin construye a partir de `sources/` y de lo importado en
modo `bridge`.

### Convención de proyectos (Jarvis debe seguirla, ver `AGENTS.md`)

```
sources/proyectos/<slug>/
├── resumen.md
├── decisiones.md
├── riesgos.md
└── reuniones/YYYY-MM-DD.md
```

Cada nota empieza con `<!-- openclaw:wiki:raw-source -->` y usa
`[[wikilinks]]` para relacionar notas entre sí (p. ej. una entrada de
`decisiones.md` enlaza a la reunión donde se tomó). El resto de contenido
(memoria de usuario, resúmenes de sesión) ya llega solo por el `bridge` desde
`memory-core` — no hace falta replicarlo a mano.

## Auditabilidad de lo que Jarvis escribe sin confirmación

A diferencia de correo/calendario, anotar una nota de memoria no tiene efecto
externo, así que no pasa por `packages/security/confirmation.py` — Jarvis
escribe directamente. `reports/` (auto-generado por `wiki lint`) ya cubre
parte del control de calidad (contradicciones, páginas huérfanas, baja
confianza); además, `~/.openclaw/wiki/main/` puede versionarse con `git init`
igual que cualquier otro directorio si se quiere un historial revertible
línea a línea — decisión pendiente, no crítica dado que `reports/` ya
señala anomalías.

## Sincronización: cómo lo abres de verdad en Obsidian

El vault vive en el servidor (`jarvis-gpu`); Obsidian corre en tu portátil o
móvil. Hace falta sincronizar `~/.openclaw/wiki/main/`. Opciones, de menor a
mayor fricción:

* **`git clone`/`git pull` manual** (si se decide versionar el vault) — sin
  coste, sin servicio nuevo, sincronización a demanda.
* **Syncthing** (self-hosted, P2P, sin servidor de terceros) — sincronización
  continua, encaja con los criterios ya declarados en `docs/INTEGRACIONES.md`
  (sin dependencia de APIs de pago, self-hosted).
* **Obsidian Sync** (servicio de pago de los propios creadores de Obsidian) —
  la más cómoda, pero rompe el criterio "sin dependencia de proveedores
  externos de pago" que gobierna el resto del proyecto. No recomendado salvo
  que lo aceptes explícitamente para esta pieza en concreto.

**Pendiente de decidir contigo**: cuál de las dos primeras opciones montamos
y en qué dispositivo(s) quieres el vault.

## Verificación en esta VM

```bash
openclaw wiki status   # confirma vault, modo, render, bridge
openclaw wiki doctor    # audita la configuración
```

Ejecutado ya en `jarvis-gpu`: `Render mode: obsidian`, `Bridge: enabled`,
vault en `/home/adamacaetanoramirez/.openclaw/wiki/main`. El aviso "Bridge
mode is enabled but the active memory plugin is not exporting any public
memory artifacts yet" es esperable con cero conversaciones registradas
todavía; se resuelve solo en cuanto `memory-core` tenga sesiones que
exportar.

## Pendiente

* Primera nota de proyecto real (`sources/proyectos/<slug>/resumen.md`) para
  validar que el flujo completo (escritura → `wiki lint`/compilación →
  `wiki_search`) funciona de punta a punta.
* Decidir sincronización (Syncthing vs. `git clone` manual) y, si aplica,
  `git init` del vault.
