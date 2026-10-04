"""Voz del ensayo de la demo, dentro del contenedor openclaw (las mismas piezas que usa
OpenClaw con Telegram). Lo copia y lo llama scripts/_ensayo_demo.py.

  decir <nombre>      texto por stdin → Piper (jarvis-tts) → ogg/opus como una nota de voz
  oir <ruta>          ffmpeg a wav 16 kHz → el transcriptor de tools.media.models de la
                      configuración viva (whisper-cli con su idioma y vocabulario)
  reunion <nombre>    guion por stdin, líneas «voz|frase» (voz 0-3) → grabación ogg a 128 kbps,
                      como la de la grabadora de un móvil; cada voz con otro tono
"""

import json
import subprocess
import sys
import time
import wave
from pathlib import Path

DIR = Path("/tmp/ensayo")
TTS = "/home/jarvis/.local/bin/jarvis-tts"
CONFIG = Path("/home/jarvis/.openclaw/openclaw.json")
# Cuatro «personas» con la única voz de Piper: tono y velocidad distintos.
VOICES = {
    "0": "anull",
    "1": "asetrate=22050*0.88,aresample=22050,atempo=1.136",
    "2": "asetrate=22050*1.10,aresample=22050,atempo=0.909",
    "3": "asetrate=22050*1.22,aresample=22050,atempo=0.82",
}


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def say(text: str, wav: Path) -> float:
    t0 = time.monotonic()
    subprocess.run([TTS, str(wav), text], check=True, capture_output=True)
    return time.monotonic() - t0


def main() -> None:
    DIR.mkdir(exist_ok=True)
    mode, arg = sys.argv[1], sys.argv[2]
    if mode == "decir":
        wav, ogg = DIR / f"{arg}.wav", DIR / f"{arg}.ogg"
        tts = say(sys.stdin.read(), wav)
        with wave.open(str(wav)) as w:
            seconds = w.getnframes() / w.getframerate()
        ffmpeg(
            "-i", str(wav), "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "24k", str(ogg)
        )
        print(json.dumps({"tts_s": round(tts, 2), "audio_s": round(seconds, 1), "ogg": str(ogg)}))
    elif mode == "oir":
        t0 = time.monotonic()
        wav = DIR / "stt.wav"
        ffmpeg("-i", arg, "-ac", "1", "-ar", "16000", str(wav))
        entry = json.loads(CONFIG.read_text(encoding="utf-8"))["tools"]["media"]["models"][0]
        args = [
            a.replace("{{AttachmentPath}}", str(wav)).replace("{{MediaPath}}", str(wav))
            for a in entry["args"]
        ]
        out = subprocess.run(
            [entry["command"], *args], capture_output=True, text=True, check=True
        ).stdout
        print(
            json.dumps({"stt_s": round(time.monotonic() - t0, 2), "texto": " ".join(out.split())})
        )
    elif mode == "reunion":
        parts = []
        for n, line in enumerate(x for x in sys.stdin.read().splitlines() if "|" in x):
            voice, text = line.split("|", 1)
            raw, part = DIR / f"reu-{n:02d}-raw.wav", DIR / f"reu-{n:02d}.wav"
            say(text.strip(), raw)
            ffmpeg(
                "-i",
                str(raw),
                "-af",
                f"{VOICES[voice.strip()]},apad=pad_dur=0.6",
                "-ar",
                "22050",
                "-ac",
                "1",
                str(part),
            )
            parts.append(part)
        listing = DIR / "reunion.txt"
        listing.write_text("".join(f"file {p.name}\n" for p in parts), encoding="utf-8")
        ogg = DIR / f"{arg}.ogg"
        ffmpeg(
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
            str(ogg),
        )
        print(json.dumps({"ogg": str(ogg), "bytes": ogg.stat().st_size}))


if __name__ == "__main__":
    main()
