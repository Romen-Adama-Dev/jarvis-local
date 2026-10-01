"""Benchmarks de Jarvis contra el sistema en marcha (docs/BENCHMARKS.md, "Benchmarks de
Jarvis"). Lo lanza scripts/benchmark-jarvis dentro de la imagen jarvis-local.

Mide lo que el usuario nota y lo que el TFM tiene que demostrar:

* rag        calidad (respuesta correcta y con su fuente), abstención fuera de dominio y
             latencia de /v1/rag/query sobre la documentación general indexada.
* traduccion terminología y latencia de la traducción de la consulta al inglés (la misma
             que hace el RAG, con su mismo prompt y modelo).
* actas      una reunión sintetizada con la voz de Jarvis: tiempo total, factor de tiempo
             real, error de transcripción (WER) y qué parte del acta sale bien.
* documentos un resumen generado desde el RAG: tiempo y secciones con evidencia.

Los casos están en docs/benchmarks/casos/ y el resultado se guarda como JSON en
docs/benchmarks/. No crea nada en OpenProject, el vault ni el RAG.
"""

import argparse
import datetime
import json
import os
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "docs" / "benchmarks" / "casos"
API = os.environ.get("JARVIS_API_URL", "http://127.0.0.1:8000")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def primary_model() -> str:
    """El modelo que eligió init según la VRAM (/run/jarvis/models.env), si no viene dado."""
    if model := os.environ.get("OLLAMA_PRIMARY_MODEL"):
        return model
    models = Path("/run/jarvis/models.env")
    lines = models.read_text().splitlines() if models.exists() else []
    found = [line.split("=", 1)[1] for line in lines if line.startswith("OLLAMA_PRIMARY_MODEL=")]
    return found[0].strip() if found else ""


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text)


def matches(text: str, groups: list[list[str]]) -> bool:
    """Al menos una palabra de cada grupo aparece en el texto (sin tildes ni mayúsculas)."""
    text = norm(text)
    return all(any(norm(word) in text for word in group) for group in groups)


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 2)


def timing(values: list[float]) -> dict:
    return {"mediana_s": round(statistics.median(values), 2), "p95_s": pct(values, 0.95)}


class Api:
    def __init__(self) -> None:
        token = Path(os.environ.get("JARVIS_TOKEN_FILE", "/run/jarvis/jarvis_api_internal_token"))
        self.client = httpx.Client(
            base_url=API,
            headers={"Authorization": f"Bearer {token.read_text().strip()}"},
            timeout=600,
        )

    def post(self, path: str, **kwargs) -> dict:
        response = self.client.post(path, **kwargs)
        response.raise_for_status()
        return response.json()

    def wait(self, job_id: str, limit: int = 3600) -> tuple[dict, float]:
        start = time.perf_counter()
        while time.perf_counter() - start < limit:
            job = self.client.get(f"/v1/jobs/{job_id}").json()
            if job["status"] in ("completed", "failed", "cancelled"):
                return job, time.perf_counter() - start
            time.sleep(2)
        raise TimeoutError(f"el trabajo {job_id} no terminó en {limit} s")


