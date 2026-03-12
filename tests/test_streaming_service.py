from __future__ import annotations

import io
from pathlib import Path
import wave

from localscribe.context import ContextRefinementService
from localscribe.config import Settings
from localscribe.engines.mock import MockEngine
from localscribe.models import TranscriptionOptions
from localscribe.storage import FileStore, SessionStore
from localscribe.streaming import LiveChunkRequest, StreamingService


class _StubDiarizationService:
    def __init__(self) -> None:
        self.speech_windows = None

    def detect_speech(self, audio_path, offset_seconds: float = 0.0):
        return self.speech_windows

    def process_live_result(self, session, normalized_path, result, options, speech_windows=None):
        return result

    def process_file_result(self, normalized_path, result, options, speech_windows=None):
        return result


def _service(tmp_path: Path) -> tuple[StreamingService, _StubDiarizationService]:
    settings = Settings(data_dir=tmp_path, chunk_millis=2200)
    diarization_service = _StubDiarizationService()
    return StreamingService(
        settings=settings,
        engine=MockEngine(settings),
        session_store=SessionStore(settings.sessions_dir),
        file_store=FileStore(settings.uploads_dir),
        diarization_service=diarization_service,
        context_refinement_service=ContextRefinementService(enabled=False),
    ), diarization_service


def test_update_live_settings_clamps_chunk_millis(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    minimum = service.update_live_settings(chunk_millis=50)
    maximum = service.update_live_settings(chunk_millis=25000)

    assert minimum["chunkMillis"] == service.MIN_CHUNK_MILLIS
    assert maximum["chunkMillis"] == service.MAX_CHUNK_MILLIS


def test_status_reports_live_chunk_bounds(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    status = service.status()

    assert status["chunkMillis"] == 2200
    assert status["minChunkMillis"] == service.MIN_CHUNK_MILLIS
    assert status["maxChunkMillis"] == service.MAX_CHUNK_MILLIS
    assert status["liveVadFallbackEnabled"] is True


def test_ingest_live_chunk_bypasses_vad_for_low_level_speechy_audio(tmp_path: Path) -> None:
    service, diarization_service = _service(tmp_path)
    diarization_service.speech_windows = []
    session = service.create_session()

    result, updated_session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=1,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.08),
            options=TranscriptionOptions(live=True, diarize=False),
        ),
    )

    assert result.segments
    assert updated_session.segments
    assert "fallback" in " ".join(result.warnings).lower()


def test_ingest_live_chunk_keeps_silence_empty_when_vad_rejects_it(tmp_path: Path) -> None:
    service, diarization_service = _service(tmp_path)
    diarization_service.speech_windows = []
    session = service.create_session()

    result, updated_session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=1,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.0),
            options=TranscriptionOptions(live=True, diarize=False),
        ),
    )

    assert result.segments == []
    assert updated_session.segments == []
    assert result.warnings == ["No speech detected in the latest audio chunk."]


def _wav_bytes(*, amplitude: float, frequency_hz: float = 440.0, sample_rate: int = 16000, duration_ms: int = 2200) -> bytes:
    import math

    frame_count = int(sample_rate * duration_ms / 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        samples = bytearray()
        for index in range(frame_count):
            value = amplitude * math.sin(2 * math.pi * frequency_hz * (index / sample_rate))
            clamped = max(-1.0, min(1.0, value))
            samples.extend(int(clamped * 32767).to_bytes(2, "little", signed=True))
        handle.writeframes(bytes(samples))
    return buffer.getvalue()
