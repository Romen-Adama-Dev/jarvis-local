# Monitorización

Perfil `monitoring` de `compose.yml`: métricas de Jarvis, de la GPU y del servidor en
Prometheus, un panel en Grafana y alertas por Telegram.

```bash
# COMPOSE_PROFILES=...,monitoring en .env, o de forma puntual:
docker compose --profile monitoring up -d
```

| Servicio | Puerto (solo 127.0.0.1) | Qué hace |
|---|---|---|
| `prometheus` | 9090 | Recoge las métricas cada 30 s y evalúa las alertas (`infra/monitoring/alerts.yml`); guarda 30 días (`PROMETHEUS_RETENTION`) |
| `alertmanager` | 9093 | Envía las alertas por Telegram |
| `grafana` | 3000 (`GRAFANA_PORT`) | Panel "Jarvis" (`infra/monitoring/grafana/dashboards/jarvis.json`) |
| `blackbox-exporter` | 9115 | Sondas HTTP y TCP contra cada servicio |
| `node-exporter` | 9100 | CPU, memoria y disco del servidor, y la hora de la última copia de seguridad (la escribe el servicio `backup` en el volumen `backup_metrics`) |
| `dcgm-exporter` | 9400 | GPU NVIDIA: uso, VRAM, temperatura, consumo, errores Xid (sin GPU, `compose.cpu.yml` lo desactiva y pone `MONITOR_GPU=false` a Prometheus para que no lo dé por caído) |

Todos usan `network_mode: host` y escuchan solo en `127.0.0.1`, como `ollama`, `api` y
`openclaw`: así Prometheus llega a esos servicios sin abrirlos a la red. Nada se publica
por Tailscale.

## Qué se mide

* **Disponibilidad** de cada servicio con sondas: Ollama (`/api/version`), la API
  (`/ready`, que falla si falta PostgreSQL, Redis, Qdrant u Ollama), OpenClaw, SearXNG,
  y por TCP PostgreSQL, Redis y Qdrant. CouchDB solo con el perfil `livesync` y OpenProject
  solo con `pm`: `prometheus-entrypoint.sh` genera los objetivos a partir de
  `COMPOSE_PROFILES`, para no dar por caído lo que no está desplegado.
* **API de Jarvis** (`/metrics`): `jarvis_http_requests_total` y
  `jarvis_http_request_duration_seconds` por método y plantilla de ruta
  (`/documents/{document_id}`, no cada id), además de las del proceso.
* **Qdrant**: colecciones y número de vectores.
* **GPU** (DCGM) y **servidor** (node-exporter).

Los servicios sin HTTP (`worker`, `knowledge`, `vault-sync`, `livesync-bridge`,
`openproject-wiki-sync`) no tienen sonda: su estado lo comprueba
`scripts/check-integrations`.

## Alertas

| Alerta | Cuándo |
|---|---|
| `ServicioCaido` | Una sonda falla durante 3 min |
| `MetricasSinDatos` | Prometheus no puede leer un exportador o la API durante 5 min |
| `ApiErrores5xx` | Más del 5 % de las peticiones a la API acaban en 5xx durante 10 min |
| `CopiaAtrasada` | La última copia de seguridad correcta tiene más de 26 h (perfil `backup`; `jarvis_backup_last_success_timestamp_seconds`) |
| `DiscoCasiLleno` | Menos del 10 % libre en `/` |
| `MemoriaBaja` | Menos del 5 % de RAM disponible durante 10 min |
| `GpuTemperaturaAlta` | GPU por encima de 85 °C durante 5 min |
| `GpuErroresXid` | El driver de NVIDIA informa de un error Xid |

Llegan por Telegram con el mismo bot de Jarvis (`TELEGRAM_BOT_TOKEN`) al primer ID de
`TELEGRAM_AUTHORIZED_USER_IDS`, y otro mensaje cuando se resuelven. Se agrupan por alerta y
servicio y se repiten cada 12 h mientras sigan activas. Sin Telegram configurado solo se ven
en Prometheus (`/alerts`), Alertmanager y el panel de Grafana. El bot solo envía: no
interfiere con OpenClaw, que es quien lee sus mensajes.

Para comprobar el canal sin romper nada:

```bash
curl -XPOST 127.0.0.1:9093/api/v2/alerts -H 'Content-Type: application/json' -d \
  '[{"labels":{"alertname":"Prueba"},"annotations":{"summary":"Prueba del canal de alertas"}}]'
```

## Grafana

Usuario `admin`; la contraseña la genera `init` la primera vez (o `GRAFANA_ADMIN_PASSWORD`
en `.env`, que solo cuenta antes del primer arranque de Grafana):

```bash
docker compose exec openclaw cat /run/jarvis/grafana_admin_password
```

Desde otro equipo, con un túnel SSH: `ssh -L 3000:127.0.0.1:3000 <servidor>` y
`http://127.0.0.1:3000`. El panel "Jarvis" es la página de inicio y viene del repo: los
cambios hechos en la interfaz no se guardan (edítalo en
`infra/monitoring/grafana/dashboards/jarvis.json`).
