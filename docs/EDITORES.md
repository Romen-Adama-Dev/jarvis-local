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
| [PhotoCraft](#photocraft-imagen) | Edición de imagen (como Photoshop) | `photocraft` | `https://<nombre>.ts.net:8448` | `http://127.0.0.1:8099` |

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

### Jarvis y los PDF (`jarvis-pdf`)

Por Telegram, Jarvis hace lo mismo con los PDF que le mandas, sin abrir el navegador: le
envías los adjuntos y le pides «únelos», «sácame las páginas 3 a 5», «quita la 4», «gira
la primera», «ponle la contraseña …», «¿qué campos tiene este formulario?» y «rellénalo
con …», «ponle BORRADOR» o «hazlo más ligero». Devuelve un PDF nuevo (o varios, o un ZIP
si al dividir salen más de 10) y el original no cambia. No depende del perfil
`printcraft`: funciona siempre.

| Herramienta | Qué hace |
|---|---|
| `jarvis_pdf_combine(files)` | Une varios PDF en el orden dado |
| `jarvis_pdf_split(file, every)` | Divide cada `every` páginas |
| `jarvis_pdf_extract_pages(file, pages)` | PDF nuevo con esas páginas (`"3-5, 8"`) |
| `jarvis_pdf_edit_pages(file, delete, rotate, degrees)` | Borra y gira páginas |
| `jarvis_pdf_protect(file, password)` | Contraseña para abrirlo (AES-256) |
| `jarvis_pdf_form(file, values)` | Lista los campos o, con `values`, rellena el formulario |
| `jarvis_pdf_watermark(file, text)` | Marca de agua de texto en diagonal |
| `jarvis_pdf_compress(file)` | Copia más ligera (imágenes a 150 ppp) |

Cómo está hecho:

* `printcraft-cli` va en la imagen de OpenClaw (`integrations/openclaw/Dockerfile`, versión
  y SHA-256 fijados para x86_64 y ARM64).
* `integrations/openclaw/skills/jarvis-pdf` es un servidor MCP propio con 8 herramientas
  (unos 800 tokens de esquemas). El MCP que trae PrintCraft (`printcraft-cli mcp`) tiene
  123 herramientas y unos 27 000 tokens, demasiado para Gemma con 64k de contexto: el
  mismo problema que con los MCP de OpenProject de la comunidad (`docs/OPENPROJECT.md`).
* `packages/pdf` copia cada PDF a un directorio temporal, ejecuta un guion de
  `printcraft-cli run --script` encerrado en él (`--root`) y deja el resultado en el
  outbox. Solo lee adjuntos del chat, `~/jarvis-inbox`, los documentos del RAG y el
  outbox, y hasta 100 MiB por PDF.
* Los tests de `tests/unit/test_pdf.py` que usan el CLI de verdad corren en CI (que lo
  descarga) y se saltan si no está instalado.

Al actualizar PrintCraft, cambia la versión y los SHA-256 en el Dockerfile de OpenClaw y
en `.github/workflows/ci.yml`.

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

## PhotoCraft (imagen)

[storytold/photocraft](https://github.com/storytold/photocraft), versión 0.2.0.

* **Capas** con grupos, máscaras de píxel y vectoriales, capas de ajuste (Curvas, Niveles,
  Tono/saturación...), estilos de capa y objetos inteligentes con filtros editables.
* **Selección**: marcos, lazos, varita mágica, selección rápida y de objeto, y Seleccionar
  y aplicar máscara; todo en local.
* **Texto**, formas y pluma; filtros con vista previa; transformación libre e historial.
* **Ficheros**: PSD y PSB reales, PNG, JPEG, TIFF, WebP, GIF, AVIF, OpenEXR y más, a 8, 16
  y 32 bits, en RGB, escala de grises, CMYK y Lab.
