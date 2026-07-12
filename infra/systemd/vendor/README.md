# Scripts de terceros revisados

Copias congeladas de scripts de instalación remotos, revisadas manualmente antes de su ejecución (principio del prompt: "no ejecutes instalaciones mediante scripts remotos sin inspeccionar previamente su contenido").

| Script | Origen | Revisado | SHA-256 |
|---|---|---|---|
| `ollama-install.sh` | `https://ollama.com/install.sh` | 2026-07-12 | `25f64b810b947145095956533e1bdf56eacea2673c55a7e586be4515fc882c9f` |

## Notas de la revisión de `ollama-install.sh`

* Detecta arquitectura (amd64/arm64), descarga el binario oficial desde `ollama.com/download`, sin ejecutar código de terceros adicional.
* Crea un usuario de sistema `ollama` sin shell y un servicio systemd `ollama.service` que ejecuta `ollama serve` como ese usuario.
* Si detecta `nvidia-smi` funcionando (nuestro caso, driver ya instalado), no reinstala ni modifica el driver NVIDIA/CUDA; solo confirma la GPU y termina.
* Sin este `nvidia-smi` previo, intentaría instalar el driver CUDA de NVIDIA vía el repositorio oficial `developer.download.nvidia.com` — no aplica en este servidor porque el driver ya se instaló y verificó en la Fase 1 (auditoría) y Fase 3 (bootstrap).
* El API de Ollama queda en `127.0.0.1:11434` por defecto (sin flags de exposición pública).
* `scripts/install-ollama` añade sobre esto: comprobación de GPU antes de instalar, override de systemd para fijar `OLLAMA_MODELS` en `/srv/jarvis/models/ollama`, límite de un modelo cargado a la vez y pertenencia del usuario `ollama` al grupo `jarvis-svc`.

Si el contenido de `ollama.com/install.sh` cambia de forma relevante en el futuro, debe volver a descargarse, revisarse y actualizar esta copia y su hash antes de reutilizar el script.
