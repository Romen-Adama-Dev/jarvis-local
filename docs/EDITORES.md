# Editores en el navegador

Las apps de [ArtCraft](https://github.com/storytold) son reimplementaciones libres de
programas de Adobe escritas en Rust (MIT o Apache-2.0), y también se compilan a
WebAssembly. Jarvis sirve esa versión web desde el servidor y tú la abres por Tailscale en
el PC, el portátil o la tableta. La aplicación entera corre en el navegador: lo que abres
no se sube al servidor y, al guardar, se descarga en tu dispositivo.

| App | Para qué | Perfil | Por Tailscale | En el servidor |
|---|---|---|---|---|
| [PrintCraft](#printcraft-pdf) | PDF (como Acrobat) | `printcraft` | `https://<nombre>.ts.net:8446` | `http://127.0.0.1:8097` |
| [VectorCraft](#vectorcraft-ilustración-vectorial) | Ilustración vectorial (como Illustrator) | `vectorcraft` | `https://<nombre>.ts.net:8447` | `http://127.0.0.1:8098` |

## Cómo funciona

```
navegador (PC, tableta) ──Tailscale──► https://jarvis.<tailnet>.ts.net:<puerto> ──► <app>
                                                                                  (nginx)
          ◄──── index.html + <app>-web.wasm: la app se ejecuta en el navegador ─────┘
```

* Cada app es un servicio de compose con su propio perfil: un nginx sin privilegios que
  solo entrega ficheros estáticos. Su imagen (`jarvis-<app>`) se construye en el primer
  `docker compose up` con la web de la release de GitHub (`<app>-web-<versión>.zip`), cuyo
  SHA-256 se comprueba al descargarla. Todas usan la misma imagen genérica
  (`infra/docker/craft-web`, con `APP`, `VERSION` y `SHA256`).
* El `.wasm` pesa entre 25 y 50 MB según la app. Se sirve precomprimido (entre 10 y
  20 MB) y el navegador lo guarda en caché tras la primera visita.
* **Sin cuenta, sin telemetría y sin datos en el servidor**: el contenedor es de solo
  lectura, sin capacidades ni volúmenes. No hay nada que copiar en `scripts/backup`.

## Activarlo

En `.env`, añade el perfil de la app a los que ya tengas:

```bash
COMPOSE_PROFILES=vault,tailscale,pm,printcraft
docker compose up -d
docker compose restart openclaw   # si el panel de OpenClaw deja de abrir (ver abajo)
```

Ábrela en la dirección de la tabla, o pregunta a Jarvis *«¿qué servicios hay?»*. Sin
Tailscale, túnel SSH al puerto del servidor. Los puertos se cambian con
`<APP>_PORT` y `<APP>_HTTPS_PORT` (por ejemplo `PRINTCRAFT_PORT`).

`docker compose up -d` vuelve a crear el contenedor `tailscale` para publicar el puerto
nuevo, y el panel de OpenClaw pierde su publicación en el 443 (es un Serve en primer
plano). `docker compose restart openclaw` lo recupera.

Si la app sale en blanco, añade `?webgl` o `?cpu` al final de la dirección (cambian el modo
de dibujo). Están pensadas para ratón y teclado, y la interfaz está en inglés.

## Quién puede abrirlas

No piden usuario: las abre cualquier dispositivo de tu tailnet. Como no guardan nada, lo
único que obtiene es la aplicación vacía. Si compartes el servidor con otras personas,
limita los puertos con las ACL de Tailscale (`docs/ACCESO-REMOTO.md`).

## Actualizar

En el servicio de la app en `compose.yml`, cambia `VERSION`, `SHA256` (de
`SHA256SUMS.txt` en la release) y la etiqueta de `image`. Después, por ejemplo:

```bash
docker compose up -d --build printcraft
```

Son proyectos muy jóvenes: los repositorios son de finales de septiembre de 2026 y salen
versiones casi a diario. Conserva el original de cualquier documento importante.

## PrintCraft (PDF)

[storytold/printcraft](https://github.com/storytold/printcraft), versión 0.2.1.

* **Leer**: búsqueda, marcadores, miniaturas, capas, modo lectura y tema oscuro.
* **Organizar páginas**: rotar, borrar, mover, insertar, extraer; **unir** varios PDF
  (cada uno con su marcador) y **dividir** cada *n* páginas.
* **Comentarios** (resaltado, notas, formas, tinta), **formularios** (rellenar y crear),
  **contraseñas** (hasta AES-256), **tachado** de información sensible y firmas básicas.
* **Abrir por URL**: `https://…:8446/?file=<url>` carga un PDF del mismo origen o de un
  servidor con CORS.

Límites: editar el texto que ya tiene un PDF todavía no es fiable, el OCR solo reconoce
alfabeto latino y no importa ni exporta Office.

**Jarvis aún no lo usa.** `printcraft-cli` (en las releases para Linux) trae un servidor
MCP (`printcraft-cli mcp --root <carpeta>`) con 123 herramientas: unir, dividir, extraer
texto, rellenar formularios, proteger, marcas de agua, OCR... Funciona en el servidor,
pero sus esquemas ocupan unos 27 000 tokens, demasiados para Gemma con 64k de contexto
(el mismo problema que con los MCP de OpenProject de la comunidad, `docs/OPENPROJECT.md`).
Para integrarlo hace falta un servidor MCP propio con pocas herramientas que llame al CLI.

## VectorCraft (ilustración vectorial)

[storytold/vectorcraft](https://github.com/storytold/vectorcraft), versión 0.3.1.

* **Dibujo**: pluma, formas, Buscatrazos y Generador de formas, pintura, degradados,
  apariencia y transparencia.
* **Texto** con estilos y enlazado entre cuadros.
* **Ficheros**: SVG, PDF y `.ai` compatible con PDF (también PDF/X), EPS, DXF, EMF/WMF,
  formatos de imagen y PSD; imprimir y empaquetar.

Límites (según el propio proyecto, tiene entre el 69 y el 75 % de las funciones de
Illustrator): sin 3D ni materiales, sin la galería de efectos de imagen y sin variables ni
scripts.
