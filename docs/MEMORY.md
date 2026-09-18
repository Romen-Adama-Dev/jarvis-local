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
confianza); además, el vault se versiona en un repo git privado (ver
"Sincronización"), así que cada cambio de Jarvis queda como un commit revertible.

## Sincronización con Obsidian

El vault vive en el servidor; Obsidian corre en el portátil o el móvil. Dos capas, ambas
en docker compose:

* **Tiempo real (perfil `livesync`)**: plugin Self-hosted LiveSync de Obsidian contra un
  CouchDB publicado solo por Tailscale, y `livesync-bridge` entre CouchDB y los archivos
  del vault. Configuración y uso en `docs/OBSIDIAN.md`.
* **Historial (perfil `vault`)**: `vault-sync` versiona el vault en un repo git
  **privado** (contiene decisiones de proyecto, preferencias y resúmenes de correos)
  cada `VAULT_SYNC_INTERVAL` segundos (300 por defecto): commit de lo que haya cambiado,
  `pull --rebase` y push. Ignora `.openclaw-wiki/` y el estado local de la app Obsidian.
  Ante un conflicto aborta el rebase y lo deja para resolverlo a mano
  (`docker compose logs vault-sync`). Variables: `VAULT_GIT_URL` (URL SSH) y
  `VAULT_SSH_KEY_PATH` (clave con permiso de escritura en ese repo).

Fuera de docker, `scripts/install-vault-sync git@github.com:<usuario>/jarvis-vault.git`
instala lo mismo como temporizador systemd de usuario.

Descartados: Obsidian Git en el móvil (lento y frágil en iOS), Syncthing (sin cliente
oficial en iOS, sin historial) y Obsidian Sync (de pago, rompe el criterio de no depender
de proveedores externos de pago).

## Búsqueda semántica en la memoria

`memory.search` usa embeddings locales de Ollama (`embeddinggemma`, multilingüe,
~620 MB) mediante el proveedor `ollama-embeddings` de `models.providers`, sin APIs
externas. Antes estaba desactivada (`enabled: false`, herencia de "sin OpenAI"), así que
`memory_search` no encontraba lo anotado. Si se cambia el modelo de embeddings hay que
reconstruir el índice: `openclaw memory index --force --agent main`.

## Verificación en esta VM

```bash
openclaw wiki status   # confirma vault, modo, render, bridge
openclaw wiki doctor    # audita la configuración
```

Ejecutado ya en la VM: `Render mode: obsidian`, `Bridge: enabled`,
vault en `~/.openclaw/wiki/main`. El aviso "Bridge
mode is enabled but the active memory plugin is not exporting any public
memory artifacts yet" es esperable con cero conversaciones registradas
todavía; se resuelve solo en cuanto `memory-core` tenga sesiones que
exportar.

## Pendiente

* Primera nota de proyecto real (`sources/proyectos/<slug>/resumen.md`) para
  validar que el flujo completo (escritura → `wiki lint`/compilación →
  `wiki_search`) funciona de punta a punta.