def bench_rag(api: Api) -> dict:
    cases = json.loads((CASES / "rag.json").read_text(encoding="utf-8"))
    rows, times = [], []
    for case in cases["dentro"] + cases["fuera"]:
        inside = "espera" in case
        start = time.perf_counter()
        result = api.post("/v1/rag/query", json={"query": case["pregunta"]})
        times.append(time.perf_counter() - start)
        files = [s["filename"] for s in result["sources"]]
        row = {
            "id": case["id"],
            "segundos": round(times[-1], 2),
            "abstencion": result["insufficient_evidence"],
            "confianza": round(result["confidence"], 3),
        }
        if inside:
            row["fuente"] = any(f.startswith(case["fuente"]) for f in files)
            row["respuesta"] = matches(result["answer"], case["espera"])
            row["correcta"] = row["fuente"] and row["respuesta"] and not row["abstencion"]
        else:
            row["correcta"] = result["insufficient_evidence"]
        row["respuesta_texto"] = result["answer"]
        row["fuentes"] = [
            f"{f.split('---')[0]} p.{s['page']}"
            for f, s in zip(files, result["sources"], strict=True)
        ]
        rows.append(row)
        print(
            f"  rag {row['id']:28} {row['segundos']:6.1f}s {'OK' if row['correcta'] else 'FALLO'}",
            flush=True,
        )
    inside = [r for r in rows if "fuente" in r]
    outside = [r for r in rows if "fuente" not in r]
    snyder = [r for r in inside if r["id"].startswith("snyder")]
    return {
        "preguntas": len(rows),
        "aciertos_dentro": f"{sum(r['correcta'] for r in inside)}/{len(inside)}",
        "fuente_citada": f"{sum(r['fuente'] for r in inside)}/{len(inside)}",
        "documento_en_ingles": f"{sum(r['correcta'] for r in snyder)}/{len(snyder)}",
        "abstenciones_correctas": f"{sum(r['correcta'] for r in outside)}/{len(outside)}",
        "abstenciones_indebidas": sum(r["abstencion"] for r in inside),
        **timing(times),
        "casos": rows,
    }


def bench_translation() -> dict:
    sys.path.insert(0, str(ROOT))
    from packages.rag.orchestrator import _TRANSLATION_PROMPT

    model = primary_model()
    cases = json.loads((CASES / "traduccion.json").read_text(encoding="utf-8"))

    def translate(text: str) -> str:
        response = httpx.post(
            f"{OLLAMA}/api/chat",
            timeout=300,
            json={
                "model": model,
                "stream": False,
                "think": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": _TRANSLATION_PROMPT},
                    {"role": "user", "content": text},
                ],
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip().splitlines()[0]

    translate("hola")  # carga del modelo, fuera de la medida
    rows, times, hits, total = [], [], 0, 0
    for case in cases:
        start = time.perf_counter()
        out = translate(case["es"])
        times.append(time.perf_counter() - start)
        found = [t for t in case["terms"] if t in out.lower()]
        hits, total = hits + len(found), total + len(case["terms"])
        rows.append({"es": case["es"], "en": out, "terminos": f"{len(found)}/{len(case['terms'])}"})
    print(f"  traducción {hits}/{total} términos", flush=True)
    return {"modelo": model, "terminos": f"{hits}/{total}", **timing(times), "casos": rows}


def wer(reference: str, hypothesis: str) -> float:
    """Tasa de error por palabra (Levenshtein sobre palabras, sin puntuación ni tildes)."""
    ref = re.findall(r"[a-z0-9]+", norm(reference))
    hyp = re.findall(r"[a-z0-9]+", norm(hypothesis))
    previous = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, start=1):
        current = [i] + [0] * len(hyp)
        for j, other in enumerate(hyp, start=1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (word != other))
        previous = current
    return round(previous[-1] / max(1, len(ref)), 3)


