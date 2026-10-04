"""Ensayo de la demo: manda a Jarvis un guion paso a paso, por voz simulada o por texto.

Lo lanza scripts/ensayo-demo desde el servidor (necesita `docker compose`). Cada paso
entra por `openclaw agent` en una sesión nueva y aislada, con el formato que tendría por
Telegram:

* voz: Piper lo dice, ffmpeg lo pasa a ogg/opus y el transcriptor de la configuración viva
  (whisper-cli con su idioma y vocabulario) lo convierte en
  `[Audio transcript (machine-generated, untrusted)]: "…"`. Se mide también cuánto
  duraría la respuesta leída en voz alta;
* texto: el mensaje tal cual;
* reunion: un guion de reunión (docs/demo/*.txt, «voz|frase») se convierte en una
  grabación de móvil y se deja en media/inbound, con el texto que la acompaña;
* adjunto: un documento en media/inbound con su bloque <file …>.

No borra nada ni pulsa botones: las aprobaciones (correo, altas) llegan al Telegram del
propietario y aquí solo se cuentan. Como no vacía el escenario, el guion debe usar nombres
que no existan aún si se quiere partir de cero. Los resultados (con las respuestas, que
llevan los enlaces del servidor) se guardan fuera del repo, en ~/jarvis-ensayos/.
"""

import argparse
import datetime
import json
import re
import shutil
import subprocess
import time
import unicodedata
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOUND = Path.home() / ".openclaw" / "media" / "inbound"
OUT_DIR = Path.home() / "jarvis-ensayos"
# tools.media.audio.maxBytes (integrations/openclaw/config/openclaw.template.json): por
# encima, OpenClaw no transcribe el audio y la grabación va directa a la herramienta del acta.
AUDIO_MAX_BYTES = 1_048_576


def compose(*args: str, stdin: str | None = None, timeout: int = 1200) -> str:
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
        lines = result.stderr.splitlines()
        cause = next((x for x in lines if "Error" in x or "error:" in x), "")
        raise RuntimeError(f"docker compose {' '.join(args[:4])}…: {cause or result.stderr[-800:]}")
    return result.stdout


def voz(mode: str, arg: str, stdin: str | None = None) -> dict:
    out = compose("exec", "-T", "openclaw", "python3", "/tmp/ensayo/voz.py", mode, arg, stdin=stdin)
    return json.loads(out.strip().splitlines()[-1])


PENDING = """
import asyncio, json
from apps.api.jarvis_api.deps import _redis_client

async def main():
    redis = _redis_client()
    async for key in redis.scan_iter("jarvis:confirmation:*"):
        raw = await redis.get(key)
        print(json.dumps({"action": (json.loads(raw) if raw else {}).get("action")}))

asyncio.run(main())
"""


def pending() -> list[str]:
    """Aprobaciones esperando un botón o un «sí» (solo se cuentan)."""
    out = compose(
        "exec", "-T", "-w", "/app", "-e", "PYTHONPATH=/app", "api", "python", "-", stdin=PENDING
    )
    return [json.loads(x)["action"] for x in out.splitlines() if x.startswith("{")]


# --- Trayectoria del paso --------------------------------------------------------------


def _ts(event: dict) -> float:
    return datetime.datetime.fromisoformat(event["ts"].replace("Z", "+00:00")).timestamp()


def trajectory(key: str, since: float) -> dict:
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
    events = []
    for line in raw.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue  # alguna línea llega cortada en la exportación
    events = sorted((e for e in events if "ts" in e and _ts(e) >= since - 1), key=_ts)
    calls, results, failed, tools = {}, {}, [], []
    model, last, turns, compactions = 0.0, None, 0, 0
    for event in events:
        data = event.get("data", {})
        if event["type"] == "prompt.submitted":
            last = _ts(event)
        elif event["type"] == "assistant.message":
            turns += 1
            if last is not None:
                model += max(_ts(event) - last, 0)
        elif event["type"] == "session.compaction":
            compactions += 1
        elif event["type"] == "tool.call" and data.get("toolCallId") not in calls:
            calls[data.get("toolCallId")] = _ts(event)
            tools.append({"tool": data.get("name", "?"), "args": data.get("arguments") or {}})
        elif event["type"] == "tool.result":
            results[data.get("toolCallId")] = last = _ts(event)
            text = json.dumps(data, ensure_ascii=False)
            if re.search(r"No se pudo|Error executing|Traceback|No encuentro", text):
                failed.append(text[:400])
    return {
        "turnos": turns,
        "llamadas": tools,
        "fallos": failed,
        "compactaciones": compactions,
        "modelo_s": round(model, 1),
        "herramientas_s": round(sum(results[c] - t for c, t in calls.items() if c in results), 1),
    }


# --- Un paso ----------------------------------------------------------------------------


def _words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    return re.findall(r"[a-z0-9]+", "".join(c for c in text if not unicodedata.combining(c)))


def wer(reference: str, heard: str) -> float:
    ref, hyp = _words(reference), _words(heard)
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return round(row[len(hyp)] / max(len(ref), 1), 3)


def spoken(text: str) -> str:
    """Lo que leería Piper: sin líneas MEDIA, enlaces ni símbolos de Markdown."""
    text = "\n".join(x for x in text.splitlines() if not x.strip().startswith("MEDIA:"))
    return re.sub(r"[*_`#>|]", "", re.sub(r"https?://\S+", "", text)).strip()


