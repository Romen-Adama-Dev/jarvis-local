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

## Una sola memoria: el árbol de Jarvis, Obsidian y OpenProject

El vault es **la** memoria de Jarvis. Lo que sabe de tus proyectos está en él como un árbol
de notas enlazadas, y OpenProject y Jarvis leen y escriben ese mismo árbol:

```
OpenProject (proyectos, tareas, hitos, riesgos, reuniones, wiki) ─┐
Actas del vault · documentos del RAG ─────────────────────────────┤
                                                                  ▼
                         vault de Obsidian: árbol de Jarvis ─── LiveSync ─► iPhone, portátil
                           │            ▲                     └── git ─► jarvis-vault (historial)
    wiki de OpenProject ◄──┘            └── Jarvis: "recuerda que…" (jarvis_remember)
    ("Memoria de Jarvis")                   y memory_search sobre todo el vault
```

* **`knowledge`** (perfiles `vault` o `livesync`, `packages/knowledge/red.py`) regenera
  cada `KNOWLEDGE_REFRESH_SECONDS` (10 min) **un solo árbol** con todo lo que Jarvis sabe
  (ver más abajo): empresas, proyectos y sus personas; conocimiento (metodologías,
  documentación, temas y directivas), y los nexos que unen ramas. Las actas se mueven a
  su reunión dentro del árbol. Todas las notas llevan el frontmatter del wiki de OpenClaw
  (`pageType`, `entityType`, `relationships`), así que Jarvis las usa como memoria
  estructurada.
* **`openproject-wiki-sync`** (perfil `pm`) publica la nota de cada empresa y proyecto en
  la wiki de OpenProject (página **Memoria de Jarvis**, con el diagrama del árbol) y copia
  al vault las demás páginas de su wiki, en la carpeta `Wiki/` del proyecto (`📖 <página>`).
  Encuentra las notas por el índice que deja la red en `.jarvis/arbol.json`.
* **Jarvis**: "recuerda que en Web corporativa el cliente prefiere los viernes" →
  `jarvis_remember` lo añade a la sección **Notas** de esa nota; sale en Obsidian, en la
  wiki del proyecto y en `memory_search`. Si es alguien o algo que aún no tiene nota,
  la crea: una persona en `👥 Contactos` (pasa sola al equipo de su empresa cuando
  aparece trabajando con ella), una metodología en `🗂 Metodologías` (cada método en su
  nota, sin mezclarse) o un tema general en `🗂 Temas`.