def bench_minutes(api: Api, audio: Path) -> dict:
    case = json.loads((CASES / "reunion.json").read_text(encoding="utf-8"))
    with audio.open("rb") as fh:
        job = api.post(
            "/v1/meetings", params={"format": "md"}, files={"file": (audio.name, fh, "audio/wav")}
        )
    job, seconds = api.wait(job["id"])
    if job["status"] != "completed":
        return {"error": job.get("error") or job["status"]}
    result = job["result"]
    minutes = result["minutes"]
    markdown = api.client.get(f"/v1/meetings/{job['id']}/markdown").text
    transcript = markdown.split("## Anexo: transcripción", 1)[-1]
    transcript = re.sub(r"\[[0-9:.,\s-]+\]", " ", transcript)  # marcas de tiempo
    guion = re.sub(r"^\w+( \w+)?:", " ", case["guion"], flags=re.MULTILINE)

    attendees = norm(" ".join(minutes["asistentes"]))
    actions = minutes["acciones"]

    def action_ok(expected: dict) -> bool:
        return any(
            expected["responsable"] in norm(a["responsable"])
            and expected["fecha"] in a["fecha_limite"]
            and matches(a["tarea"] + " " + a.get("detalle", ""), [expected["tarea"]])
            for a in actions
        )

    risks = minutes["riesgos"]
    checks = {
        "fecha": minutes["fecha"] == case["fecha"],
        "asistentes": sum(name in attendees for name in case["asistentes"]),
        "decisiones": sum(
            matches(" ".join(minutes["decisiones"]), [g]) for g in case["decisiones"]
        ),
        "acciones": sum(action_ok(a) for a in case["acciones"]),
        "riesgos": sum(
            any(
                matches(r["riesgo"] + " " + r["mitigacion"], [e["riesgo"]])
                and e["responsable"] in norm(r["responsable"])
                for r in risks
            )
            for e in case["riesgos"]
        ),
        "proxima_reunion": matches(minutes["proxima_reunion"], case["proxima_reunion"]),
    }
    expected = {
        "fecha": 1,
        "asistentes": len(case["asistentes"]),
        "decisiones": len(case["decisiones"]),
        "acciones": len(case["acciones"]),
        "riesgos": len(case["riesgos"]),
        "proxima_reunion": 1,
    }
    got = sum(int(v) for v in checks.values())
    duration = result.get("duration", "")
    print(f"  actas {seconds:.0f}s, {got}/{sum(expected.values())} elementos", flush=True)
    return {
        "segundos": round(seconds, 1),
        "duracion_audio": duration,
        "wer": wer(guion, transcript),
        "elementos": f"{got}/{sum(expected.values())}",
        "detalle": {k: f"{int(v)}/{expected[k]}" for k, v in checks.items()},
        "acta": minutes,
    }


def bench_documents(api: Api) -> dict:
    job = api.post(
        "/v1/documents/generate",
        json={"kind": "resumen", "topic": "los dominios de desempeño del proyecto", "format": "md"},
    )
    job, seconds = api.wait(job["id"])
    if job["status"] != "completed":
        return {"error": job.get("error") or job["status"]}
    sections = job["result"]["sections"]
    with_evidence = sum(not s["insufficient_evidence"] for s in sections)
    print(f"  documento {seconds:.0f}s, {with_evidence}/{len(sections)} secciones", flush=True)
    return {
        "segundos": round(seconds, 1),
        "secciones_con_evidencia": f"{with_evidence}/{len(sections)}",
        "secciones": sections,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--solo", default="rag,traduccion,actas,documentos")
    parser.add_argument("--audio", type=Path, help="WAV de la reunión (lo sintetiza el lanzador)")
    parser.add_argument(
        "--con-respuestas",
        action="store_true",
        help="guarda cada respuesta (cita la documentación: no subirlo a un repo público)",
    )
    parser.add_argument("--salida", type=Path, default=ROOT / "docs" / "benchmarks")
    args = parser.parse_args()
    wanted = set(args.solo.split(","))
    api = Api()
    report: dict = {
        "fecha": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "modelo": primary_model(),
        "gpu": os.environ.get("BENCH_GPU", ""),
        "commit": os.environ.get("BENCH_COMMIT", ""),
    }
    benches = {
        "rag": lambda: bench_rag(api),
        "traduccion": bench_translation,
        "actas": lambda: bench_minutes(api, args.audio) if args.audio else {"error": "sin audio"},
        "documentos": lambda: bench_documents(api),
    }
    for name, bench in benches.items():
        if name not in wanted:
            continue
        try:
            report[name] = bench()
        except Exception as exc:  # noqa: BLE001 — se apunta y se sigue con el resto
            report[name] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"  {name}: ERROR {exc}", flush=True)
    if not args.con_respuestas and isinstance(report.get("rag"), dict):
        for case in report["rag"].get("casos", []):
            case.pop("respuesta_texto", None)
    args.salida.mkdir(parents=True, exist_ok=True)
    stamp = report["fecha"].replace(":", "-").removesuffix("+00-00")
    out = args.salida / f"jarvis-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summary = {
        k: {kk: vv for kk, vv in v.items() if kk not in ("casos", "acta", "secciones")}
        for k, v in report.items()
        if isinstance(v, dict)
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"Guardado en {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


if __name__ == "__main__":
    main()
