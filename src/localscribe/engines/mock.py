from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..audio import probe_duration_seconds
from ..config import Settings
from ..models import SpeakerProfile, TranscriptSegment, TranscriptionOptions, TranscriptResult
from .base import TranscriptionEngine


class MockEngine(TranscriptionEngine):
    name = "mock"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._speaker = SpeakerProfile(speaker_id="speaker-1", label="Speaker 1", enrolled=False, samples=1)

    def status(self) -> dict[str, object]:
        return {
            **super().status(),
            "engine": self.name,
            "supportsDiarization": True,
            "warnings": [
                "Mock mode is active. Install runtime dependencies and point the app at a local WhisperKit server to enable real transcription.",
            ],
        }

    def transcribe_file(self, audio_path: str, options: TranscriptionOptions) -> TranscriptResult:
        duration = max(probe_duration_seconds(Path(audio_path)), 1.0)
        midpoint = max(duration / 2.0, 0.5)
        segments = [
            TranscriptSegment(
                segment_id=uuid4().hex,
                start=0.0,
                end=min(midpoint, duration),
                text="Mock transcript preview. This UI is ready for a local Whisper engine.",
                confidence=0.51,
                speaker_id=self._speaker.speaker_id,
                speaker_name=self._speaker.label,
            ),
            TranscriptSegment(
                segment_id=uuid4().hex,
                start=min(midpoint, duration),
                end=duration,
                text="Switch LOCALSCRIBE_ENGINE to whisperkit once a local OpenAI-compatible server is running.",
                confidence=0.48,
                speaker_id=self._speaker.speaker_id,
                speaker_name=self._speaker.label,
            ),
        ]
        return TranscriptResult(
            engine_name=self.name,
            segments=segments,
            speakers=[self._speaker],
            duration_seconds=duration,
            warnings=self.status()["warnings"],
        )

    def transcribe_live_chunk(self, audio_path: str, options: TranscriptionOptions, session) -> TranscriptResult:
        duration = max(probe_duration_seconds(Path(audio_path)), 0.1)
        start = options.offset_seconds
        end = start + duration
        sequence = session.chunk_count + 1
        segment = TranscriptSegment(
            segment_id=uuid4().hex,
            start=start,
            end=end,
            text=f"Chunk {sequence} captured in mock mode. Replace the engine to get real-time transcription.",
            confidence=0.42,
            speaker_id=self._speaker.speaker_id,
            speaker_name=self._speaker.label,
            source="live",
        )
        return TranscriptResult(
            engine_name=self.name,
            segments=[segment],
            speakers=[self._speaker],
            duration_seconds=duration,
            warnings=self.status()["warnings"],
        )
