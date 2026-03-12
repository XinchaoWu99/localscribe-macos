from __future__ import annotations

from pathlib import Path

from localscribe.models import SegmentWord, SpeakerProfile, TranscriptResult, TranscriptSegment
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


def test_rename_session_persists_title(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = store.create("whisperkit-server")

    updated = store.rename_session(session.session_id, "Weekly product sync")

    assert updated.title == "Weekly product sync"
    assert SessionStore(tmp_path).get(session.session_id).title == "Weekly product sync"


def test_update_segment_text_clears_word_alignment_and_persists(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = store.create("whisperkit-server")
    session.attach_segments(
        [
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=1.0,
                text="hello world",
            )
        ]
    )
    session.segments[0].words.append(SegmentWord(start=0.0, end=0.5, text="hello"))
    store.save(session)

    segment, updated = store.update_segment_text(session.session_id, "seg-1", "hello, world.")

    assert segment.text == "hello, world."
    assert segment.words == []
    assert segment.manually_edited is True
    assert segment.edited_at is not None
    assert updated.segments[0].text == "hello, world."
    assert updated.segments[0].manually_edited is True
    assert SessionStore(tmp_path).get(session.session_id).segments[0].text == "hello, world."


def test_apply_live_result_refuses_to_replace_manually_edited_tail(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = store.create("whisperkit-server")
    session.attach_segments(
        [
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=1.0,
                text="hello world",
                manually_edited=True,
                edited_at="2026-03-12T00:00:00+00:00",
            )
        ]
    )
    store.save(session)
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=2.0,
                text="hello world again",
            )
        ],
        speakers=[],
        duration_seconds=1.0,
    )

    try:
        store.apply_live_result(session, 1, 1.0, result, replace_tail_count=1)
    except RuntimeError as exc:
        assert "manually edited" in str(exc)
    else:
        raise AssertionError("Expected replacing a manually edited live segment to fail.")


def test_clear_live_sessions_keeps_uploads(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    live_session = store.create("whisperkit-server", session_type="live", title="live")
    upload_session = store.create("whisperkit-server", session_type="upload", title="upload")

    deleted = store.clear(session_type="live")

    assert deleted == 1
    assert not store.session_dir(live_session.session_id).exists()
    assert store.session_dir(upload_session.session_id).exists()
