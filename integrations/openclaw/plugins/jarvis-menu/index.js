// Plugin de OpenClaw `jarvis-menu`: comando /menu con botones en línea de Telegram y el
// manejador de sus pulsaciones. Registro en integrations/openclaw/config/openclaw.template.json
// (plugins.load.paths); docs/TELEGRAM.md.
import { ACTIONS, MENU_TEXT, NAMESPACE, actionFor, menuRows } from "./actions.js";

function menuReply() {
  return {
    text: MENU_TEXT,
    presentationTextMode: "fallback",
    presentation: {
      blocks: [
        { type: "text", text: MENU_TEXT },
        ...menuRows().map((buttons) => ({ type: "buttons", buttons })),
      ],
    },
  };
}

export default {
  id: "jarvis-menu",
  name: "Jarvis: menú de acceso rápido",
  description: "Comando /menu con botones de Telegram para las automatizaciones frecuentes",
  register(api) {
    api.registerCommand({
      name: "menu",
      description: "Botones de acceso rápido (acta, memoria, tarea, informe, búsqueda, agenda)",
      channels: ["telegram"],
      requireAuth: true,
      handler: async () => menuReply(),
    });

    api.registerInteractiveHandler({
      channel: "telegram",
      namespace: NAMESPACE,
      handler: async (ctx) => {
        // Solo el dueño (allowlist del canal) y solo por privado: en un grupo nadie más
        // puede disparar acciones con los botones de otro.
        if (!ctx.auth?.isAuthorizedSender || ctx.isGroup) {
          return { handled: true };
        }
        const action = actionFor(ctx.callback?.payload);
        if (!action) {
          await ctx.respond.reply({ text: "Ese botón ya no existe. Usa /menu de nuevo." });
          return { handled: true };
        }
        await ctx.respond.editMessage({ text: `${MENU_TEXT}\n→ ${action.label}` });
        return { handled: true, submitText: action.prompt };
      },
    });

    api.logger?.info?.(`[jarvis-menu] ${ACTIONS.length} acciones registradas`);
  },
};
