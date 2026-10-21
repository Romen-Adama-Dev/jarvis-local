// Plugin de OpenClaw `jarvis-formato`: deja en texto plano las fórmulas en LaTeX de las
// respuestas de Jarvis, en lo que se guarda (y enseña el panel) y en lo que sale por los
// canales (Telegram). Ver formato.js.
import { cleanAssistantMessage, latexToText } from "./formato.js";

export default {
  id: "jarvis-formato",
  name: "Jarvis: formato de las respuestas",
  description: "Fórmulas en texto plano: el chat no dibuja LaTeX",
  register(api) {
    // Síncrono: OpenClaw no espera promesas en este gancho
    api.on("before_message_write", (event) => {
      const message = cleanAssistantMessage(event?.message);
      return message ? { message } : undefined;
    });
    api.on("message_sending", (event) => {
      const content = latexToText(event?.content);
      return content !== event?.content ? { content } : undefined;
    });
    api.logger?.info?.("[jarvis-formato] fórmulas en texto plano en las respuestas");
  },
};
