from __future__ import annotations

import io
from pathlib import Path
import wave

from localscribe.context import ContextRefinementService
from localscribe.config import Settings
from localscribe.diarization.vad import SpeechWindow
from localscribe.models import SpeakerProfile, TranscriptResult, TranscriptSegment
from localscribe.engines.mock import MockEngine
from localscribe.models import TranscriptionOptions
from localscribe.postprocess.service import PostProcessingPlan
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


def _service_with_postprocess(
    tmp_path: Path,
    post_processing_service,
) -> tuple[StreamingService, _StubDiarizationService]:
    settings = Settings(data_dir=tmp_path, chunk_millis=2200)
    diarization_service = _StubDiarizationService()
    return StreamingService(
        settings=settings,
        engine=MockEngine(settings),
        session_store=SessionStore(settings.sessions_dir),
        file_store=FileStore(settings.uploads_dir),
        diarization_service=diarization_service,
        context_refinement_service=ContextRefinementService(enabled=False),
        post_processing_service=post_processing_service,
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


def test_ingest_live_chunk_boosts_very_quiet_audio_before_transcription(tmp_path: Path) -> None:
    service, diarization_service = _service(tmp_path)
    diarization_service.speech_windows = []
    session = service.create_session()

    result, updated_session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=1,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.004),
            options=TranscriptionOptions(live=True, diarize=False),
        ),
    )

    assert result.segments
    assert updated_session.segments
    assert result.warnings[0] == StreamingService.QUIET_INPUT_BOOST_WARNING


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
    assert result.warnings == [
        "Input level is very low. Check the selected microphone or audio source.",
        "No speech detected in the latest audio chunk.",
    ]


def test_live_caption_stays_draft_until_pause_then_finalizes(tmp_path: Path) -> None:
    service, diarization_service = _service(tmp_path)
    service.engine = _SequenceEngine(["hello everyone", "thanks for joining", "today."])
    session = service.create_session()

    diarization_service.speech_windows = [SpeechWindow(start=0.0, end=2.2)]
    first, session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=1,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.08),
            options=TranscriptionOptions(live=True, diarize=False),
        ),
    )
    assert session.segments == []
    assert len(session.draft_segments) == 1
    assert session.draft_segments[0].is_final is False
    assert first.segments[0].text == "hello everyone"

    diarization_service.speech_windows = [SpeechWindow(start=2.2, end=4.4)]
    second, session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=2,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.08),
            options=TranscriptionOptions(live=True, diarize=False, offset_seconds=session.total_audio_seconds),
        ),
    )
    assert session.segments == []
    assert len(session.draft_segments) == 1
    assert "thanks for joining" in session.draft_segments[0].text
    assert second.segments[0].is_final is False

    diarization_service.speech_windows = [SpeechWindow(start=4.4, end=5.6)]
    third, session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=3,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.08),
            options=TranscriptionOptions(live=True, diarize=False, offset_seconds=session.total_audio_seconds),
        ),
    )
    assert len(session.segments) == 1
    assert session.draft_segments == []
    assert session.segments[0].is_final is True
    assert session.segments[0].text.endswith("today.")
    assert third.segments[0].is_final is True


def test_live_caption_finalizes_previous_turn_when_speaker_changes(tmp_path: Path) -> None:
    service, diarization_service = _service(tmp_path)
    service.engine = _SequenceEngine(["first speaker is talking", "second speaker jumps in"])
    session = service.create_session()

    diarization_service.speech_windows = [SpeechWindow(start=0.0, end=2.2)]
    _, session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=1,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.08),
            options=TranscriptionOptions(live=True, diarize=False),
        ),
    )

    service.engine.speaker = SpeakerProfile(speaker_id="speaker-2", label="Speaker 2", enrolled=False, samples=1)
    diarization_service.speech_windows = [SpeechWindow(start=2.2, end=4.4)]
    result, session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=2,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.08),
            options=TranscriptionOptions(live=True, diarize=False, offset_seconds=session.total_audio_seconds),
        ),
    )

    assert len(session.segments) == 1
    assert session.segments[0].speaker_id == "speaker-1"
    assert len(session.draft_segments) == 1
    assert session.draft_segments[0].speaker_id == "speaker-2"
    assert result.segments[-1].is_final is False


def test_manually_edited_live_caption_locks_current_draft_and_continues_in_next_segment(tmp_path: Path) -> None:
    service, diarization_service = _service(tmp_path)
    service.engine = _SequenceEngine(["hello everyone", "thanks for joining"])
    session = service.create_session()

    diarization_service.speech_windows = [SpeechWindow(start=0.0, end=2.2)]
    _, session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=1,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.08),
            options=TranscriptionOptions(live=True, diarize=False),
        ),
    )

    edited_segment_id = session.draft_segments[0].segment_id
    service.update_segment_text(session.session_id, edited_segment_id, "hello everyone, team")

    diarization_service.speech_windows = [SpeechWindow(start=2.2, end=4.4)]
    result, session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=2,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.08),
            options=TranscriptionOptions(live=True, diarize=False, offset_seconds=session.total_audio_seconds),
        ),
    )

    assert len(session.segments) == 1
    assert session.segments[0].text == "hello everyone, team"
    assert session.segments[0].manually_edited is True
    assert len(session.draft_segments) == 1
    assert session.draft_segments[0].text == "thanks for joining"
    assert StreamingService.MANUAL_DRAFT_LOCK_WARNING in result.warnings


def test_live_post_processing_skips_draft_only_updates(tmp_path: Path) -> None:
    class _CountingPostProcessingService:
        def __init__(self) -> None:
            self.calls = 0

        def prepare_backend(self, options):  # noqa: ANN001
            return {}

        def refine_live_result(self, session, result, options, *, replace_tail_count=0):  # noqa: ANN001
            self.calls += 1
            return PostProcessingPlan(result=result, replace_tail_count=replace_tail_count)

    post_processing_service = _CountingPostProcessingService()
    service, diarization_service = _service_with_postprocess(tmp_path, post_processing_service)
    service.engine = _SequenceEngine(["hello everyone"])
    session = service.create_session()

    diarization_service.speech_windows = [SpeechWindow(start=0.0, end=2.2)]
    result, session = service.ingest_live_chunk(
        session.session_id,
        LiveChunkRequest(
            sequence=1,
            mime_type="audio/wav",
            raw_bytes=_wav_bytes(amplitude=0.08),
            options=TranscriptionOptions(live=True, diarize=False, post_process=True),
        ),
    )

    assert post_processing_service.calls == 0
    assert result.segments[0].is_final is False
    assert session.draft_segments


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


class _SequenceEngine(MockEngine):
    def __init__(self, texts: list[str]) -> None:
        super().__init__(Settings())
        self.texts = list(texts)
        self.index = 0
        self.speaker = self._speaker

    def transcribe_live_chunk(self, audio_path: str, options: TranscriptionOptions, session) -> TranscriptResult:
        duration = 2.2
        start = options.offset_seconds
        end = start + duration
        text = self.texts[self.index]
        self.index += 1
        segment = TranscriptSegment(
            segment_id=f"seg-{self.index}",
            start=start,
            end=end,
            text=text,
            confidence=0.9,
            speaker_id=self.speaker.speaker_id,
            speaker_name=self.speaker.label,
            is_final=False,
            source="live",
        )
        return TranscriptResult(
            engine_name=self.name,
            segments=[segment],
            speakers=[self.speaker],
            duration_seconds=duration,
            warnings=[],
        )
