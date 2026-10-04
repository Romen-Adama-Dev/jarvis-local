"""Benchmark de la demo: Jarvis monta dos clientes unidos con un solo mensaje.

Lo lanza scripts/benchmark-demo desde el servidor (necesita `docker compose`). Cada pasada:

1. Deja el escenario vacío: borra de OpenProject las empresas y las personas del caso,
   quita de MEMORY.md sus proyectos y las metodologías que el caso crea, y borra sus
   notas del vault. Nada más: el resto de OpenProject, el RAG y el vault no se tocan.
2. Manda el mensaje del caso a Jarvis en una sesión nueva y aislada (como un mensaje de
   Telegram, pero sin pasar por el chat) y mide el tiempo hasta su respuesta.
3. Con `--aprobar`, hace de propietario: cuando Jarvis pide las altas, espera `--espera`
   segundos (lo que tardaría en pulsar) y las confirma por la API, igual que el botón.
   Sin `--aprobar`, el aviso con botones llega al Telegram del propietario y la pasada
   cuenta solo que Jarvis lo pidió.
4. Saca de la trayectoria de la sesión los turnos del modelo, las llamadas a
   herramientas y el tiempo de cada cosa, y comprueba qué quedó hecho en OpenProject.

El caso está en docs/benchmarks/casos/demo-dos-clientes.json; el resultado se guarda en
docs/benchmarks/demo-<fecha>.json. La última pasada se queda montada para verla.
"""

import argparse
import datetime
import json
import statistics
import subprocess
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "docs" / "benchmarks" / "casos" / "demo-dos-clientes.json"


# --- docker compose -----------------------------------------------------------------------


def compose(*args: str, stdin: str | None = None, timeout: int = 600) -> str:
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        # La primera línea con «Error» dice más que el final de una traza de Ruby.
        lines = result.stderr.splitlines()
        cause = next((line for line in lines if "Error" in line or "error:" in line), "")
        raise RuntimeError(f"docker compose {' '.join(args[:3])}…: {cause or result.stderr[-800:]}")
    return result.stdout


def python_in(service: str, code: str, *extra: str) -> str:
    """Ejecuta `code` con el Python del servicio (knowledge o api), con el repo en el path."""
    return compose(
        "exec",
        "-T",
        "-w",
        "/app",
        "-e",
        "PYTHONPATH=/app",
        service,
        "python",
        "-",
        *extra,
        stdin=code,
    )


def rails(code: str) -> str:
    """Ruby en OpenProject sin mandar correos (como infra/docker/openproject-setup.rb)."""
    with tempfile.NamedTemporaryFile("w", suffix=".rb", delete=False) as script:
        # Borrar un proyecto avisa por correo a sus miembros: aquí no se manda nada.
        script.write(
            "ActionMailer::Base.delivery_method = :test\n"
            "ActionMailer::Base.perform_deliveries = false\n" + code
        )
    Path(script.name).chmod(0o644)  # lo lee el usuario de OpenProject, no el nuestro
    compose("cp", script.name, "openproject:/tmp/benchmark-demo.rb")
    Path(script.name).unlink()
    return compose(
        "exec",
        "-T",
        "-e",
        "MAIL_PROVIDER=none",
        "openproject",
        "/opt/jarvis/openproject-entrypoint.sh",
        "bundle",
        "exec",
        "rails",
        "runner",
        "/tmp/benchmark-demo.rb",
    )


# --- 1. Escenario vacío -------------------------------------------------------------------

RESET_MEMORY = """
import json, sys
from pathlib import Path
from packages.core.directives import write_directive
case = json.loads(sys.argv[1])
memory = Path("/state/workspace-jarvis/MEMORY.md")
for p in case["proyectos"]:
    write_directive(memory, "proyecto", f"{p['empresa']} › {p['proyecto']}", "", replace_all=True)
for method in case["metodologias_nuevas"]:
    write_directive(memory, "metodologia", method, "", replace_all=True)
"""


