# Obsidian: la memoria de Jarvis en el móvil y el portátil

Cómo abrir y editar desde Obsidian (iPhone, Android, portátil) el vault donde Jarvis
guarda lo que aprende (`docs/MEMORY.md`), con sincronización en tiempo real y sin
exponer nada a internet.

## Cómo funciona

```
Obsidian (iPhone, portátil)                servidor
  plugin Self-hosted LiveSync  ──Tailscale──► https://jarvis.<tailnet>.ts.net:8443
                                                 │  (tailscale serve)
                                                 ▼
                                              couchdb  ◄──►  livesync-bridge  ◄──►  vault en disco
                                                                                    ~/.openclaw/wiki/main
                                                                                       ▲        │
                                                                     OpenClaw (memory-wiki)     vault-sync
                                                                     lee y escribe notas        git → GitHub (historial)
```

* **Self-hosted LiveSync** es un plugin comunitario de Obsidian que sincroniza el vault
  con una base de datos CouchDB propia, en tiempo real y con cifrado de extremo a extremo.
* **`couchdb`** guarda las notas cifradas. Escucha solo en `127.0.0.1` y el servicio
  `tailscale` la publica en el puerto 8443 del nombre `*.ts.net`: solo llegan tus
  dispositivos del tailnet, con HTTPS válido (obligatorio en iOS).
* **`livesync-bridge`** copia en los dos sentidos entre CouchDB y los archivos Markdown
  del vault del servidor, que son los que lee y escribe Jarvis. No sincroniza `.git` ni
  `.openclaw-wiki/` (estado interno del plugin de memoria).
* **`livesync-init`** (se ejecuta y termina) configura CouchDB, escribe la configuración
  del puente y genera el **Setup URI**: un enlace cifrado con todos los ajustes, para
  configurar cada dispositivo pegándolo.
* **`vault-sync`** (perfil `vault`) sigue guardando cada cambio como commit en el repo git
  privado: historial, copia de seguridad y posibilidad de revertir lo que escriba Jarvis.

Contraseñas (las genera `init` en el volumen `jarvis_runtime`; puedes fijarlas en `.env`):

| Secreto | Para qué | `.env` |
|---|---|---|
| `couchdb_password` | Usuario `jarvis` de CouchDB | `COUCHDB_PASSWORD` |
| `livesync_passphrase` | Cifrado de extremo a extremo de las notas | `LIVESYNC_PASSPHRASE` |
| `livesync_uri_passphrase` | Abrir el Setup URI | `LIVESYNC_URI_PASSPHRASE` |

## Configurarlo (servidor, una vez)

Requiere el acceso por Tailscale ya funcionando (`docs/ACCESO-REMOTO.md`).

1. En `.env`, añade `livesync` a los perfiles:

   ```bash
   COMPOSE_PROFILES=vault,tailscale,livesync
   ```

2. Arranca:

   ```bash
   docker compose up -d
   ```

3. Comprueba:

   ```bash
   docker compose logs livesync-init
   # CouchDB provisioning completed.
   # Servidor: https://jarvis.<tailnet>.ts.net:8443
   docker compose logs livesync-bridge | grep saved | tail   # notas subidas a CouchDB
   ```

Si `livesync-init` avisa de que no hay Tailscale conectado, une primero el servidor al
tailnet y relanza `docker compose up -d livesync-init`.

## Configurar Obsidian (cada dispositivo)

1. Muestra el Setup URI y su contraseña en el servidor:

   ```bash
   docker compose exec openclaw cat /run/jarvis/livesync_setup_uri
   docker compose exec openclaw cat /run/jarvis/livesync_uri_passphrase
   ```

   Pásalos al dispositivo por canales distintos (p. ej. el URI por una nota y la
   contraseña escribiéndola), o cópialos desde una sesión SSH en el propio dispositivo.
   Si no puedes copiar desde la terminal, envía el URI a tu chat de Telegram con el bot
   y cópialo desde allí (la contraseña, aparte):

   ```bash
   set -a && . ./.env && set +a
   curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
     --data-urlencode "chat_id=${TELEGRAM_AUTHORIZED_USER_IDS%%,*}" \
     --data-urlencode "parse_mode=HTML" \
     --data-urlencode "text=<code>$(docker compose exec -T openclaw cat /run/jarvis/livesync_setup_uri)</code>"
   ```

