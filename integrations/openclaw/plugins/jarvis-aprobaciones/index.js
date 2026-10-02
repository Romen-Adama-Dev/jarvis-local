// Plugin de OpenClaw `jarvis-aprobaciones`: atiende los botones que la API adjunta a lo que
// necesita la aprobación del propietario: los borradores de correo (Enviar/Descartar,
// docs/EMAIL.md) y las altas de personas en OpenProject (Dar de alta/Descartar). Quien
// confirma es el botón, no el modelo: el agente no ve el token ni puede confirmar.
import { readFile } from "node:fs/promises";

import { NAMESPACES, doneText, errorText, parsePayload } from "./approval.js";

const API_URL = (process.env.JARVIS_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
// El gateway arranca sin secretos en el entorno: el token de la API se lee del volumen de init.
const TOKEN_FILE = `${process.env.JARVIS_RUNTIME_DIR ?? "/run/jarvis"}/jarvis_api_internal_token`;

async function callApi(url, senderId) {
  const apiToken = (await readFile(TOKEN_FILE, "utf8")).trim();
  const response = await fetch(`${API_URL}${url}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ telegram_user_id: Number(senderId) }),
    signal: AbortSignal.timeout(120_000),
  });
  const body = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, body };
}

export default {
  id: "jarvis-aprobaciones",
  name: "Jarvis: aprobaciones",
  description: "Botones de aprobación de correos y de altas en OpenProject",
  register(api) {
    for (const namespace of NAMESPACES) {
      api.registerInteractiveHandler({
        channel: "telegram",
        namespace,
        handler: (ctx) => handle(ctx, namespace),
      });
    }
    api.logger?.info?.(`[jarvis-aprobaciones] botones registrados: ${NAMESPACES.join(", ")}`);
  },
};

async function handle(ctx, namespace) {
  // Solo el dueño y por privado; la API comprueba además que la petición es suya.
  if (!ctx.auth?.isAuthorizedSender || ctx.isGroup || !ctx.senderId) {
    return { handled: true };
  }
  const parsed = parsePayload(ctx.callback?.payload, namespace);
  if (!parsed) {
    await ctx.respond.clearButtons();
    return { handled: true };
  }
  const original = ctx.callback?.messageText ?? "";
  try {
    const result = await callApi(parsed.url, ctx.senderId);
    const text = result.ok
      ? doneText(parsed.action, result.body, namespace)
      : errorText(result.status, result.body);
    await ctx.respond.editMessage({ text: `${original}\n\n${text}`.trim() });
  } catch (error) {
    await ctx.respond.reply({ text: `⚠️ No se pudo contactar con la API: ${error.message}` });
  }
  return { handled: true };
}
