from __future__ import annotations

import io
from pathlib import Path
import wave

from localscribe.models import LiveSession, TranscriptSegment
from localscribe.speakers.resolver import SpeakerResolver


def test_assign_falls_back_when_voiceprint_runtime_fails(tmp_path: Path) -> None:
    resolver = SpeakerResolver(tmp_path / "models", enabled=False, similarity_threshold=0.73)
    resolver.enabled = True
    resolver._import_error = None

    def fail_embedding(_audio_path: Path):
        raise RuntimeError("hf_hub_download() got an unexpected keyword argument 'use_auth_token'")

    resolver._embedding_for_file = fail_embedding  # type: ignore[method-assign]
    session = LiveSession(session_id="live-1")
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(_wav_bytes())
    segments = [
        TranscriptSegment(
            segment_id="seg-1",
            start=0.0,
            end=1.0,
            text="hello world",
            source="live",
        )
    ]

    speakers = resolver.assign(session, audio_path, segments)

    assert len(speakers) == 1
    assert segments[0].speaker_id == "speaker-1"
    assert segments[0].speaker_name == "Speaker 1"
    assert "voiceprint model failed to run" in (resolver.status()["warning"] or "")


def _wav_bytes(sample_rate: int = 16000, duration_ms: int = 1200) -> bytes:
    frame_count = int(sample_rate * duration_ms / 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()