def attach(step: dict, message: str, n: int, result: dict) -> str:
    if step.get("reunion"):
        script = (ROOT / step["reunion"]).read_text(encoding="utf-8")
        name = f"{Path(step['reunion']).stem}-{n}"
        made = voz("reunion", name, script)
        target = INBOUND / f"{name}.ogg"
        compose("cp", f"openclaw:{made['ogg']}", str(target))
        target.touch()
        result["grabacion_bytes"] = made["bytes"]
        if made["bytes"] > AUDIO_MAX_BYTES:
            return f"{message}\n<media:audio>" if message else "<media:audio>"
        heard = voz("oir", f"/home/jarvis/.openclaw/media/inbound/{target.name}")
        result["stt_s"] = heard["stt_s"]
        caption = f"User text:\n{message}\n" if message else ""
        return f"[Audio]\n{caption}Transcript:\n{heard['texto']}"
    if step.get("adjunto"):
        src = ROOT / step["adjunto"]
        shutil.copy(src, INBOUND / f"{src.stem}---{uuid.uuid4()}{src.suffix}")
        mime = {".md": "text/markdown", ".pdf": "application/pdf"}.get(src.suffix, "text/plain")
        extract = src.read_text(encoding="utf-8")[:1500] if src.suffix != ".pdf" else ""
        tag = uuid.uuid4().hex[:16]
        block = (
            f'<file name="{src.name}" mime="{mime}">\n\n'
            f'<<<EXTERNAL_UNTRUSTED_CONTENT id="{tag}">>>\nSource: External\n---\n{extract}\n'
            f'<<<END_EXTERNAL_UNTRUSTED_CONTENT id="{tag}">>>\n</file>'
        )
        return f"{message}\n\n{block}" if message else block
    return message


def run_step(step: dict, key: str, n: int) -> dict:
    result: dict = {"paso": step["id"], "modo": step["modo"], "dice": step.get("dice", "")}
    message = step.get("dice", "")
    if step["modo"] == "voz":
        note = voz("decir", f"p{n}", message)
        heard = voz("oir", note["ogg"])
        result.update(nota_s=note["audio_s"], stt_s=heard["stt_s"], oido=heard["texto"])
        result["wer"] = wer(message, heard["texto"])
        message = f'[Audio transcript (machine-generated, untrusted)]: "{heard["texto"]}"'
    message = attach(step, message, n, result)
    compose("exec", "-T", "openclaw", "sh", "-c", "cat > /tmp/ensayo/msg.txt", stdin=message)
    started, t0 = time.time(), time.monotonic()
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
        "/tmp/ensayo/msg.txt",
        "--timeout",
        "900",
        "--json",
        timeout=1100,
    )
    result["agente_s"] = round(time.monotonic() - t0, 1)
    try:
        payloads = json.loads(out[out.find("{") : out.rfind("}") + 1])["result"]["payloads"]
    except (ValueError, KeyError):
        payloads = []
    result["respuesta"] = "\n".join(p.get("text") or "" for p in payloads).strip()
    result["media"] = [m for p in payloads for m in (p.get("mediaUrls") or [])]
    result.update(trajectory(key, started))
    result["pendientes"] = pending()
    if step["modo"] == "voz" and spoken(result["respuesta"]):
        talk = voz("decir", f"r{n}", spoken(result["respuesta"]))
        result.update(tts_s=talk["tts_s"], habla_s=talk["audio_s"])
    result["total_s"] = round(
        result.get("stt_s", 0) + result["agente_s"] + result.get("tts_s", 0), 1
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("guion", help="docs/demo/guion-voz.json o docs/demo/guion-texto.json")
    parser.add_argument("--desde", type=int, default=1, help="primer paso (1 = el primero)")
    parser.add_argument("--hasta", type=int, default=999)
    parser.add_argument("--sesion", default="", help="seguir en una sesión ya empezada")
    args = parser.parse_args()
    guion = json.loads((ROOT / args.guion).read_text(encoding="utf-8"))
    compose("exec", "-T", "openclaw", "mkdir", "-p", "/tmp/ensayo")
    compose("cp", str(ROOT / "scripts" / "_ensayo_voz.py"), "openclaw:/tmp/ensayo/voz.py")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    key = args.sesion or f"agent:main:ensayo-{guion['nombre']}-{stamp}"
    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{guion['nombre']}-{stamp}.json"
    print(f"Sesión {key} → {out_path}", flush=True)
    results = []
    for n, step in enumerate(guion["pasos"], 1):
        if not args.desde <= n <= args.hasta:
            continue
        try:
            result = run_step(step, key, n)
        except Exception as exc:  # noqa: BLE001 - un paso roto no para el ensayo
            result = {"paso": step["id"], "error": str(exc)[:800]}
        results.append(result)
        out_path.write_text(
            json.dumps({"sesion": key, "pasos": results}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        tools = ", ".join(c["tool"].split("__")[-1] for c in result.get("llamadas", []))
        voice = (
            f" · whisper {result['stt_s']} s (WER {result.get('wer', '-')})"
            if "stt_s" in result
            else ""
        )
        print(
            f"[{n:02d} {step['id']}] {result.get('total_s', '-')} s · Jarvis "
            f"{result.get('agente_s', '-')} s{voice}"
            + (f" · hablaría {result['habla_s']} s" if "habla_s" in result else "")
            + f" · {tools or 'sin herramientas'}"
            + (f" · {len(result['media'])} archivo(s)" if result.get("media") else "")
            + (
                f" · pendiente: {', '.join(result['pendientes'])}"
                if result.get("pendientes")
                else ""
            )
            + (f" · ERROR {result['error'][:200]}" if result.get("error") else ""),
            flush=True,
        )
    print(f"Hecho: {out_path}")


if __name__ == "__main__":
    main()
