from __future__ import annotations

from pathlib import Path
import threading
from uuid import uuid4

import httpx

from ..audio import probe_duration_seconds
from ..config import Settings
from ..models import SegmentWord, TranscriptSegment, TranscriptionOptions, TranscriptResult
from .base import TranscriptionEngine
from .whisperkit_runtime import WhisperKitRuntime


class WhisperKitServerEngine(TranscriptionEngine):
    name = "whisperkit-server"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.base_url = settings.whisper_server_url.rstrip("/")
        self._lock = threading.RLock()
        self.runtime = WhisperKitRuntime(settings)

    @classmethod
    def is_available(cls, settings: Settings) -> bool:
        runtime = WhisperKitRuntime(settings)
        return runtime.can_manage() or runtime.is_ready()

    def startup(self) -> None:
        self.runtime.startup()

    def shutdown(self) -> None:
        self.runtime.shutdown()

    def status(self) -> dict[str, object]:
        runtime_status = self.runtime.status()
        warnings: list[str] = []
        warning = runtime_status.get("warning")
        if isinstance(warning, str) and warning:
            warnings.append(warning)
        return {
            **super().status(),
            "engine": self.name,
            "ready": bool(runtime_status.get("ready", False)),
            "supportsDiarization": True,
            "supportsEnrollment": True,
            "supportsModelManagement": True,
            "currentModel": self.settings.whisper_model,
            "runtime": runtime_status,
            "warnings": warnings,
        }

    def model_catalog(self) -> dict[str, object]:
        return self.runtime.model_catalog()

    def install_model(self, model_id: str) -> dict[str, object]:
        return self.runtime.install_model(model_id)

    def select_model(self, model_id: str) -> dict[str, object]:
        with self._lock:
            return self.runtime.select_model(model_id)

    def transcribe_file(self, audio_path: str, options: TranscriptionOptions) -> TranscriptResult:
        duration = probe_duration_seconds(Path(audio_path))
        payload = self._transcribe(Path(audio_path), options)
        segments = self._segments_from_payload(payload, options.offset_seconds, "file", clip_duration_seconds=duration)
        return TranscriptResult(
            engine_name=self.name,
            segments=segments,
            speakers=[],
            duration_seconds=duration,
            detected_language=payload.get("language"),
            warnings=[],
        )

    def transcribe_live_chunk(self, audio_path: str, options: TranscriptionOptions, session) -> TranscriptResult:
        duration = probe_duration_seconds(Path(audio_path))
        payload = self._transcribe(Path(audio_path), options)
        segments = self._segments_from_payload(payload, options.offset_seconds, "live", clip_duration_seconds=duration)
        return TranscriptResult(
            engine_name=self.name,
            segments=segments,
            speakers=[],
            duration_seconds=duration,
            detected_language=payload.get("language"),
            warnings=[],
        )

    def _transcribe(self, audio_path: Path, options: TranscriptionOptions) -> dict[str, object]:
        with self._lock:
            self.runtime.ensure_running()
            multipart_fields: list[tuple[str, tuple[str | None, object, str | None] | tuple[None, str]]] = [
                ("model", (None, self.runtime.request_model_name())),
                ("response_format", (None, "verbose_json")),
                ("temperature", (None, "0")),
                ("timestamp_granularities[]", (None, "segment")),
                ("timestamp_granularities[]", (None, "word")),
            ]
            if options.language:
                multipart_fields.append(("language", (None, options.language)))
            if options.prompt:
                multipart_fields.append(("prompt", (None, options.prompt)))

            with audio_path.open("rb") as handle:
                multipart_fields.append(("file", (audio_path.name, handle, "audio/wav")))
                with httpx.Client(timeout=httpx.Timeout(120.0)) as client:
                    response = client.post(f"{self.base_url}/audio/transcriptions", files=multipart_fields)
                    response.raise_for_status()
                    return response.json()

    def _segments_from_payload(
        self,
        payload: dict[str, object],
        offset_seconds: float,
        source: str,
        clip_duration_seconds: float | None = None,
    ) -> list[TranscriptSegment]:
        raw_segments = payload.get("segments")
        if not isinstance(raw_segments, list):
            text = str(payload.get("text", "")).strip()
            if not text:
                return []
            return [
                TranscriptSegment(
                    segment_id=uuid4().hex,
                    start=offset_seconds,
                    end=offset_seconds,
                    text=text,
                    source=source,
                )
            ]

        segments: list[TranscriptSegment] = []
        for entry in raw_segments:
            if not isinstance(entry, dict):
                continue
            segment_start, segment_end = _normalize_time_range(
                entry.get("start", 0.0),
                entry.get("end", 0.0),
                clip_duration_seconds,
            )
            words = []
            raw_words = entry.get("words")
            if isinstance(raw_words, list):
                for raw_word in raw_words:
                    if not isinstance(raw_word, dict):
                        continue
                    word_start, word_end = _normalize_time_range(
                        raw_word.get("start", 0.0),
                        raw_word.get("end", 0.0),
                        clip_duration_seconds,
                    )
                    words.append(
                        SegmentWord(
                            start=word_start + offset_seconds,
                            end=word_end + offset_seconds,
                            text=str(raw_word.get("word", "")).strip(),
                            confidence=_maybe_float(raw_word.get("probability")),
                        )
                    )

            segments.append(
                TranscriptSegment(
                    segment_id=uuid4().hex,
                    start=segment_start + offset_seconds,
                    end=segment_end + offset_seconds,
                    text=str(entry.get("text", "")).strip(),
                    confidence=_maybe_float(entry.get("avg_logprob")),
                    source=source,
                    words=words,
                )
            )
        return [segment for segment in segments if segment.text]


def _maybe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_time_range(start_value, end_value, clip_duration_seconds: float | None) -> tuple[float, float]:
    start = max(0.0, _maybe_float(start_value) or 0.0)
    end = max(start, _maybe_float(end_value) or start)
    if clip_duration_seconds is None:
        return start, end

    clip_duration = max(0.0, float(clip_duration_seconds))
    if end <= clip_duration and start <= clip_duration:
        return start, end

    span = max(0.0, end - start)
    if span >= clip_duration:
        return 0.0, clip_duration

    end = min(end, clip_duration)
    start = min(start, end)
    if end - start < span:
        start = max(0.0, end - span)
    return start, end
