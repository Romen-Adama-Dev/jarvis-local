// Fórmulas en texto plano: ni Telegram ni el panel dibujan LaTeX, y una respuesta con
// `$\ge$ 99,5 %` o `$\frac{EV}{PV}$` se lee con barras y llaves. AGENTS.md pide fórmulas en
// texto, pero el modelo a veces reescribe en LaTeX lo que la herramienta le dio bien escrito
// («≥» → «$\ge$»); esto lo deja como texto. Mismo criterio que packages/rag/formulas.py.

const SYMBOLS = {
  times: "×", cdot: "·", div: "÷", geq: "≥", ge: "≥", leq: "≤", le: "≤", neq: "≠", ne: "≠",
  approx: "≈", pm: "±", to: "→", rightarrow: "→", Rightarrow: "⇒", infty: "∞", sum: "Σ",
  Delta: "Δ", "%": "%", $: "$", ",": " ", ";": " ", " ": " ", quad: " ", qquad: " ",
  left: "", right: "", displaystyle: "",
};
const WRAPPERS = new Set(["text", "mathrm", "textbf", "mathbf", "textit", "mathit", "operatorname", "mbox"]);
const FRACTIONS = new Set(["frac", "dfrac", "tfrac"]);
// $$…$$, $…$ (sin espacio junto a los dólares, en una línea), \(…\) y \[…\]
const MATH = /\$\$([\s\S]+?)\$\$|\$(?!\s)([^$\n]+?)(?<!\s)\$|\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]/g;
// LaTeX suelto, fuera de los dólares
const BARE = /\\(?:[dt]?frac|text|mathrm|textbf|mathbf|operatorname)\s*\{|\\(?:times|cdot|div|geq|leq|neq|approx|pm|rightarrow|infty|ge|le)(?![A-Za-z])/g;

// Argumento de un comando: lo que hay entre llaves (anidadas) o un solo carácter.
function argument(tex, start) {
  let i = start;
  while (i < tex.length && tex[i] === " ") i += 1;
  if (i >= tex.length) return ["", i];
  if (tex[i] !== "{") return [tex[i], i + 1];
  let depth = 0;
  for (let j = i; j < tex.length; j += 1) {
    if (tex[j] === "{") depth += 1;
    if (tex[j] === "}") depth -= 1;
    if (depth === 0) return [tex.slice(i + 1, j), j + 1];
  }
  return [tex.slice(i + 1), tex.length];
}

const operand = (text) => (/[\s+\-−×·/]/.test(text.trim()) ? `(${text.trim()})` : text.trim());

// Traduce el comando que empieza en `start` (la barra) y dice dónde acaba.
function command(tex, start) {
  const match = /^\\([A-Za-z]+|[\s\S])/.exec(tex.slice(start));
  if (!match) return [tex[start], start + 1];
  const name = match[1];
  let end = start + match[0].length;
  if (FRACTIONS.has(name)) {
    let top, bottom;
    [top, end] = argument(tex, end);
    [bottom, end] = argument(tex, end);
    return [`${operand(formula(top))} / ${operand(formula(bottom))}`, end];
  }
  if (WRAPPERS.has(name)) {
    let inner;
    [inner, end] = argument(tex, end);
    return [formula(inner), end];
  }
  return [SYMBOLS[name] ?? name, end];
}

function formula(tex) {
  const parts = [];
  let i = 0;
  while (i < tex.length) {
    if (tex[i] === "\\") {
      const [text, end] = command(tex, i);
      parts.push(text);
      i = end;
    } else {
      parts.push(tex[i]);
      i += 1;
    }
  }
  return parts.join("").replace(/[{}]/g, "").replace(/[ \t]+/g, " ").trim();
}

/** «$\frac{EV}{PV}$» → «EV / PV». Lo que va entre dólares sin comandos («entre $500 y $300») no se toca. */
export function latexToText(text) {
  if (typeof text !== "string" || !/[\\$]/.test(text)) return text;
  const plain = text.replace(MATH, (whole, ...groups) => {
    const tex = groups.slice(0, 4).find((g) => g !== undefined);
    if (!tex.includes("\\") && !/[\^_]\{/.test(tex)) return whole;
    return formula(tex);
  });
  let out = "";
  let i = 0;
  for (const match of plain.matchAll(BARE)) {
    if (match.index < i) continue;
    const [converted, end] = command(plain, match.index);
    out += plain.slice(i, match.index) + converted;
    i = end;
  }
  return out + plain.slice(i);
}

/** El mensaje del asistente con sus textos limpios, o null si no hay nada que cambiar. */
export function cleanAssistantMessage(message) {
  if (!message || message.role !== "assistant") return null;
  if (typeof message.content === "string") {
    const text = latexToText(message.content);
    return text === message.content ? null : { ...message, content: text };
  }
  if (!Array.isArray(message.content)) return null;
  let changed = false;
  const content = message.content.map((part) => {
    if (part?.type !== "text" || typeof part.text !== "string") return part;
    const text = latexToText(part.text);
    if (text === part.text) return part;
    changed = true;
    return { ...part, text };
  });
  return changed ? { ...message, content } : null;
}
