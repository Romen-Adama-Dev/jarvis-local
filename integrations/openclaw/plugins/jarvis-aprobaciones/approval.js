// Botones de aprobación: los manda la API de Jarvis (correos: apps/api/jarvis_api/routers/
// email.py; altas en OpenProject: routers/pm.py) y los atiende este plugin. El callback
// lleva el token de confirmación, que nunca pasa por el modelo. Sin efectos: `node --test`.

export const NAMESPACE = "correo";
export const PEOPLE_NAMESPACE = "personas";

const names = (result) => (result.lines ?? []).join("\n");

// Espacio del callback → ruta de la API y acciones (acción → ruta final y texto al acabar).
const APPROVALS = new Map([
  [
    NAMESPACE,
    {
      base: "/v1/email/draft",
      actions: new Map([
        ["enviar", { path: "confirm", done: (r) => `✅ Enviado a ${(r.to ?? []).join(", ")}.` }],
        ["descartar", { path: "cancel", done: () => "🗑️ Borrador descartado." }],
      ]),
    },
  ],
  [
    PEOPLE_NAMESPACE,
    {
      base: "/v1/pm/people",
      actions: new Map([
        ["alta", { path: "confirm", done: (r) => `✅ Hecho en OpenProject:\n${names(r)}`.trim() }],
        ["descartar", { path: "cancel", done: () => "🗑️ Altas descartadas." }],
      ]),
    },
  ],
]);

export const NAMESPACES = [...APPROVALS.keys()];

/** `enviar:<token>` en el espacio `correo` → { action, path, token, url }; null si no encaja. */
export function parsePayload(payload, namespace = NAMESPACE) {
  const approval = APPROVALS.get(namespace);
  const match = /^([a-z]+):([A-Za-z0-9_-]{16,64})$/.exec(String(payload ?? "").trim());
  if (!approval || !match || !approval.actions.has(match[1])) return null;
  const { path } = approval.actions.get(match[1]);
  return { action: match[1], path, token: match[2], url: `${approval.base}/${match[2]}/${path}` };
}

/** Texto que se añade al aviso cuando la API responde bien. */
export function doneText(action, result, namespace = NAMESPACE) {
  return APPROVALS.get(namespace).actions.get(action).done(result ?? {});
}

/** Mensaje de error de la API (`{"detail": ...}` o `{"error": {"message": ...}}`). */
export function errorText(status, body) {
  const detail = body?.error?.message ?? body?.detail ?? body?.message;
  return `⚠️ No se pudo (${status}): ${typeof detail === "string" ? detail : "error de la API"}`;
}
