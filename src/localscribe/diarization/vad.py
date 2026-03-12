from __future__ import annotations

from array import array
from dataclasses import dataclass
from pathlib import Path
import wave

from ..config import Settings


@dataclass(slots=True)
class SpeechWindow:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def overlaps(self, start: float, end: float) -> bool:
        return min(self.end, end) > max(self.start, start)

    def shifted(self, offset_seconds: float) -> "SpeechWindow":
        return SpeechWindow(
            start=self.start + offset_seconds,
            end=self.end + offset_seconds,
        )


class SileroVoiceActivityDetector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.enable_vad
        self._import_error: str | None = None
        self._model = None

        if not self.enabled:
            self._import_error = "Silero VAD is disabled."
            return

        try:
            import torch
            from silero_vad import get_speech_timestamps, load_silero_vad
        except Exception as exc:  # pragma: no cover - optional dependency path
            self._import_error = str(exc)
            return

        self._torch = torch
        self._get_speech_timestamps = get_speech_timestamps
        self._load_silero_vad = load_silero_vad

    @property
    def ready(self) -> bool:
        return self.enabled and self._import_error is None

    def status(self) -> dict[str, object]:
        status: dict[str, object] = {
            "enabled": self.enabled,
            "ready": self.ready,
            "backend": "silero-vad",
            "threshold": self.settings.vad_threshold,
            "minSpeechMs": self.settings.vad_min_speech_ms,
            "minSilenceMs": self.settings.vad_min_silence_ms,
            "speechPadMs": self.settings.vad_speech_pad_ms,
            "maxSpeechSeconds": self.settings.vad_max_speech_seconds,
        }
        if self._import_error is not None:
            status["warning"] = self._import_error
        return status

    def detect(self, audio_path: Path, offset_seconds: float = 0.0) -> list[SpeechWindow] | None:
        if not self.enabled:
            return None
        if self._import_error is not None:
            return None

        samples, sampling_rate = self._load_audio(audio_path)
        if samples.numel() == 0:
            return []

        timestamps = self._get_speech_timestamps(
            samples,
            self._get_model(),
            sampling_rate=sampling_rate,
            threshold=self.settings.vad_threshold,
            min_speech_duration_ms=self.settings.vad_min_speech_ms,
            min_silence_duration_ms=self.settings.vad_min_silence_ms,
            speech_pad_ms=self.settings.vad_speech_pad_ms,
            max_speech_duration_s=self.settings.vad_max_speech_seconds,
            return_seconds=True,
        )
        windows = [
            SpeechWindow(
                start=float(item["start"]) + offset_seconds,
                end=float(item["end"]) + offset_seconds,
            )
            for item in timestamps
        ]
        return _merge_windows(windows)

    def _get_model(self):
        if self._import_error is not None:
            raise RuntimeError(self._import_error)
        if self._model is None:  # pragma: no cover - optional dependency path
            self._model = self._load_silero_vad()
        return self._model

    def _load_audio(self, audio_path: Path):
        with wave.open(str(audio_path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sampling_rate = handle.getframerate()
            frame_count = handle.getnframes()
            raw = handle.readframes(frame_count)

        if channels != 1:
            raise RuntimeError(f"Silero VAD expects mono WAV input, got {channels} channels in {audio_path}.")
        if sample_width != 2:
            raise RuntimeError(f"Silero VAD expects 16-bit PCM WAV input, got {sample_width * 8}-bit audio.")

        pcm = array("h")
        pcm.frombytes(raw)
        samples = self._torch.tensor(pcm, dtype=self._torch.float32) / 32768.0
        return samples, sampling_rate


def _merge_windows(windows: list[SpeechWindow]) -> list[SpeechWindow]:
    ordered = sorted(windows, key=lambda item: (item.start, item.end))
    if not ordered:
        return []

    merged: list[SpeechWindow] = [ordered[0]]
    for window in ordered[1:]:
        current = merged[-1]
        if window.start <= current.end:
            current.end = max(current.end, window.end)
            continue
        merged.append(window)
    return merged
