// Plugin de OpenClaw `jarvis-aprobaciones`: atiende los botones Enviar/Descartar que la API
// adjunta a cada borrador de correo. Quien envía es el botón, no el modelo: el agente no
// ve el token ni tiene herramienta para confirmar (docs/EMAIL.md).
import { readFile } from "node:fs/promises";

import { NAMESPACE, doneText, errorText, parsePayload } from "./approval.js";

const API_URL = (process.env.JARVIS_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
// El gateway arranca sin secretos en el entorno: el token de la API se lee del volumen de init.
const TOKEN_FILE = `${process.env.JARVIS_RUNTIME_DIR ?? "/run/jarvis"}/jarvis_api_internal_token`;

async function callApi(path, token, senderId) {
  const apiToken = (await readFile(TOKEN_FILE, "utf8")).trim();
  const response = await fetch(`${API_URL}/v1/email/draft/${token}/${path}`, {
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
  name: "Jarvis: aprobación de correos",
  description: "Botones Enviar/Descartar de los borradores de correo",
  register(api) {
    api.registerInteractiveHandler({
      channel: "telegram",
      namespace: NAMESPACE,
      handler: async (ctx) => {
        // Solo el dueño y por privado; la API comprueba además que el borrador es suyo.
        if (!ctx.auth?.isAuthorizedSender || ctx.isGroup || !ctx.senderId) {
          return { handled: true };
        }
        const parsed = parsePayload(ctx.callback?.payload);
        if (!parsed) {
          await ctx.respond.clearButtons();
          return { handled: true };
        }
        const original = ctx.callback?.messageText ?? "";
        try {
          const result = await callApi(parsed.path, parsed.token, ctx.senderId);
          const text = result.ok ? doneText(parsed.action, result.body) : errorText(result.status, result.body);
          await ctx.respond.editMessage({ text: `${original}\n\n${text}`.trim() });
        } catch (error) {
          await ctx.respond.reply({ text: `⚠️ No se pudo contactar con la API: ${error.message}` });
        }
        return { handled: true };
      },
    });
    api.logger?.info?.("[jarvis-aprobaciones] botones de correo registrados");
  },
};
