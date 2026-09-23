import assert from "node:assert/strict";
import { test } from "node:test";

import { NAMESPACE, doneText, errorText, parsePayload } from "./approval.js";

const TOKEN = "AbCdEf0123456789_-xYzW";

test("el callback más largo cabe en los 64 bytes de Telegram", () => {
  assert.ok(Buffer.byteLength(`${NAMESPACE}:descartar:${TOKEN}`) <= 64);
});

test("enviar y descartar llevan a confirm y cancel", () => {
  assert.deepEqual(parsePayload(`enviar:${TOKEN}`), { action: "enviar", path: "confirm", token: TOKEN });
  assert.deepEqual(parsePayload(`descartar:${TOKEN}`), { action: "descartar", path: "cancel", token: TOKEN });
});

test("rechaza acciones desconocidas y tokens que podrían cambiar la ruta", () => {
  for (const bad of ["", "enviar:", "borrar:" + TOKEN, "enviar:../../x/abcdefghijklmnop", `enviar:${TOKEN}/x`]) {
    assert.equal(parsePayload(bad), null, bad);
  }
});

test("textos de resultado y de error", () => {
  assert.equal(doneText("enviar", { to: ["a@b.c", "d@e.f"] }), "✅ Enviado a a@b.c, d@e.f.");
  assert.equal(doneText("descartar"), "🗑️ Borrador descartado.");
  assert.match(errorText(404, { detail: "Confirmación no encontrada o ya usada" }), /404.*ya usada/);
  assert.match(errorText(500, null), /error de la API/);
});