def reset(case: dict) -> None:
    companies = json.dumps([p["empresa"] for p in case["proyectos"]])
    emails = json.dumps([p["correo"] for p in case["personas"]])
    rails(f"""
admin = User.user.where(admin: true).where.not(login: "jarvis").order(:id).first
User.current = admin
Project.where(name: {companies}, parent_id: nil).each do |project|
  Projects::DeleteService.new(user: admin, model: project).call
end
User.where(mail: {emails}).each {{ |user| Principals::DeleteJob.perform_now(user) }}
""")
    python_in("knowledge", RESET_MEMORY, json.dumps(case))
    folders = " ".join(f'"entities/Empresas/{p["empresa"]}"' for p in case["proyectos"])
    methods = " ".join(
        f'"concepts/Conocimiento/Metodologías/{m}"' for m in case["metodologias_nuevas"]
    )
    compose(
        "exec",
        "-T",
        "knowledge",
        "sh",
        "-c",
        f"cd /state/wiki/main && rm -rf {folders} entities/Nexos {methods}",
    )


# --- 2-3. La pasada y la aprobación -------------------------------------------------------

APPROVALS = """
import asyncio, json, sys, httpx
from apps.api.jarvis_api.deps import _redis_client

async def main(confirm):
    redis = _redis_client()
    token = open("/run/jarvis/jarvis_api_internal_token").read().strip()
    async for key in redis.scan_iter("jarvis:confirmation:*"):
        raw = await redis.get(key)
        pending = json.loads(raw) if raw else {}
        if pending.get("action") != "pm_people":
            continue
        if not confirm:
            print(json.dumps({"token": pending["token"]}))
            continue
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"http://127.0.0.1:8000/v1/pm/people/{pending['token']}/confirm",
                json={"telegram_user_id": pending["telegram_user_id"]},
                headers={"Authorization": f"Bearer {token}"},
            )
        lines = response.json().get("lines", [])
        print(json.dumps({"status": response.status_code, "lines": lines}))

asyncio.run(main(sys.argv[1] == "confirmar"))
"""


def approver(start: float, stop: threading.Event, wait: float, log: dict) -> None:
    """Hace de propietario: confirma las altas `wait` segundos después de que se pidan."""
    while not stop.is_set():
        if python_in("api", APPROVALS, "listar").strip():
            log.setdefault("pedida_s", round(time.monotonic() - start, 1))
            time.sleep(wait)
            out = python_in("api", APPROVALS, "confirmar").strip().splitlines()
            log["aprobada_s"] = round(time.monotonic() - start, 1)
            log["resultado"] = [json.loads(line) for line in out]
        stop.wait(3)


def run_once(case: dict, key: str, args: argparse.Namespace) -> dict:
    compose(
        "exec", "-T", "openclaw", "sh", "-c", "cat > /tmp/benchmark-demo.txt", stdin=case["mensaje"]
    )
    approval: dict = {}
    stop = threading.Event()
    start = time.monotonic()
    watcher = threading.Thread(
        target=approver, args=(start, stop, args.espera, approval), daemon=True
    )
    if args.aprobar:
        watcher.start()
    out = compose(
        "exec",
        "-T",
        "openclaw",
        "openclaw",
        "agent",
        "--agent",
        "main",
        "--session-key",
        key,
        "--message-file",
        "/tmp/benchmark-demo.txt",
        "--timeout",
        str(args.timeout),
        "--json",
        timeout=args.timeout + 120,
    )
    wall = round(time.monotonic() - start, 1)
    if args.aprobar:
        # Por si pidió las altas en el último turno: un margen para confirmarlas.
        time.sleep(args.espera + 5)
        stop.set()
        watcher.join(timeout=120)
    elif python_in("api", APPROVALS, "listar").strip():
        approval["pedida_s"] = "sí (pendiente en Telegram)"
    reply = json.loads(out[out.find("{") : out.rfind("}") + 1])
    texts = [p.get("text") or "" for p in reply.get("result", {}).get("payloads", [])]
    return {"segundos": wall, "respuesta": "\n".join(texts), "aprobacion": approval}


# --- 4. Medidas y resultado ---------------------------------------------------------------


