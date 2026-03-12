from __future__ import annotations

from localscribe.exports import build_session_export
from localscribe.models import LiveSession, TranscriptSegment


def _session() -> LiveSession:
    return LiveSession(
        session_id="abc12345def67890",
        session_type="upload",
        title="demo meeting.wav",
        total_audio_seconds=12.5,
        segments=[
            TranscriptSegment(
                segment_id="seg-1",
                start=0.5,
                end=3.0,
                text="hello world",
                speaker_name="Alice",
            )
        ],
    )


def test_srt_export_contains_subtitle_blocks() -> None:
    exported = build_session_export(_session(), "srt")
    assert exported.filename.endswith(".srt")
    assert "1\n00:00:00,500 --> 00:00:03,000\nAlice: hello world" in exported.content


def test_json_export_contains_session_metadata() -> None:
    exported = build_session_export(_session(), "json")
    assert exported.media_type == "application/json"
    assert '"sessionType": "upload"' in exported.content
    assert '"title": "demo meeting.wav"' in exported.content
