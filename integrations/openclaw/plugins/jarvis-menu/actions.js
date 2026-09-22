// Acciones del menú de Jarvis. Cada botón manda al agente una petición en lenguaje
// natural (como si la escribiera el usuario), que sigue el flujo normal: herramientas
// MCP, preguntas que falten y, en todo lo que escribe o envía, el "sí" explícito.
// Este módulo no tiene efectos: se prueba con `node --test`.

export const NAMESPACE = "jarvis";

export const ACTIONS = [
  {
    id: "acta",
    label: "🎙️ Acta de reunión",
    prompt:
      "[Botón: acta de reunión] Quiero levantar el acta de una reunión. Pídeme que te " +
      "envíe la grabación (nota de voz o archivo de audio) y de qué proyecto es. Con el " +
      "audio, transcríbelo y prepara el borrador del acta; no pases nada a OpenProject " +
      "hasta que te diga «sí».",
  },
  {
    id: "memoria",
    label: "🧠 Añadir a la memoria",
    prompt:
      "[Botón: memoria] Quiero guardar algo en tu memoria de Obsidian (una nota, una " +
      "decisión o un riesgo). Pregúntame qué es y de qué proyecto o persona trata; " +
      "enséñame cómo quedará la nota y guárdala solo cuando te diga «sí».",
  },
  {
    id: "tarea",
    label: "✅ Tarea en OpenProject",
    prompt:
      "[Botón: tarea] Quiero crear una tarea en OpenProject. Pregúntame lo que falte " +
      "(proyecto, asunto, tipo, fecha de vencimiento y responsable), enséñame el " +
      "resumen y créala solo cuando te diga «sí».",
  },
  {
    id: "informe",
    label: "📄 Informe de estado",
    prompt:
      "[Botón: informe] Quiero el informe de estado de un proyecto de OpenProject. Si " +
      "no está claro cuál, enséñame la lista de proyectos y pregúntame.",
  },
  {
    id: "buscar",
    label: "🔎 Búsqueda web",
    prompt:
      "[Botón: búsqueda web] Quiero buscar algo en la web con el SearXNG del servidor. " +
      "Pregúntame qué busco y dame los resultados con sus enlaces.",
  },
  {
    id: "agenda",
    label: "📅 Agenda",
    prompt:
      "[Botón: agenda] ¿Qué reuniones y vencimientos tengo en los próximos 7 días?",
  },
];

const BY_ID = new Map(ACTIONS.map((action) => [action.id, action]));

export const MENU_TEXT = "¿Qué hacemos? Elige una acción:";

/** Botones del menú con el contrato `presentation` de OpenClaw (Telegram los pinta como
 * teclado en línea, dos por fila); cada uno devuelve el callback `jarvis:<id>`. */
export function menuButtons() {
  return ACTIONS.map((action) => ({
    label: action.label,
    action: { type: "callback", value: `${NAMESPACE}:${action.id}` },
  }));
}

/** Filas de dos botones (lo que acaba en el teclado de Telegram). */
export function menuRows() {
  const buttons = menuButtons();
  const rows = [];
  for (let i = 0; i < buttons.length; i += 2) rows.push(buttons.slice(i, i + 2));
  return rows;
}

/** Acción de un callback `jarvis:<id>`; null si no existe. */
export function actionFor(payload) {
  return BY_ID.get(String(payload ?? "").trim()) ?? null;
}