* **Directivas de Jarvis**: lo que le pides que sea parte de su forma de trabajar ("a
  partir de ahora…") lo escribe él en el `MEMORY.md` de su workspace, que OpenClaw le
  carga en cada conversación y que un reinicio no pisa; si cambias de criterio, lo
  sobrescribe dentro de su zona (**General**, **Metodologías** con una zona por método,
  **Proyectos** con el método de cada uno; ver "Metodologías por proyecto" en
  [EMPRESAS.md](EMPRESAS.md)). `knowledge` copia ese archivo al vault como
  `🧠 Directivas de Jarvis` (rama Conocimiento), de solo lectura, y las reglas de cada
  metodología salen también en su nota `📐`: para cambiarlas, pídeselo a Jarvis. El
  *dreaming* de OpenClaw está desactivado para que nada reescriba ese archivo por su
  cuenta. La plantilla (`integrations/openclaw/workspace/MEMORY.md`) no trae ninguna
  directiva ni método de trabajo: cada usuario le dicta los suyos. Ejemplos para trabajo
  predictivo, Scrum y Kanban en [ejemplos/directivas.md](ejemplos/directivas.md).

Dónde escribir cada cosa:

| Quieres... | Escríbelo en |
|---|---|
| Notas tuyas sobre un proyecto, empresa, persona, metodología o tema | Su nota en Obsidian, **fuera** del bloque `jarvis:red` (p. ej. en `## Notas`). Se conserva al regenerar, viaja con la nota si cambia de rama y, si es de empresa o proyecto, se publica en OpenProject |
| Documentación de proyecto para el equipo | La wiki de OpenProject (cualquier página salvo *Memoria de Jarvis*): llega al vault |
| Tareas, fechas, riesgos | OpenProject (o por Telegram); el árbol se actualiza solo |

Lo que hay entre `<!-- jarvis:red:start -->` y `<!-- jarvis:red:end -->` se regenera;
*Memoria de Jarvis* en OpenProject se sobrescribe desde Obsidian. Nada se borra solo: si
quitas algo de OpenProject, su nota se queda hasta que la borres.

### Un solo árbol, unido por nexos

Cada nota cuelga de **una sola** nota padre, y la carpeta es el árbol, así que el
explorador de Obsidian ya te sirve de índice. Todo sale del núcleo, `🧭 Mapa de Jarvis`
(en la raíz del vault, con el diagrama de todo el árbol):

```
🧭 Mapa de Jarvis
├── 🗂 Empresas                         entities/Empresas/
│   └── 🏢 Estudio Delta                entities/Empresas/Estudio Delta/
│       ├── 👥 Equipo de Estudio Delta  → 👤 Lucía Martín, 👤 Diego Sanz…
│       ├── 🗃 Documentos de Estudio Delta → 📄 …
│       └── 📁 App de reservas          …/App de reservas/
│           ├── 🏁 Hitos de App de reservas      → 🏁 Puesta en marcha
│           ├── ⚠️ Riesgos de App de reservas    → ⚠️ El proveedor de pagos tarda…
│           ├── 📅 Reuniones de App de reservas  → 📅 2026-09-24 · Kick-off → 📝 su acta
│           ├── ✅ Tareas de App de reservas     → ✅ las que pesan
│           └── 🗃 Documentos de App de reservas → 📄 Brief app reservas
├── 📚 Conocimiento                     concepts/Conocimiento/
│   ├── 🗂 Metodologías → 📐 PMI → 📄 PMBOK 7Ed, 📄 Snyder…
│   ├── 🗃 Documentación general → 📄 …
│   ├── 🗂 Temas → 💡 …
│   ├── 📖 Glosario → 📖 Glosario · Scrum, · Kanban, · Lean… (docs/GLOSARIO.md)
│   └── 🧠 Directivas de Jarvis
├── 🕸 Nexos                            entities/Nexos/ → 🔗 personas de varias empresas
├── 👥 Contactos                        personas que aún no trabajan con ninguna empresa
└── 📅 Agenda                           reuniones y actas sin proyecto
```

Las reglas:

* **El hijo declara su padre** (`relationships: pertenece-a`) y enlaza solo con él; el
  padre lista a sus hijos. Las hojas (hitos, riesgos, reuniones, tareas, documentos) **no
  enlazan** con personas ni con conceptos: los nombran en texto. Así el grafo es un árbol
  y no una maraña. Las relaciones completas (responsable, equipo, metodología…) siguen en
  el frontmatter, que es lo que lee Jarvis y que Obsidian no dibuja.
* **Las personas viven en el equipo de su empresa** (`👥 Equipo de <Empresa>`), con lo que
  hacen allí en texto. El propietario (`JARVIS_OWNER_NAME`) no tiene nota: es el núcleo.
* **Lo que une ramas es un nexo**, una nota con varias relaciones que hace de puente, nunca
  un enlace suelto entre hojas:
  * una persona que trabaja con **dos o más empresas** no cuelga de ninguna: es `🔗 Persona`
    en `🕸 Nexos`, enlaza con el equipo de cada empresa y explica el motivo (su rol, en qué
    proyectos y qué hace en cada una);
  * una **metodología** (`📐 PMI`) une el conocimiento con los proyectos que la usan (la
    zona *Proyectos* de `MEMORY.md`).
  En los diagramas, los nexos son líneas de puntos.
* **Las tareas** solo tienen nota propia cuando pesan —están bloqueadas o en espera, o las
  nombra un acta—; el resto son líneas de `✅ Tareas de <Proyecto>`.
* **Las actas** cuelgan de su reunión (mismo proyecto y fecha) o, si no la hay, de las
  reuniones del proyecto. Jarvis las guarda ya en su sitio si el proyecto existe; si no,
  en `sources/proyectos/` y la red las mueve cuando aparece.
* **Nombres que se entienden**: un icono por tipo y el título, sin códigos (`⚠️ Retraso del
  proveedor`, `📅 2026-09-24 · Kick-off`). El número de OpenProject está en la nota y en su
  `id`; solo se añade al nombre si dos notas de la misma carpeta se llaman igual.
* **Si algo cambia de rama** (una persona empieza a trabajar con una segunda empresa, un
  contacto entra en un equipo, cambias el título de una tarea), la nota se mueve con lo que
  hayas escrito fuera del bloque: se reconoce por su `id`, no por su nombre. Los enlaces
  llevan la ruta completa, así que dos notas pueden llamarse igual en carpetas distintas.

Cada empresa, proyecto, metodología y nexo lleva un **diagrama** (Mermaid, que Obsidian y
OpenProject dibujan) con su parte del árbol.

### Verlo como árbol

Abre la **vista de grafo** (icono del grafo o `Ctrl/Cmd+G`) y, en sus ajustes:

* **Filtros**: `-path:reports -path:sources -file:index -file:AGENTS -file:WIKI`. Quita los
  índices y los informes del plugin de memoria, que enlazan con todas las notas y harían
  de estrella en el centro.
* **Grupos** (uno por rama, con su color): `path:entities/Empresas`,
  `path:concepts/Conocimiento`, `path:entities/Nexos`, `path:entities/Contactos`; o por
  tipo: `tag:#empresa`, `tag:#proyecto`, `tag:#persona`, `tag:#nexo`, `tag:#riesgo`,
  `tag:#hito`, `tag:#reunion`, `tag:#tarea`, `tag:#documento`, `tag:#metodologia`.
* Para ver solo una empresa: `path:"entities/Empresas/Estudio Delta"`.

Los ajustes de la vista son de cada dispositivo. Los iconos de los nombres ya distinguen el
tipo de cada nodo sin configurar nada.

Si vienes de la estructura anterior (`entities/empresas/…`, `entities/personas/`,
`concepts/Gestión de riesgos`…), sus notas no se mueven solas: vacía esas carpetas (tras
una copia, `scripts/backup`) y la siguiente pasada crea el árbol nuevo. Lo que escribiste a
mano en ellas sigue en el historial git del vault.

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
| Notas borradas del vault que siguen en el móvil | Borradas con el puente parado (reinicio, recompilación): el puente del upstream no las detectaba y quedaban en CouchDB para siempre (así quedaron 27 notas de proyectos de prueba y de la estructura plana anterior al árbol, visto el 21-09). `infra/livesync-bridge/offline-deletions.patch` lo arregla: al arrancar, cada archivo que el puente conocía y ya no está se borra también en CouchDB (`Offline deletions detected: N` en el log). Si falta más de la mitad de lo conocido (vault vacío o sin montar, restauración a medias) no borra nada y lo avisa. Las notas nuevas del móvil no se tocan: el puente nunca las vio en el vault. |

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
| livesync-bridge | commit `c3760be` de `vrtmrz/livesync-bridge` (sin releases publicadas) más `infra/livesync-bridge/offline-deletions.patch` (imagen `jarvis-livesync-bridge:c3760be-borrados`) |
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