2. En el dispositivo: Tailscale conectado.
3. En Obsidian: crea un vault **nuevo y vacío** (p. ej. `Jarvis`). No reutilices uno
   sincronizado con Obsidian Git o iCloud para evitar duplicados.
4. **Ajustes → Plugins de la comunidad** → activa los plugins de la comunidad → busca
   e instala **Self-hosted LiveSync** → actívalo.
5. Abre la paleta de comandos (en iPhone, desliza hacia abajo en una nota); los comandos
   del plugin aparecen como **Self-hosted sync: …**. Usa *Use the copied setup URI* (o
   el asistente que aparece al activar el plugin → *Use Setup URI*) → pega el URI →
   escribe la contraseña del URI.
6. En el asistente elige **My remote server is already set up, I want to join it**
   (no *I am setting up a new server*, que reinicializa la base de datos). Cuando
   pregunte, elige que este dispositivo **reciba** los datos del servidor
   (*fetch from remote*), no que los suba: el servidor ya tiene el vault completo.
7. Espera a que termine la primera descarga. A partir de ahí los cambios van y vienen
   en segundos: lo que anota Jarvis aparece en Obsidian, y lo que edites llega al vault
   del servidor.

En el portátil, si antes usabas el plugin Obsidian Git con `jarvis-vault`, pásate a
LiveSync en un vault nuevo y deja ese clon de git sin plugin: git queda solo para el
servidor.

## Una sola memoria: red de conocimiento, Jarvis y OpenProject

El vault es **la** memoria de Jarvis. Lo que sabe de tus proyectos está en él como una red
de notas enlazadas, y OpenProject y Jarvis leen y escriben esa misma red:

```
OpenProject (proyectos, tareas, hitos, riesgos, reuniones, wiki) ─┐
Actas del vault · documentos del RAG ─────────────────────────────┤
                                                                  ▼
                         vault de Obsidian: red de conocimiento ── LiveSync ─► iPhone, portátil
                           │            ▲                     └── git ─► jarvis-vault (historial)
    wiki de OpenProject ◄──┘            └── Jarvis: "recuerda que…" (jarvis_remember)
    ("Memoria de Jarvis")                   y memory_search sobre todo el vault
```

* **`knowledge`** (perfiles `vault` o `livesync`, `packages/knowledge/red.py`) regenera
  cada `KNOWLEDGE_REFRESH_SECONDS` (10 min) una nota por empresa, proyecto, persona, hito,
  riesgo, reunión y documento, más los conceptos *Gestión de riesgos*, *Hitos y
  cronograma*, *Reuniones y actas*, *Documentación* y *Equipo*, y la nota raíz
  **Red de conocimiento**. Las actas reciben un bloque "Red" con enlaces a su proyecto y a
  los asistentes. Las notas llevan el frontmatter del wiki de OpenClaw (`pageType`,
  `entityType`, `relationships`), así que Jarvis las usa como memoria estructurada.
* **`openproject-wiki-sync`** (perfil `pm`) publica la nota de cada empresa y proyecto en
  la wiki de OpenProject (página **Memoria de Jarvis**) y copia al vault las demás páginas
  de la wiki de OpenProject (`sources/openproject/<proyecto>/wiki/`).
* **Jarvis**: "recuerda que en Web corporativa el cliente prefiere los viernes" →
  `jarvis_remember` lo añade a la sección **Notas** de esa nota; sale en Obsidian, en la
  wiki del proyecto y en `memory_search`.

Dónde escribir cada cosa:

| Quieres... | Escríbelo en |
|---|---|
| Notas tuyas sobre un proyecto, empresa o persona | Su nota en Obsidian, **fuera** del bloque `jarvis:red` (p. ej. en `## Notas`). Se conserva al regenerar y se publica en OpenProject |
| Documentación de proyecto para el equipo | La wiki de OpenProject (cualquier página salvo *Memoria de Jarvis*): llega al vault |
| Tareas, fechas, riesgos | OpenProject (o por Telegram); la red se actualiza sola |

