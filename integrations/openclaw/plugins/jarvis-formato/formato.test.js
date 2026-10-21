import assert from "node:assert/strict";
import { test } from "node:test";

import { cleanAssistantMessage, latexToText } from "./formato.js";

test("las fórmulas en LaTeX pasan a texto", () => {
  const cases = [
    ["**Exactitud del inventario:** $\\ge$ 99,5 % tras el arranque.", "**Exactitud del inventario:** ≥ 99,5 % tras el arranque."],
    ["Fórmula: $\\text{SPI} = \\frac{\\text{EV}}{\\text{PV}}$", "Fórmula: SPI = EV / PV"],
    ["$$\\text{CV} = \\text{EV} - \\text{AC}$$", "CV = EV - AC"],
    ["\\(\\frac{\\text{EV} - \\text{PV}}{\\text{PV}} \\times 100\\)", "(EV - PV) / PV × 100"],
    ["$\\text{SPI} \\geq 0{,}95$ y $\\text{CPI} \\leq 1$", "SPI ≥ 0,95 y CPI ≤ 1"],
    ["El CPI es \\frac{EV}{AC} \\times 100", "El CPI es EV / AC × 100"],
  ];
  for (const [latex, plain] of cases) assert.equal(latexToText(latex), plain);
});

test("el dinero y el texto normal no se tocan", () => {
  for (const text of ["Entre $500 y $300 por licencia.", "SPI = EV / PV = 0,92", "Usa {proyecto}.", ""]) {
    assert.equal(latexToText(text), text);
  }
  assert.equal(latexToText(undefined), undefined);
});

test("solo se limpian los mensajes del asistente, y solo si hace falta", () => {
  const message = { role: "assistant", content: [{ type: "text", text: "Meta: $\\ge$ 99,5 %" }, { type: "toolCall", name: "x" }] };
  const clean = cleanAssistantMessage(message);
  assert.equal(clean.content[0].text, "Meta: ≥ 99,5 %");
  assert.equal(clean.content[1], message.content[1]);
  assert.equal(message.content[0].text, "Meta: $\\ge$ 99,5 %"); // sin mutar el original
  assert.equal(cleanAssistantMessage({ role: "user", content: "$\\ge$" }), null);
  assert.equal(cleanAssistantMessage({ role: "assistant", content: "sin fórmulas" }), null);
  assert.equal(cleanAssistantMessage({ role: "assistant", content: "$\\ge$ 5" }).content, "≥ 5");
});
