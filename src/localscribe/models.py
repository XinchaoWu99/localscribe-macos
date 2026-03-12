from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SegmentWord:
    start: float
    end: float
    text: str
    confidence: float | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
        }
        if self.confidence is not None:
            payload["confidence"] = round(self.confidence, 4)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "SegmentWord":
        return cls(
            start=float(payload.get("start", 0.0)),
            end=float(payload.get("end", 0.0)),
            text=str(payload.get("text", "")).strip(),
            confidence=_maybe_float(payload.get("confidence")),
        )


@dataclass(slots=True)
class TranscriptSegment:
    segment_id: str
    start: float
    end: float
    text: str
    confidence: float | None = None
    speaker_id: str | None = None
    speaker_name: str | None = None
    is_final: bool = True
    source: str = "file"
    manually_edited: bool = False
    edited_at: str | None = None
    words: list[SegmentWord] = field(default_factory=list)

    def shifted(self, offset_seconds: float) -> "TranscriptSegment":
        return TranscriptSegment(
            segment_id=self.segment_id,
            start=self.start + offset_seconds,
            end=self.end + offset_seconds,
            text=self.text,
            confidence=self.confidence,
            speaker_id=self.speaker_id,
            speaker_name=self.speaker_name,
            is_final=self.is_final,
            source=self.source,
            manually_edited=self.manually_edited,
            edited_at=self.edited_at,
            words=[
                SegmentWord(
                    start=word.start + offset_seconds,
                    end=word.end + offset_seconds,
                    text=word.text,
                    confidence=word.confidence,
                )
                for word in self.words
            ],
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "segmentId": self.segment_id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "isFinal": self.is_final,
            "source": self.source,
            "manuallyEdited": self.manually_edited,
            "words": [word.to_payload() for word in self.words],
        }
        if self.confidence is not None:
            payload["confidence"] = round(self.confidence, 4)
        if self.speaker_id is not None:
            payload["speakerId"] = self.speaker_id
        if self.speaker_name is not None:
            payload["speakerName"] = self.speaker_name
        if self.edited_at is not None:
            payload["editedAt"] = self.edited_at
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "TranscriptSegment":
        raw_words = payload.get("words")
        words = []
        if isinstance(raw_words, list):
            for entry in raw_words:
                if isinstance(entry, dict):
                    words.append(SegmentWord.from_payload(entry))

        return cls(
            segment_id=str(payload.get("segmentId", "")),
            start=float(payload.get("start", 0.0)),
            end=float(payload.get("end", 0.0)),
            text=str(payload.get("text", "")).strip(),
            confidence=_maybe_float(payload.get("confidence")),
            speaker_id=_maybe_str(payload.get("speakerId")),
            speaker_name=_maybe_str(payload.get("speakerName")),
            is_final=bool(payload.get("isFinal", True)),
            source=str(payload.get("source", "file")),
            manually_edited=bool(payload.get("manuallyEdited", False)),
            edited_at=_maybe_str(payload.get("editedAt")),
            words=words,
        )


@dataclass(slots=True)
class SpeakerProfile:
    speaker_id: str
    label: str
    enrolled: bool = False
    samples: int = 0
    similarity: float | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "speakerId": self.speaker_id,
            "label": self.label,
            "enrolled": self.enrolled,
            "samples": self.samples,
        }
        if self.similarity is not None:
            payload["similarity"] = round(self.similarity, 4)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "SpeakerProfile":
        return cls(
            speaker_id=str(payload.get("speakerId", "")),
            label=str(payload.get("label", "")).strip(),
            enrolled=bool(payload.get("enrolled", False)),
            samples=int(payload.get("samples", 0)),
            similarity=_maybe_float(payload.get("similarity")),
        )


@dataclass(slots=True)
class TranscriptResult:
    engine_name: str
    segments: list[TranscriptSegment]
    speakers: list[SpeakerProfile]
    duration_seconds: float
    detected_language: str | None = None
    warnings: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(segment.text for segment in self.segments if segment.text)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "engine": self.engine_name,
            "segments": [segment.to_payload() for segment in self.segments],
            "speakers": [speaker.to_payload() for speaker in self.speakers],
            "durationSeconds": round(self.duration_seconds, 3),
            "warnings": self.warnings,
            "text": self.text(),
        }
        if self.detected_language:
            payload["detectedLanguage"] = self.detected_language
        return payload


@dataclass(slots=True)
class TranscriptionOptions:
    language: str | None = None
    diarize: bool = True
    prompt: str | None = None
    link_context: bool = True
    post_process: bool = False
    post_process_backend: str | None = None
    post_process_model: str | None = None
    live: bool = False
    max_speakers: int = 6
    offset_seconds: float = 0.0


