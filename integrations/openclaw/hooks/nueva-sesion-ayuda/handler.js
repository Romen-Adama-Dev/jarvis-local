const GUIA = `🤖 *Jarvis — sesión nueva lista*

Soy tu asistente local: la IA corre en tu servidor (Ollama + GTX 1070), sin nube.

📚 *Documentación (RAG)*
• Adjunta un PDF, DOCX, TXT, MD, HTML, CSV o XLSX y lo indexo (máx. 50 MiB).
• Pregúntame por su contenido: respondo citando documento y sección/página.
• "¿Qué trabajos de indexación hay?" · "Cancela el trabajo X".
• Si no hay evidencia en tus documentos, te lo digo — no invento.

🧠 *Modo profundo (/deep)*
• "Analiza en profundidad ..." o "/deep ..." — encolo la consulta en AirLLM (lento por diseño, sin prisas) y te doy un número de trabajo.
• "¿Cómo va el trabajo X?" / "dame el resultado del trabajo X" — recojo la respuesta cuando termine.

📧 *Correo y calendario* (Google, requiere autorización única del propietario)
• "¿Tengo correos nuevos?" · "Léeme el último correo de X" · "¿Qué tengo mañana en la agenda?" — lectura directa y segura (solo lectura).
• "Respóndele a X que..." · "Crea un evento el viernes a las 10" — te enseño el borrador, espero tu sí y además pido aprobación con botones.

🌐 *Búsqueda web*
• "Busca en la web ..." — uso un SearXNG propio del servidor, sin API keys.

🖥️ *Control del servidor*
• "Ejecuta uptime / df -h / nvidia-smi..." — comandos de solo lectura corren directos.
• Cualquier otro comando te pedirá confirmación con botones (o /approve).
• Puedo crear y editar archivos: "crea un documento con..." (workspace o jarvis-inbox).
• "¿Cómo va el sistema?" → estado de servicios, disco, modelos, GPU.

🎙️ *Voz*
• Mándame una nota de voz: la transcribo (📝) y te contesto también con audio.
• /tts on | off — activar/desactivar mis respuestas de voz.

🛡️ *Proactividad*
• Un watchdog vigila servicios, disco y GPU cada 5 min y te aviso si algo falla.

⌨️ *Comandos*
/new [modelo] — sesión nueva (con esta guía)
/reset — reinicia el contexto de la sesión
/stop — detiene lo que esté haciendo
/status — estado de la sesión y del gateway
/model — ver o cambiar el modelo (qwen3:4b rápido · llama3.1:8b potente)
/compact — resume la conversación para liberar contexto
/approve — aprobar un comando pendiente
/tts on|off — respuestas con voz
/help — ayuda de OpenClaw

Escríbeme en lenguaje natural: entiendo peticiones normales, no hace falta comando. 🚀`;

const handler = async (event) => {
  if (event.type !== "command") return;
  if (event.action !== "new" && event.action !== "reset") return;
  console.log("[nueva-sesion-ayuda] disparado:", event.action, "sesión:", event.sessionKey);
  event.messages.push(GUIA);
};

export default handler;
