// Botones de aprobación de correos: los manda la API de Jarvis con el borrador
// (apps/api/jarvis_api/routers/email.py) y los atiende este plugin. El callback lleva el
// token de confirmación, que nunca pasa por el modelo. Sin efectos: `node --test`.

export const NAMESPACE = "correo";

const ACTIONS = new Map([
  ["enviar", { path: "confirm", done: (r) => `✅ Enviado a ${(r.to ?? []).join(", ")}.` }],
  ["descartar", { path: "cancel", done: () => "🗑️ Borrador descartado." }],
]);

/** `enviar:<token>` / `descartar:<token>` → { action, path, token }; null si no encaja. */
export function parsePayload(payload) {
  const match = /^(enviar|descartar):([A-Za-z0-9_-]{16,64})$/.exec(String(payload ?? "").trim());
  if (!match) return null;
  return { action: match[1], path: ACTIONS.get(match[1]).path, token: match[2] };
}

/** Texto que sustituye al del borrador cuando la API responde bien. */
export function doneText(action, result) {
  return ACTIONS.get(action).done(result ?? {});
}

/** Mensaje de error de la API (`{"detail": ...}` o `{"error": {"message": ...}}`). */
export function errorText(status, body) {
  const detail = body?.error?.message ?? body?.detail ?? body?.message;
  return `⚠️ No se pudo (${status}): ${typeof detail === "string" ? detail : "error de la API"}`;
}
