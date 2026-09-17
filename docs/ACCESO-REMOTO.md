# Acceso remoto: interfaz web de OpenClaw por Tailscale

Cómo abrir el panel de OpenClaw (chat, sesiones, dispositivos, aprobaciones) desde el
móvil o el portátil, estés donde estés, sin abrir puertos del servidor a internet.

Resultado final: `https://jarvis.<tu-tailnet>.ts.net` en el navegador de cualquier
dispositivo con Tailscale conectado, con HTTPS de verdad y sin pegar el token.

## Uso diario (una vez configurado)

1. En el móvil o el portátil, abre la app de Tailscale y conéctate.
2. Abre `https://jarvis.<tu-tailnet>.ts.net` (el nombre exacto sale en la app de
   Tailscale, en el dispositivo `jarvis`, o en <https://login.tailscale.com/admin/machines>).
3. Si no carga, en el servidor:

   ```bash
   cd jarvis-local
   docker compose ps tailscale openclaw          # ambos deben estar healthy
   docker compose logs openclaw | grep -i tailscale   # debe decir "Tailscale: serve"
   docker compose restart openclaw               # si dice "Tailscale: off"
   ```

No hay que repetir nada del paso a paso tras reiniciar el servidor o actualizar Jarvis.

## Cómo funciona

```
iPhone / portátil ──(Tailscale, cifrado)──► servidor
  https://jarvis.<tailnet>.ts.net:443         │
                                              ├─ contenedor tailscale (tailscaled)
                                              │    recibe el HTTPS con el certificado
                                              │    de *.ts.net y lo reenvía a 127.0.0.1
                                              │
                                              └─ contenedor openclaw (gateway)
                                                   escucha solo en 127.0.0.1:18789
```

* **Tailscale** crea una red privada (tailnet) entre tus dispositivos. Solo los que
  hayan iniciado sesión con tu cuenta la ven; desde internet no hay nada abierto.
* El servicio **`tailscale`** de `compose.yml` (perfil `tailscale`) une el servidor a esa
  red con el nombre `TAILSCALE_HOSTNAME` (por defecto `jarvis`). Corre en espacio de
  usuario: no necesita privilegios, dispositivo TUN ni instalar nada en el host.
* **OpenClaw** detecta al arrancar que tailscaled está conectado y activa
  `gateway.tailscale.mode: "serve"`: él mismo ejecuta `tailscale serve`, que publica el
  panel en el puerto 443 del nombre `*.ts.net` con un certificado de Let's Encrypt, y lo
  retira al pararse. Sin Tailscale, el modo queda en `off` y todo sigue igual.
* Quien entra por Serve se identifica con su cuenta de Tailscale (OpenClaw lo verifica
  con `tailscale whois`), así que no hace falta el token del gateway.
* El gateway escucha **solo en `127.0.0.1`** (`gateway.bind: "loopback"`). Por eso no
  sirve `http://<ip-tailscale>:18789`: la única entrada es la URL `https://…ts.net`.

## Requisitos

* Una cuenta de Tailscale (gratuita), por ejemplo iniciando sesión con GitHub o Google.
* La app de Tailscale en cada dispositivo desde el que quieras entrar (iOS, Android,
  macOS, Windows, Linux), con esa misma cuenta.
* Jarvis desplegado con docker compose (`docs/DOCKER.md`).

## Paso a paso

### 1. Tailscale en tus dispositivos

Instala la app de Tailscale en el móvil (o el portátil), inicia sesión y deja la VPN
conectada. Con eso ya existe tu tailnet.

### 2. Activar MagicDNS y certificados HTTPS

En <https://login.tailscale.com/admin/dns>:

* **MagicDNS** → activado (da nombres como `jarvis.tail1234.ts.net`).
* **HTTPS Certificates** → activado (permite que el servidor pida su certificado).

Tu nombre de tailnet (`tail1234.ts.net`) aparece en esa misma página.

### 3. Activar el perfil en `.env`

```bash
# añade tailscale a los perfiles que ya tengas, separados por comas
COMPOSE_PROFILES=vault,tailscale
# opcional: nombre del servidor dentro del tailnet
TAILSCALE_HOSTNAME=jarvis
```

### 4. Arrancar

```bash
docker compose up -d
```

La primera vez aparece un aviso `optional dependency "tailscale" failed to start`: es
normal, el servidor aún no ha iniciado sesión y OpenClaw arranca sin Tailscale.

### 5. Unir el servidor al tailnet (solo la primera vez)

Elige una de las dos formas. El resultado se guarda en el volumen `tailscale_state` y
sobrevive a reinicios y actualizaciones.

**a) Con tu cuenta (sin crear claves).** Busca el enlace en los logs:

```bash
docker compose logs tailscale | grep login.tailscale.com
```

Ábrelo en cualquier navegador e inicia sesión con la misma cuenta que en el móvil. El
enlace no caduca mientras el contenedor siga en marcha. Comprueba que ya está dentro
(deben salir el servidor y tus dispositivos):

```bash
docker compose exec tailscale tailscale --socket /var/run/tailscale/tailscaled.sock status
```

