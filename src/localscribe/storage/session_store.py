from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from ..models import LiveSession, TranscriptResult, TranscriptSegment, utcnow_iso

_SESSION_FILE = "session.json"


class SessionStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, LiveSession] = {}

    def create(self, engine_name: str, session_type: str = "live", title: str | None = None) -> LiveSession:
        session_id = uuid4().hex
        session = LiveSession(
            session_id=session_id,
            engine_name=engine_name,
            session_type=session_type,
            title=title,
        )
        self._sessions[session_id] = session
        self.session_dir(session_id).mkdir(parents=True, exist_ok=True)
        self.save(session)
        return session

    def get(self, session_id: str) -> LiveSession:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing

        session_path = self.session_file(session_id)
        if not session_path.exists():
            raise KeyError(f"Unknown session: {session_id}")

        session = LiveSession.from_payload(json.loads(session_path.read_text(encoding="utf-8")))
        self._sessions[session_id] = session
        return session

    def list_recent(self, limit: int = 20) -> list[LiveSession]:
        sessions: list[LiveSession] = []
        for session_path in sorted(self.base_dir.glob(f"*/{_SESSION_FILE}")):
            try:
                session_id = session_path.parent.name
                session = self._sessions.get(session_id)
                if session is None:
                    session = LiveSession.from_payload(json.loads(session_path.read_text(encoding="utf-8")))
                    self._sessions[session_id] = session
                sessions.append(session)
            except Exception:
                continue

        sessions.sort(key=lambda item: (item.updated_at, item.created_at, item.session_id), reverse=True)
        return sessions[:limit]

    def session_dir(self, session_id: str) -> Path:
        return self.base_dir / session_id

    def session_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / _SESSION_FILE

    def chunk_path(self, session_id: str, sequence: int, suffix: str) -> Path:
        return self.session_dir(session_id) / "chunks" / f"{sequence:05d}{suffix}"

    def save(self, session: LiveSession) -> LiveSession:
        session.updated_at = utcnow_iso()
        session_path = self.session_file(session.session_id)
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(json.dumps(session.to_payload(), indent=2), encoding="utf-8")
        self._sessions[session.session_id] = session
        return session

    def save_result(
        self,
        session: LiveSession,
        result: TranscriptResult,
        duration_seconds: float | None = None,
    ) -> LiveSession:
        if duration_seconds is not None:
            session.total_audio_seconds = duration_seconds
        session.engine_name = result.engine_name
        session.attach_segments(result.segments)
        session.merge_speakers(result.speakers)
        session.warnings = _merge_warnings(session.warnings, result.warnings)
        return self.save(session)

    def apply_live_result(
        self,
        session: LiveSession,
        sequence: int,
        duration_seconds: float,
        result: TranscriptResult,
        draft_segments: list[TranscriptSegment] | None = None,
        replace_tail_count: int = 0,
        replacement_segments: list[TranscriptSegment] | None = None,
    ) -> LiveSession:
        session.chunk_count = max(session.chunk_count, sequence)
        session.total_audio_seconds += duration_seconds
        session.engine_name = result.engine_name
        if replace_tail_count > 0:
            tail_segments = session.segments[-replace_tail_count:]
            if any(segment.manually_edited for segment in tail_segments):
                raise RuntimeError("Cannot replace manually edited live transcript segments.")
            session.segments = session.segments[:-replace_tail_count]
        session.attach_segments(result.segments if replacement_segments is None else replacement_segments)
        session.replace_draft_segments(draft_segments or [])
        session.merge_speakers(result.speakers)
        session.warnings = _merge_warnings(session.warnings, result.warnings)
        return self.save(session)

    def rename_speaker(self, session_id: str, speaker_id: str, label: str):
        session = self.get(session_id)
        profile = session.rename_speaker(speaker_id, label)
        self.save(session)
        return profile, session

    def rename_session(self, session_id: str, title: str | None):
        session = self.get(session_id)
        session.rename(title)
        self.save(session)
        return session

    def update_segment_text(self, session_id: str, segment_id: str, text: str):
        session = self.get(session_id)
        segment = session.update_segment_text(segment_id, text)
        self.save(session)
        return segment, session

    def clear(self, *, session_type: str | None = None, exclude_session_id: str | None = None) -> int:
        deleted = 0
        for session in list(self.list_recent(limit=10000)):
            if session_type and session.session_type != session_type:
                continue
            if exclude_session_id and session.session_id == exclude_session_id:
                continue
            session_dir = self.session_dir(session.session_id)
            if session_dir.exists():
                shutil.rmtree(session_dir)
            self._sessions.pop(session.session_id, None)
            deleted += 1
        return deleted


def _merge_warnings(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    for warning in incoming:
        if warning not in merged:
            merged.append(warning)
    return merged
