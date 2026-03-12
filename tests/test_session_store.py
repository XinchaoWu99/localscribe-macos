from __future__ import annotations

from pathlib import Path

from localscribe.models import SpeakerProfile, TranscriptResult, TranscriptSegment
from localscribe.storage import SessionStore


def test_session_store_persists_and_loads_sessions(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = store.create("whisperkit-server", session_type="upload", title="demo.wav")
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=2.5,
                text="hello world",
                speaker_name="Speaker 1",
            )
        ],
        speakers=[],
        duration_seconds=2.5,
    )

    store.save_result(session, result, duration_seconds=result.duration_seconds)

    reloaded = SessionStore(tmp_path).get(session.session_id)
    assert reloaded.session_type == "upload"
    assert reloaded.title == "demo.wav"
    assert len(reloaded.segments) == 1
    assert reloaded.segments[0].text == "hello world"


def test_list_recent_returns_most_recent_first(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    older = store.create("engine-a", title="older")
    newer = store.create("engine-b", title="newer")

    sessions = store.list_recent()
    assert sessions[0].session_id == newer.session_id


def test_rename_speaker_updates_existing_segments(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = store.create("whisperkit-server")
    session.speakers["speaker-a"] = SpeakerProfile(speaker_id="speaker-a", label="Speaker 1")
    session.attach_segments(
        [
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=1.0,
                text="hello",
                speaker_id="speaker-a",
                speaker_name="Speaker 1",
            )
        ]
    )
    store.save(session)

    profile, updated = store.rename_speaker(session.session_id, "speaker-a", "Host")

    assert profile.label == "Host"
    assert updated.segments[0].speaker_name == "Host"
    assert SessionStore(tmp_path).get(session.session_id).segments[0].speaker_name == "Host"
