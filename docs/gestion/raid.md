# Registro RAID: paso a producción

Riesgos, supuestos, incidencias y dependencias para llevar Jarvis Local del entorno del
TFM a uso diario en una organización. Revisión: noviembre de 2026. Cada entrada que se
convierta en trabajo se abre como tarea o como riesgo en OpenProject (tipo *Riesgo*, que
el aprovisionamiento crea) y se enlaza desde aquí.

## Responsables

En un despliegue real los roles se asignan en el arranque del proyecto. Hoy los cubre el
propietario del repositorio.

| Rol | Qué decide o hace |
|---|---|
| PM | Alcance, plan, comunicación con usuarios, aceptación de riesgos |
| Responsable técnico | Servidor, GPU, despliegue, actualizaciones de imágenes y modelos |
| Seguridad | Accesos, secretos, revisión de auditorías, respuesta a incidentes |
| Usuario clave | Valida respuestas y flujos en la UAT y en el piloto |

Escalas: probabilidad e impacto en alta, media o baja.

## Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación | Responsable |
|---|---|---|---|---|---|
| R1 | El modelo responde con algo que la documentación no dice | Media | Alto | Abstención con marca `insufficient_evidence`; `scripts/benchmark-jarvis` tras cada cambio de modelo o de prompt (hoy 4/4 abstenciones y 14/18 respuestas correctas con fuente); revisión de los fallos uno a uno en [BENCHMARKS.md](../BENCHMARKS.md) | Responsable técnico |
| R2 | La GPU de producción tiene menos VRAM que la de las pruebas | Media | Medio | `scripts/select-models` elige modelo por franjas de VRAM ([MODELS.md](../MODELS.md)); `compose.cpu.yml` como último recurso, con más latencia | Responsable técnico |
| R3 | Un documento o un correo intenta inyectar instrucciones al agente | Media | Alto | Correo delimitado como contenido no confiable; `exec` con lista blanca de solo lectura; toda acción externa pide confirmación con botón fuera del modelo ([SECURITY.md](../SECURITY.md)) | Seguridad |
| R4 | Un servicio interno queda expuesto a Internet | Baja | Alto | Sin `ports:` publicados fuera de loopback; acceso remoto solo por Tailscale; comprobación con `ss -tlnp` (criterio 3 de [ACCEPTANCE.md](../ACCEPTANCE.md)) | Seguridad |
| R5 | Pérdida de datos (bases, vectores, vault) | Baja | Alto | Perfil `backup` diario, `scripts/test-restore` en un proyecto aislado y alerta `CopiaAtrasada` ([BACKUP.md](../BACKUP.md)) | Responsable técnico |
| R6 | OpenClaw, proyecto de terceros, cambia de forma incompatible | Media | Medio | Versión fijada en la imagen; las capacidades viven en servidores MCP propios, así que cambiar de cliente no obliga a reescribirlas ([ROADMAP.md](../ROADMAP.md), 3.1) | Responsable técnico |
| R7 | Credenciales usadas durante el TFM siguen activas en producción | Media | Alto | Rotar el token del bot de Telegram y la contraseña de aplicación del correo antes del piloto; secretos solo en `.env` y `/run/jarvis` | Seguridad |
| R8 | La latencia del RAG (mediana 14,2 s, p95 19,7 s) no es aceptable para los usuarios | Media | Medio | Medirla en la UAT con tareas reales; modelo rápido para consultas normales; avisar en el chat cuando una tarea va a la cola | PM |
| R9 | Varias personas necesitan acceso con permisos distintos | Alta | Medio | Hoy hay un solo usuario autorizado. Multiusuario con permisos por empresa y proyecto entra como requisito del piloto si hay más de un usuario ([ROADMAP.md](../ROADMAP.md), 4.1) | PM |
| R10 | Se indexa documentación con derechos de autor o datos personales | Media | Medio | Política de qué se sube al RAG acordada con la organización; los benchmarks no guardan el texto de las respuestas | PM |

## Supuestos

| ID | Supuesto | Cómo se valida | Responsable |
|---|---|---|---|
| A1 | Hay un servidor con GPU NVIDIA de 8 GB o más y NVIDIA Container Toolkit | `scripts/check-integrations` en el servidor de destino | Responsable técnico |
| A2 | Los usuarios ya usan Telegram o aceptan usarlo | Pregunta en el arranque; sin Telegram, el alcance cambia (Teams quedó fuera el 01-10-2026) | PM |
| A3 | OpenProject sirve como herramienta de gestión de la organización | Demo con un proyecto real en el piloto | PM |
| A4 | La organización tiene correo con IMAP/SMTP o Microsoft 365 | Configuración con `scripts/configure-mail` | Responsable técnico |
| A5 | La documentación está mayoritariamente en español, con terminología PMBOK | Revisión del corpus antes de indexar; el glosario cubre español e inglés | Usuario clave |

## Incidencias abiertas

| ID | Incidencia | Efecto | Acción | Responsable |
|---|---|---|---|---|
| I1 | La UAT con usuarios y la medición del ahorro de tiempo no se han hecho | Sin dato real de ahorro para justificar el paso a producción | Ejecutar el protocolo de [UAT.md](../UAT.md) con 5 participantes | PM |
| I2 | 4 de 18 preguntas del benchmark de RAG fallan | Riesgo R1 sigue abierto | Revisar recuperación y chunking de esos casos; repetir el benchmark | Responsable técnico |
| I3 | Las actas no distinguen quién habla | El usuario tiene que asignar intervenciones a mano | Diarización local (pendiente en [ROADMAP.md](../ROADMAP.md), 4.1) | Responsable técnico |
| I4 | El calendario no mueve ni cancela reuniones ni crea recurrentes | Parte de la agenda se sigue llevando en OpenProject a mano | Ampliar `jarvis-calendar` | Responsable técnico |

## Dependencias

| ID | Dependencia | Tipo | Si falla | Responsable |
|---|---|---|---|---|
| D1 | Driver NVIDIA y NVIDIA Container Toolkit | Infraestructura | Ollama cae a CPU o no arranca | Responsable técnico |
| D2 | Imágenes fijadas (Ollama 0.34.0, Qdrant v1.12.5, PostgreSQL 17.2, OpenProject 17.8.0) | Software | Una actualización sin probar rompe la pila; se actualizan por PR | Responsable técnico |
| D3 | API de bots de Telegram | Servicio externo | Sin canal de chat; los paneles siguen accesibles por Tailscale | PM |
| D4 | Proveedor de correo | Servicio externo | No salen invitaciones ni correos; el resto funciona | Responsable técnico |
| D5 | Servicio de coordinación de Tailscale | Servicio externo | Sin acceso remoto a los paneles; Telegram sigue funcionando | Seguridad |
| D6 | Descarga de modelos en la primera instalación | Servicio externo | Sin modelos no hay inferencia; después funciona sin Internet (criterio 27) | Responsable técnico |

## English summary

RAID log for the production rollout. The main risks are answers not backed by the
documents (mitigated with abstention and a repeatable benchmark), prompt injection through
documents or email (approval buttons outside the model, read-only command allowlist) and
single-user access. Open issues: user acceptance testing, 4 failing RAG benchmark
questions, speaker diarization and calendar edits. Each entry has an owner role and a
mitigation.
