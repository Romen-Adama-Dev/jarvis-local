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

2. En el dispositivo: Tailscale conectado.
3. En Obsidian: crea un vault **nuevo y vacío** (p. ej. `Jarvis`). No reutilices uno
   sincronizado con Obsidian Git o iCloud para evitar duplicados.
4. **Ajustes → Plugins de la comunidad** → activa los plugins de la comunidad → busca
   e instala **Self-hosted LiveSync** → actívalo.
5. Abre la paleta de comandos (en iPhone, desliza hacia abajo en una nota) →
   **Self-hosted LiveSync: Use the copied setup URI** (o el asistente que aparece al
   activar el plugin → *Use Setup URI*) → pega el URI → escribe la contraseña del URI.
6. Cuando pregunte, elige que este dispositivo **reciba** los datos del servidor
   (*fetch from remote*), no que los suba: el servidor ya tiene el vault completo.
7. Espera a que termine la primera descarga. A partir de ahí los cambios van y vienen
   en segundos: lo que anota Jarvis aparece en Obsidian, y lo que edites llega al vault
   del servidor.

En el portátil, si antes usabas el plugin Obsidian Git con `jarvis-vault`, pásate a
LiveSync en un vault nuevo y deja ese clon de git sin plugin: git queda solo para el
servidor.

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
