"""Transcripción de reuniones largas con faster-whisper (CTranslate2).

En GPU (`device="auto"` y CUDA disponible) usa `int8_float16` y el pipeline por lotes:
una hora de audio tarda un par de minutos y ocupa ~2 GB de VRAM junto al modelo de
Ollama. Sin GPU, o si la GPU no tiene memoria libre, transcribe en CPU en `int8`. El
modelo se descarga la primera vez en `<models_dir>/whisper` y se libera al terminar para
devolver la VRAM.

faster-whisper decodifica el audio con PyAV: vale cualquier formato habitual (ogg/opus de
Telegram, m4a, mp3, wav, webm de la grabadora de Obsidian...).
"""

import gc
from dataclasses import dataclass
from pathlib import Path

from packages.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class Transcript:
    language: str
    duration_seconds: float
    segments: list[Segment]

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments).strip()

    def with_timestamps(self) -> str:
        """Texto con marca [hh:mm:ss] cada párrafo de ~1 minuto, para el anexo del acta."""
        lines: list[str] = []
        paragraph: list[str] = []
        paragraph_start = 0.0
        for segment in self.segments:
            if not paragraph:
                paragraph_start = segment.start
            paragraph.append(segment.text)
            if segment.end - paragraph_start >= 60:
                lines.append(f"[{format_timestamp(paragraph_start)}] {' '.join(paragraph)}")
                paragraph = []
        if paragraph:
            lines.append(f"[{format_timestamp(paragraph_start)}] {' '.join(paragraph)}")
        return "\n\n".join(lines)


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


# Lo que whisper confunde si no se lo enseñan («pemboquet» por PMBOK, «Aplecitas» por App
# de citas): va como contexto previo (initial_prompt) junto a STT_VOCABULARY.
BASE_VOCABULARY = (
    "Jarvis, OpenProject, Obsidian, Telegram, PMBOK, PMI, Scrum, Kanban, Gantt, sprint, hito, "
    "Excel, Word, PowerPoint, PDF"
)


def vocabulary_prompt(extra: str = "") -> str:
    return ", ".join(x for x in (BASE_VOCABULARY, extra.strip(" ,")) if x) + "."


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001 - sin CUDA o sin drivers: se usa CPU
        return False


def _transcribe_on(
    device_name: str,
    audio_path: Path,
    model_name: str,
    models_dir: Path,
    language: str | None,
    vocabulary: str,
) -> Transcript:
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    use_cuda = device_name == "cuda"
    compute_type = "int8_float16" if use_cuda else "int8"
    logger.info("meeting_transcribe_start", model=model_name, device=device_name)
    model = WhisperModel(
        model_name,
        device=device_name,
        compute_type=compute_type,
        download_root=str(models_dir / "whisper"),
    )
    try:
        pipeline = BatchedInferencePipeline(model)
        segments, info = pipeline.transcribe(
            str(audio_path),
            language=language or None,
            initial_prompt=vocabulary_prompt(vocabulary),
            batch_size=8 if use_cuda else 4,
            vad_filter=True,
        )
        result = [
            Segment(start=s.start, end=s.end, text=s.text.strip())
            for s in segments
            if s.text.strip()
        ]
        return Transcript(language=info.language, duration_seconds=info.duration, segments=result)
    finally:
        # Devolver la VRAM antes de que el modelo de Ollama redacte el acta.
        del model
        gc.collect()


def transcribe(
    audio_path: Path,
    *,
    model_name: str,
    models_dir: Path,
    device: str = "auto",
    language: str | None = "es",
    vocabulary: str = "",
) -> Transcript:
    use_cuda = device == "cuda" or (device == "auto" and _cuda_available())
    try:
        transcript = _transcribe_on(
            "cuda" if use_cuda else "cpu", audio_path, model_name, models_dir, language, vocabulary
        )
    except RuntimeError as exc:
        # En la L4, Gemma con 64k de contexto y el modelo de embeddings ocupan ~20,7 GB de
        # 23: el whisper de las actas (~1,5 GB) cabe con poco margen. Si un día no cabe,
        # mejor un acta lenta en CPU que ninguna (docs/MODELS.md, «Presupuesto de VRAM»).
        if not use_cuda or "out of memory" not in str(exc).lower():
            raise
        logger.warning("meeting_transcribe_gpu_oom", error=str(exc)[:200])
        gc.collect()
        transcript = _transcribe_on("cpu", audio_path, model_name, models_dir, language, vocabulary)
    logger.info(
        "meeting_transcribe_done",
        seconds=round(transcript.duration_seconds),
        segments=len(transcript.segments),
    )
    return transcript
