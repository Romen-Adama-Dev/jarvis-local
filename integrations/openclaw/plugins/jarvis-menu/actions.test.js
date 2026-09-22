import assert from "node:assert/strict";
import { test } from "node:test";

import { ACTIONS, NAMESPACE, actionFor, menuButtons, menuRows } from "./actions.js";

test("cada botón cabe en el callback_data de Telegram (64 bytes) y es único", () => {
  const data = menuButtons().map((b) => b.action.value);
  assert.equal(new Set(data).size, ACTIONS.length);
  for (const value of data) {
    assert.ok(Buffer.byteLength(value) <= 64, value);
    assert.ok(value.startsWith(`${NAMESPACE}:`));
  }
});

test("dos botones por fila", () => {
  const rows = menuRows();
  assert.ok(rows.every((row) => row.length <= 2));
  assert.equal(rows.flat().length, ACTIONS.length);
});

test("las acciones con efectos piden el sí explícito", () => {
  for (const id of ["acta", "memoria", "tarea"]) {
    assert.match(actionFor(id).prompt, /«sí»/);
  }
});

test("callbacks desconocidos no disparan nada", () => {
  assert.equal(actionFor("borrar-todo"), null);
  assert.equal(actionFor(undefined), null);
});
