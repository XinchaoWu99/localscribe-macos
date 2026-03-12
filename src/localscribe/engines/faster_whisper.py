from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..audio import probe_duration_seconds
from ..models import SegmentWord, TranscriptSegment, TranscriptionOptions, TranscriptResult
from .base import TranscriptionEngine


class FasterWhisperEngine(TranscriptionEngine):
    name = "faster-whisper"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # pragma: no cover - import failure path
            raise RuntimeError(
                "faster-whisper is not installed. Run `uv sync` in /Users/xwu/Downloads/codex/localscribe."
            ) from exc
        self._WhisperModel = WhisperModel
        self._model = None

    @classmethod
    def is_available(cls) -> bool:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except Exception:
            return False
        return True

    def status(self) -> dict[str, object]:
        return {
            **super().status(),
            "engine": self.name,
            "supportsDiarization": True,
            "supportsEnrollment": True,
            "warnings": [
                f"Running local faster-whisper with model '{self.settings.faster_whisper_model}'."
            ],
        }

    def transcribe_file(self, audio_path: str, options: TranscriptionOptions) -> TranscriptResult:
        duration = max(probe_duration_seconds(Path(audio_path)), 0.1)
        segments, info = self._transcribe(audio_path, options)
        return TranscriptResult(
            engine_name=self.name,
            segments=self._segments_from_items(segments, options.offset_seconds, "file"),
            speakers=[],
            duration_seconds=duration,
            detected_language=getattr(info, "language", None),
            warnings=[],
        )

    def transcribe_live_chunk(self, audio_path: str, options: TranscriptionOptions, session) -> TranscriptResult:
        duration = max(probe_duration_seconds(Path(audio_path)), 0.1)
        segments, info = self._transcribe(audio_path, options)
        return TranscriptResult(
            engine_name=self.name,
            segments=self._segments_from_items(segments, options.offset_seconds, "live"),
            speakers=[],
            duration_seconds=duration,
            detected_language=getattr(info, "language", None),
            warnings=[],
        )

    def _get_model(self):
        if self._model is None:
            self._model = self._WhisperModel(
                self.settings.faster_whisper_model,
                device="cpu",
                compute_type=self.settings.faster_whisper_compute_type,
                cpu_threads=self.settings.faster_whisper_cpu_threads,
            )
        return self._model

    def _transcribe(self, audio_path: str, options: TranscriptionOptions):
        model = self._get_model()
        kwargs: dict[str, object] = {
            "vad_filter": False,
            "word_timestamps": not options.live,
            "condition_on_previous_text": False,
        }
        if options.language:
            kwargs["language"] = options.language
        if options.prompt:
            kwargs["initial_prompt"] = options.prompt
        return model.transcribe(audio_path, **kwargs)

    def _segments_from_items(self, items, offset_seconds: float, source: str) -> list[TranscriptSegment]:
        results: list[TranscriptSegment] = []
        for item in items:
            words = []
            for raw_word in getattr(item, "words", []) or []:
                words.append(
                    SegmentWord(
                        start=float(getattr(raw_word, "start", 0.0)) + offset_seconds,
                        end=float(getattr(raw_word, "end", 0.0)) + offset_seconds,
                        text=str(getattr(raw_word, "word", "")).strip(),
                        confidence=_maybe_float(getattr(raw_word, "probability", None)),
                    )
                )

            segment = TranscriptSegment(
                segment_id=uuid4().hex,
                start=float(getattr(item, "start", 0.0)) + offset_seconds,
                end=float(getattr(item, "end", 0.0)) + offset_seconds,
                text=str(getattr(item, "text", "")).strip(),
                confidence=_maybe_float(getattr(item, "avg_logprob", None)),
                source=source,
                words=words,
            )
            if segment.text:
                results.append(segment)
        return results


def _maybe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