@dataclass(slots=True)
class LiveSession:
    session_id: str
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)
    chunk_count: int = 0
    total_audio_seconds: float = 0.0
    engine_name: str = "mock"
    session_type: str = "live"
    title: str | None = None
    warnings: list[str] = field(default_factory=list)
    segments: list[TranscriptSegment] = field(default_factory=list)
    draft_segments: list[TranscriptSegment] = field(default_factory=list)
    speakers: dict[str, SpeakerProfile] = field(default_factory=dict)
    speaker_embeddings: dict[str, object] = field(default_factory=dict)
    speaker_counts: dict[str, int] = field(default_factory=dict)

    def attach_segments(self, segments: list[TranscriptSegment]) -> None:
        self.segments.extend(segments)
        self.segments.sort(key=lambda item: (item.start, item.end, item.segment_id))

    def replace_draft_segments(self, segments: list[TranscriptSegment]) -> None:
        self.draft_segments = list(segments)
        self.draft_segments.sort(key=lambda item: (item.start, item.end, item.segment_id))

    def timeline_segments(self) -> list[TranscriptSegment]:
        return sorted(
            [*self.segments, *self.draft_segments],
            key=lambda item: (item.start, item.end, item.segment_id),
        )

    def merge_speakers(self, speakers: list[SpeakerProfile]) -> None:
        for speaker in speakers:
            self.speakers[speaker.speaker_id] = speaker

    def rename_speaker(self, speaker_id: str, label: str) -> SpeakerProfile:
        normalized = label.strip()
        if not normalized:
            raise ValueError("Speaker label cannot be empty.")

        profile = self.speakers.get(speaker_id)
        if profile is None:
            raise KeyError(f"Unknown speaker: {speaker_id}")

        profile.label = normalized
        for segment in self.segments:
            if segment.speaker_id == speaker_id:
                segment.speaker_name = normalized
        return profile

    def rename(self, title: str | None) -> str | None:
        normalized = _maybe_str(title)
        self.title = normalized
        return self.title

    def update_segment_text(self, segment_id: str, text: str) -> TranscriptSegment:
        normalized = text.strip()
        if not normalized:
            raise ValueError("Segment text cannot be empty.")

        for segment in self.segments:
            if segment.segment_id != segment_id:
                continue
            segment.text = normalized
            # Word alignment is no longer trustworthy after a manual edit.
            segment.words = []
            segment.manually_edited = True
            segment.edited_at = utcnow_iso()
            return segment

        raise KeyError(f"Unknown segment: {segment_id}")

    def to_payload(self) -> dict[str, object]:
        return {
            "sessionId": self.session_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "chunkCount": self.chunk_count,
            "totalAudioSeconds": round(self.total_audio_seconds, 3),
            "engine": self.engine_name,
            "sessionType": self.session_type,
            "title": self.title,
            "warnings": self.warnings,
            "segments": [segment.to_payload() for segment in self.segments],
            "draftSegments": [segment.to_payload() for segment in self.draft_segments],
            "speakers": [speaker.to_payload() for speaker in self.speakers.values()],
            "text": "\n".join(segment.text for segment in self.timeline_segments() if segment.text),
        }

    def to_summary_payload(self) -> dict[str, object]:
        return {
            "sessionId": self.session_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "engine": self.engine_name,
            "sessionType": self.session_type,
            "title": self.title,
            "chunkCount": self.chunk_count,
            "totalAudioSeconds": round(self.total_audio_seconds, 3),
            "segmentCount": len(self.timeline_segments()),
            "speakerCount": len(self.speakers),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "LiveSession":
        session = cls(
            session_id=str(payload.get("sessionId", "")),
            created_at=str(payload.get("createdAt", utcnow_iso())),
            updated_at=str(payload.get("updatedAt", payload.get("createdAt", utcnow_iso()))),
            chunk_count=int(payload.get("chunkCount", 0)),
            total_audio_seconds=float(payload.get("totalAudioSeconds", 0.0)),
            engine_name=str(payload.get("engine", "mock")),
            session_type=str(payload.get("sessionType", "live")),
            title=_maybe_str(payload.get("title")),
            warnings=[str(item) for item in payload.get("warnings", []) if isinstance(item, str)],
        )

        raw_segments = payload.get("segments")
        if isinstance(raw_segments, list):
            session.segments = [
                TranscriptSegment.from_payload(entry)
                for entry in raw_segments
                if isinstance(entry, dict)
            ]

        raw_draft_segments = payload.get("draftSegments")
        if isinstance(raw_draft_segments, list):
            session.draft_segments = [
                TranscriptSegment.from_payload(entry)
                for entry in raw_draft_segments
                if isinstance(entry, dict)
            ]

        raw_speakers = payload.get("speakers")
        if isinstance(raw_speakers, list):
            session.speakers = {
                speaker.speaker_id: speaker
                for speaker in (
                    SpeakerProfile.from_payload(entry)
                    for entry in raw_speakers
                    if isinstance(entry, dict)
                )
            }
        return session


def _maybe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _maybe_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
