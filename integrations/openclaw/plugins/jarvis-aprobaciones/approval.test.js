import assert from "node:assert/strict";
import { test } from "node:test";

import { NAMESPACE, PEOPLE_NAMESPACE, doneText, errorText, parsePayload } from "./approval.js";

const TOKEN = "AbCdEf0123456789_-xYzW";

test("el callback más largo cabe en los 64 bytes de Telegram", () => {
  assert.ok(Buffer.byteLength(`${NAMESPACE}:descartar:${TOKEN}`) <= 64);
});

test("enviar y descartar llevan a confirm y cancel", () => {
  assert.deepEqual(parsePayload(`enviar:${TOKEN}`), { action: "enviar", path: "confirm", token: TOKEN, url: `/v1/email/draft/${TOKEN}/confirm` });
  assert.deepEqual(parsePayload(`descartar:${TOKEN}`), { action: "descartar", path: "cancel", token: TOKEN, url: `/v1/email/draft/${TOKEN}/cancel` });
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

test("los botones de altas en OpenProject van a /v1/pm/people", () => {
  assert.deepEqual(parsePayload(`alta:${TOKEN}`, PEOPLE_NAMESPACE), {
    action: "alta",
    path: "confirm",
    token: TOKEN,
    url: `/v1/pm/people/${TOKEN}/confirm`,
  });
  assert.equal(parsePayload(`descartar:${TOKEN}`, PEOPLE_NAMESPACE).url, `/v1/pm/people/${TOKEN}/cancel`);
  // Cada espacio solo acepta sus acciones: un «alta» no vale como correo ni al revés.
  assert.equal(parsePayload(`alta:${TOKEN}`), null);
  assert.equal(parsePayload(`enviar:${TOKEN}`, PEOPLE_NAMESPACE), null);
  assert.equal(parsePayload(`alta:${TOKEN}`, "otro"), null);
  assert.ok(Buffer.byteLength(`${PEOPLE_NAMESPACE}:descartar:${TOKEN}`) <= 64);
});

test("texto de las altas hechas", () => {
  assert.equal(
    doneText("alta", { lines: ["👤 Diego Sanz: dado de alta", "   · Talleres Norte › App: miembro"] }, PEOPLE_NAMESPACE),
    "✅ Hecho en OpenProject:\n👤 Diego Sanz: dado de alta\n   · Talleres Norte › App: miembro",
  );
  assert.equal(doneText("descartar", {}, PEOPLE_NAMESPACE), "🗑️ Altas descartadas.");
});
