# Contribuir a Jarvis Local

Gracias por el interés en el proyecto. Antes de nada, ten en cuenta el principio
que gobierna toda decisión técnica aquí: **local-first**. Ningún documento,
embedding, prompt o respuesta debe salir del servidor hacia una API de modelos
en la nube. Cualquier contribución que rompa esa garantía se rechazará,
independientemente de su calidad técnica.

## Antes de abrir una issue o PR

* Revisa `docs/ARCHITECTURE.md` para entender el diseño y las restricciones de
  hardware reales del proyecto.
* Revisa `docs/ROADMAP.md` para ver en qué fase está el proyecto y si tu
  propuesta ya está prevista (o descartada) ahí.
* Para cambios de seguridad (autenticación, exposición de red, ejecución de
  comandos, allowlists de Telegram), lee primero `docs/SECURITY.md`.

## Entorno de desarrollo

```bash
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```

Las tres comprobaciones (`pytest`, `ruff`, `pyright`) deben pasar antes de abrir
un PR. `ruff` aplica `E, F, I, UP, B, SIM`; `pyright` corre en modo `basic` sobre
`apps`, `packages` y `tests`.

## Convenciones

* Python 3.12, gestionado con `uv` (no uses `pip`/`venv` a mano).
* Los mensajes de commit siguen **[Conventional Commits](https://www.conventionalcommits.org/)**:
  `tipo(ámbito): descripción` en presente, ámbito opcional pero recomendado
  cuando el cambio toca un área concreta (`feat(inference): ...`,
  `fix(rag): ...`). Tipos habituales: `feat`, `fix`, `docs`, `refactor`,
  `test`, `chore`, `perf`, `ci`. Un cambio incompatible añade un footer
  `BREAKING CHANGE: <explicación>`. Coherente con el historial existente
  (`git log --oneline`); esta es la convención definitiva del proyecto, no
  solo una costumbre.
* No añadas dependencias que llamen a APIs externas de inferencia (OpenAI,
  Anthropic, etc.) en el camino de producción. Ollama y AirLLM son los únicos
  proveedores de inferencia soportados.
* Nunca versiones secretos: `.env` está en `.gitignore`; usa `.env.example`
  como plantilla y documenta cualquier variable nueva ahí.
* Cualquier acción con efectos externos (enviar un correo, crear un evento de
  calendario, ejecutar un comando no listado en la allowlist) debe pasar por
  confirmación explícita del propietario, siguiendo el patrón ya usado en
  `packages/security` — no autonomía silenciosa.
* Los tests de evaluación RAG deben seguir demostrando **abstención** cuando no
  hay evidencia suficiente en el corpus: no relajes ese comportamiento para que
  un test pase.

## Estructura del repo

Ver la sección "Estructura" del `README.md` para la organización de
`apps/`, `packages/`, `services/`, `integrations/`, `infra/` y `scripts/`.

## Licencia

Al contribuir aceptas que tu aportación se publique bajo la licencia MIT del
proyecto (ver `LICENSE`).