def _ts(event: dict) -> float:
    return datetime.datetime.fromisoformat(event["ts"].replace("Z", "+00:00")).timestamp()


def trajectory(key: str) -> dict:
    """Turnos del modelo, llamadas a herramientas y tiempo de cada cosa."""
    name = key.rsplit(":", 1)[-1]
    raw = compose(
        "exec",
        "-T",
        "openclaw",
        "sh",
        "-c",
        f"cd /tmp && openclaw sessions export-trajectory --session-key {key} --output {name} "
        f">/dev/null 2>&1; cat /tmp/.openclaw/trajectory-exports/{name}/events.jsonl; "
        f"rm -rf /tmp/.openclaw/trajectory-exports/{name}",
    )
    events = sorted((json.loads(line) for line in raw.splitlines() if line.strip()), key=_ts)
    calls, results, model, last = {}, {}, 0.0, None
    turns, failed, names = 0, 0, []
    for event in events:
        data = event.get("data", {})
        if event["type"] == "prompt.submitted":
            last = _ts(event)
        elif event["type"] == "assistant.message":
            turns += 1
            if last is not None:
                model += max(_ts(event) - last, 0)
        elif event["type"] == "tool.call" and data.get("toolCallId") not in calls:
            calls[data.get("toolCallId")] = _ts(event)
            names.append(data.get("name", "?"))
        elif event["type"] == "tool.result":
            results[data.get("toolCallId")] = _ts(event)
            last = _ts(event)
            failed += "No se pudo" in json.dumps(data, ensure_ascii=False)
    tools = sum(results[c] - t for c, t in calls.items() if c in results)
    return {
        "turnos_modelo": turns,
        "llamadas": len(calls),
        "llamadas_fallidas": failed,
        "segundos_modelo": round(model, 1),
        "segundos_herramientas": round(tools, 1),
        "herramientas": names,
    }


EVALUATE = """
import json, sys
from pathlib import Path
from packages.core.directives import parse_directives
from packages.openproject.client import OpenProjectClient, _normalize
from packages.openproject.config import config_from_env
case = json.loads(sys.argv[1])
op = OpenProjectClient(config_from_env())
directives = parse_directives(Path("/state/workspace-jarvis/MEMORY.md").read_text(encoding="utf-8"))
users = {u.get("email", "").lower(): u for u in op.users()}
# Sin tildes ni mayúsculas: «Lucia Martín» es Lucía Martín (como al asignar tareas).
names = {_normalize(p["nombre"]) for p in case["personas"]}
checks, work = {}, {}
for p in case["proyectos"]:
    label = f"{p['empresa']} › {p['proyecto']}"
    try:
        project = op.find_project(label)
    except Exception:
        # Sin proyecto, todo lo suyo cuenta como no hecho: el total es siempre el mismo.
        for key in (f"proyecto {label}", f"metodología {p['proyecto']} en MEMORY.md",
                    f"equipo en {p['proyecto']}", f"tareas en {p['proyecto']}",
                    f"tareas asignadas en {p['proyecto']}"):
            checks[key] = False
        if case["hito"]["proyecto"] == p["proyecto"]:
            checks["hito del 15-dic"] = False
        continue
    parent = (project["_links"].get("parent") or {}).get("title")
    checks[f"proyecto {label}"] = parent == p["empresa"]
    methods = directives.for_project(p["empresa"], p["proyecto"])
    checks[f"metodología {p['proyecto']} en MEMORY.md"] = p["metodologia"].lower() in methods
    assignees = {_normalize(a["name"]) for a in op.assignees(project["id"])}
    checks[f"equipo en {p['proyecto']}"] = names <= assignees
    wps = op.work_packages(project, only_open=False, limit=200)
    tasks = [w for w in wps if w["_links"]["type"]["title"] not in ("Hito", "Riesgo")]
    checks[f"tareas en {p['proyecto']}"] = len(tasks) >= len(names)
    assigned = [_normalize((w["_links"].get("assignee") or {}).get("title") or "") for w in tasks]
    checks[f"tareas asignadas en {p['proyecto']}"] = sum(a in names for a in assigned) >= len(names)
    for w in tasks:
        who = _normalize((w["_links"].get("assignee") or {}).get("title") or "")
        if who:
            work.setdefault(who, set()).add(p["proyecto"])
    if case["hito"]["proyecto"] == p["proyecto"]:
        milestones = [w for w in wps if w["_links"]["type"]["title"] == "Hito"]
        checks["hito del 15-dic"] = any(w.get("date") == case["hito"]["fecha"] for w in milestones)
dep = case.get("dependencia")
if dep:
    ids = {}
    for p in case["proyectos"]:
        try:
            project = op.find_project(f"{p['empresa']} › {p['proyecto']}")
        except Exception:
            continue
        for w in op.work_packages(project, only_open=False, limit=200):
            ids[str(w["id"])] = p["proyecto"]
    ordering = {"precedes": 1, "blocks": 1, "follows": -1, "blocked": -1}
    linked = False
    for r in op.relations():
        a, b = (r["_links"][k]["href"].rsplit("/", 1)[-1] for k in ("from", "to"))
        if ordering.get(r["type"]) == -1:
            a, b = b, a
        wanted = (dep["antes"], dep["despues"])
        linked |= r["type"] in ordering and (ids.get(a), ids.get(b)) == wanted
    checks["dependencia entre proyectos"] = linked
for person in case["personas"]:
    checks[f"cuenta de {person['nombre']}"] = person["correo"] in users
both = all(len(work.get(n, ())) == len(case["proyectos"]) for n in names)
checks["cada empleado en los dos proyectos"] = both
for method in case["metodologias_nuevas"]:
    checks[f"reglas de {method}"] = method.lower() in {m.lower() for m in directives.methods}
print(json.dumps(checks, ensure_ascii=False))
"""