Y reinicia OpenClaw para que publique el panel:

```bash
docker compose restart openclaw
```

**b) Con una clave (sin interacción, útil para automatizar).** En
<https://login.tailscale.com/admin/settings/keys> genera una *auth key*, ponla en `.env`
**antes** del paso 4 y no hace falta reiniciar nada:

```bash
TS_AUTHKEY=tskey-auth-xxxxxxxx
```

### 6. Comprobar

```bash
docker compose logs openclaw | grep -i tailscale
# == Gateway OpenClaw en 127.0.0.1:18789 (Tailscale: serve) ==
# [tailscale] serve enabled: https://jarvis.tail1234.ts.net/
docker compose logs tailscale | grep cert
# cert("jarvis.tail1234.ts.net"): got cert
```

El certificado tarda unos 30 segundos la primera vez.

### 7. Abrir el panel

Con Tailscale conectado en el móvil, abre en el navegador:

```
https://jarvis.<tu-tailnet>.ts.net
```

Sin puerto: es el 443 de HTTPS. Puedes añadirlo a la pantalla de inicio (es una PWA).

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| La página no carga en el móvil | La app de Tailscale está desconectada, o usas otra cuenta. Comprueba que el servidor aparece en la lista de dispositivos de la app. |
| `http://100.x.x.x:18789` o `jarvis:18789` no responde | Esperado: el gateway solo escucha en loopback. Usa `https://jarvis.<tailnet>.ts.net`. |
| `tailscale` en `unhealthy` en el primer arranque | Pasaron más de ~5 minutos sin abrir el enlace de inicio de sesión. El enlace sigue valiendo: inicia sesión y ejecuta `docker compose up -d` y `docker compose restart openclaw`. |
| Logs de OpenClaw con `Tailscale: off` | OpenClaw arrancó antes de que el servidor estuviera en el tailnet: `docker compose restart openclaw`. |
| Error de certificado o `tls-cert-pending` | HTTPS Certificates desactivado en el panel de DNS, o aún se está emitiendo: espera y recarga. |
| `disconnected (1008): pairing required` | Navegador sin identidad de dispositivo (p. ej. modo privado). Aprueba desde el servidor: `docker compose exec openclaw openclaw devices list` y `… devices approve <requestId>`. |
| `tailscale serve status` dice `No serve config` | Normal: OpenClaw usa un Serve en primer plano; mira `tailscale serve status --json` (sección `Foreground`). |
| El servidor sale dos veces en el panel de Tailscale | Se borró el volumen `tailscale_state` y se volvió a unir. Borra la entrada antigua en <https://login.tailscale.com/admin/machines>. |
| `Access denied: checkprefs access denied` | `tailscale` y `openclaw` corren con distinto UID. Ambos usan `JARVIS_UID`/`JARVIS_GID`; no los cambies por separado. |

## Seguridad

* No se expone ningún puerto a internet: el tráfico entra por la conexión cifrada de
  Tailscale y solo desde dispositivos de tu tailnet.
* Entrar por Serve sin token confía en tu identidad de Tailscale y en que el servidor es
  de confianza. Para exigir también el token, añade `"allowTailscale": false` dentro de
  `gateway.auth` en `integrations/openclaw/config/openclaw.template.json`.
* Si compartes el tailnet con otras personas, limita quién llega al servidor con las
  ACL de Tailscale (<https://login.tailscale.com/admin/acls>).
* No uses `funnel` (publicaría el panel en internet).

## Desactivar o cambiar

* **Quitar el acceso**: elimina `tailscale` de `COMPOSE_PROFILES` y
  `docker compose up -d --remove-orphans`; OpenClaw vuelve a `Tailscale: off`. Para
  sacar el servidor del tailnet, bórralo también en el panel de máquinas.
* **Cambiar el nombre**: cambia `TAILSCALE_HOSTNAME`, `docker compose up -d tailscale` y
  `docker compose restart openclaw`.
* **Alternativa sin Tailscale**: túnel SSH, ver `docs/DOCKER.md`.

## ¿Y Obsidian?

El vault no tiene interfaz web ni pasa por Tailscale: se abre con la app Obsidian en el
portátil o el móvil, sincronizada con el repo git privado del perfil `vault`
(`docs/MEMORY.md`).

## Archivos implicados

| Archivo | Qué hace |
|---|---|
| `compose.yml` (servicio `tailscale`, volúmenes `tailscale_state` y `tailscale_socket`) | Contenedor de tailscaled y socket compartido con `openclaw` |
| `infra/docker/tailscale-entrypoint.sh` | Arranca tailscaled y `tailscale up` (con `TS_AUTHKEY` o esperando al enlace) |
| `infra/docker/jarvis-init` | Da los volúmenes de Tailscale al UID de `openclaw` |
| `integrations/openclaw/Dockerfile` | Copia la CLI `tailscale` en la imagen de OpenClaw |
| `integrations/openclaw/docker-entrypoint.sh` | Elige `serve` u `off` según haya tailscaled conectado |
| `integrations/openclaw/config/openclaw.template.json` | `gateway.bind: "loopback"` y `gateway.tailscale.mode` |
