from __future__ import annotations

from ..config import Settings
from .base import TranscriptionEngine
from .faster_whisper import FasterWhisperEngine
from .mock import MockEngine
from .whisperkit import WhisperKitServerEngine


def build_engine(settings: Settings) -> TranscriptionEngine:
    requested = settings.engine.strip().lower()
    if requested in {"auto", ""}:
        if WhisperKitServerEngine.is_available(settings):
            return WhisperKitServerEngine(settings)
        if FasterWhisperEngine.is_available():
            return FasterWhisperEngine(settings)
        return MockEngine(settings)
    if requested in {"faster-whisper", "faster", "local-whisper"}:
        return FasterWhisperEngine(settings)
    if requested in {"whisperkit", "whisperkit-server", "openai-local"}:
        return WhisperKitServerEngine(settings)
    return MockEngine(settings)