def evaluate(case: dict) -> dict:
    checks = json.loads(python_in("knowledge", EVALUATE, json.dumps(case)))
    return {"hecho": sum(checks.values()), "total": len(checks), "comprobaciones": checks}


def summary(runs: list[dict]) -> dict:
    def stats(values: list[float]) -> dict:
        return {"mediana": statistics.median(values), "min": min(values), "max": max(values)}

    return {
        "segundos": stats([r["segundos"] for r in runs]),
        "turnos_modelo": stats([r["trayectoria"]["turnos_modelo"] for r in runs]),
        "llamadas": stats([r["trayectoria"]["llamadas"] for r in runs]),
        "hecho": stats([r["resultado"]["hecho"] for r in runs]),
        "total": runs[0]["resultado"]["total"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--veces", type=int, default=3)
    parser.add_argument("--aprobar", action="store_true", help="confirmar las altas por la API")
    parser.add_argument("--espera", type=float, default=10, help="segundos hasta «pulsar»")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    case = json.loads(CASE.read_text(encoding="utf-8"))
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    runs = []
    for i in range(1, args.veces + 1):
        print(f"Pasada {i}/{args.veces}: limpiando el escenario…", flush=True)
        reset(case)
        key = f"agent:main:bench-demo-{stamp}-{i}"
        result = run_once(case, key, args)
        result["trayectoria"] = trajectory(key)
        result["resultado"] = evaluate(case)
        runs.append(result)
        t, r = result["trayectoria"], result["resultado"]
        print(
            f"  {result['segundos']:.0f} s · {t['turnos_modelo']} turnos · "
            f"{t['llamadas']} llamadas "
            f"({t['llamadas_fallidas']} fallidas) · modelo {t['segundos_modelo']:.0f} s · "
            f"herramientas {t['segundos_herramientas']:.0f} s · hecho {r['hecho']}/{r['total']}",
            flush=True,
        )
    report = {
        "caso": case["nombre"],
        "fecha": datetime.datetime.now().isoformat(timespec="seconds"),
        "aprobacion": f"simulada a los {args.espera:g} s" if args.aprobar else "por Telegram",
        "resumen": summary(runs),
        "pasadas": runs,
    }
    out = ROOT / "docs" / "benchmarks" / f"demo-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Resumen: {json.dumps(report['resumen'], ensure_ascii=False)}")
    print(f"Guardado en {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