Lo que hay entre `<!-- jarvis:red:start -->` y `<!-- jarvis:red:end -->` se regenera;
*Memoria de Jarvis* en OpenProject se sobrescribe desde Obsidian. Nada se borra solo: si
quitas algo de OpenProject, su nota se queda hasta que la borres.

### Verlo como red

Abre la **vista de grafo** (icono del grafo o `Ctrl/Cmd+G`). Para distinguir los tipos,
en *Grupos* añade uno por etiqueta con su color: `tag:#empresa`, `tag:#proyecto`,
`tag:#persona`, `tag:#riesgo`, `tag:#hito`, `tag:#reunion`, `tag:#documento`,
`tag:#concepto`. Con *Filtros → Archivos huérfanos* desactivado se ocultan los índices del
plugin. Los ajustes de la vista son de cada dispositivo.

## Comprobar que funciona

* Crea una nota en el móvil y mira en el servidor:
  `docker compose logs livesync-bridge | grep '<nombre de la nota>'` y
  `ls ~/.openclaw/wiki/main` (o el `OPENCLAW_STATE_PATH` de tu `.env`).
* Pide a Jarvis por Telegram que anote algo en la memoria y ábrelo en Obsidian.
* A los 5 minutos, el cambio aparece como commit en el repo git del vault.

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| El plugin no conecta en el iPhone | Tailscale desconectado en el iPhone, o `tailscale serve status` no muestra el puerto 8443: `docker compose restart tailscale`. |
| `livesync-init` sin Setup URI | El servidor no estaba en el tailnet al arrancar: `docker compose up -d livesync-init`. |
| Error de cifrado o notas ilegibles | La `passphrase` del dispositivo no coincide con `livesync_passphrase`. Vuelve a configurar con el Setup URI. |
| Notas duplicadas o con sufijo de conflicto | Se editó la misma nota a la vez en dos sitios; LiveSync lo marca como conflicto para resolverlo en Obsidian. |
| `livesync-bridge` en reinicio continuo | `docker compose logs livesync-bridge`; si es la caché de Deno, borra el volumen `livesync_bridge_state` y rearranca (vuelve a escanear el vault). |
| Notas creadas en el móvil que no llegan al vault del servidor | Obsidian en segundo plano (iOS pausa la sincronización) o sin Tailscale: ábrelo y lanza *Self-hosted sync: Replicate now*. Si CouchDB las recibió (`docker compose logs couchdb \| grep _bulk_docs`) pero no aparecen en el vault, `docker compose restart livesync-bridge` (visto el 18-09 en la primera sincronización del iPhone). |
| Cambios del vault que no llegan a Obsidian | El puente detecta cambios por eventos del sistema de archivos; tras cambios hechos con el contenedor parado, se recogen al arrancar (`scanOfflineChanges`). |

## Seguridad

* CouchDB no tiene puertos abiertos a internet: solo `127.0.0.1` y el tailnet.
* Las notas viajan y se guardan en CouchDB cifradas con `livesync_passphrase`, y las
  rutas de archivo también se ofuscan.
* El Setup URI incluye la contraseña de CouchDB y la de cifrado, protegidas con
  `livesync_uri_passphrase`: no los compartas juntos.
* `livesync-bridge` monta el estado de OpenClaw completo (para llegar al vault); es el
  proyecto oficial del autor de LiveSync, construido desde un commit fijado.

## Versiones fijadas

| Pieza | Versión |
|---|---|
| CouchDB | imagen `couchdb:3.5.2` |
| livesync-bridge | commit `c3760be` de `vrtmrz/livesync-bridge` (sin releases publicadas) |
| Herramientas de preparación y Setup URI | commit `85a12e3` de `vrtmrz/obsidian-livesync` (`LIVESYNC_UTILS_REF`) |

## Desactivar

Quita `livesync` de `COMPOSE_PROFILES` y `docker compose up -d --remove-orphans`. El vault
del servidor y git no cambian. Para borrar también la base de datos:
`docker volume rm jarvis-local_couchdb_data jarvis-local_couchdb_config`.

## Alternativas descartadas

* **Obsidian Git en el móvil**: en iOS va por HTTPS con token, es lento y falla con
  frecuencia; los cambios tardan hasta 5 minutos.
* **Obsidian Sync**: de pago y en la nube de terceros.
* **Syncthing**: sin cliente oficial en iOS y sin historial.
