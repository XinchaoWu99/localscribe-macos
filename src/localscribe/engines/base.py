from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import Settings
from ..models import LiveSession, SpeakerProfile, TranscriptionOptions, TranscriptResult


class TranscriptionEngine(ABC):
    name = "base"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> dict[str, object]:
        return {
            "engine": self.name,
            "ready": True,
            "supportsLive": True,
            "supportsDiarization": False,
            "supportsEnrollment": False,
            "warnings": [],
        }

    def startup(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    @abstractmethod
    def transcribe_file(self, audio_path: str, options: TranscriptionOptions) -> TranscriptResult:
        raise NotImplementedError

    @abstractmethod
    def transcribe_live_chunk(
        self,
        audio_path: str,
        options: TranscriptionOptions,
        session: LiveSession,
    ) -> TranscriptResult:
        raise NotImplementedError

    def enroll_speaker(self, audio_path: str, label: str, session: LiveSession) -> SpeakerProfile:
        raise RuntimeError(f"{self.name} does not support speaker enrollment.")
