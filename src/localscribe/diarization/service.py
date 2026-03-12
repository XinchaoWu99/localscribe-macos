from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..models import LiveSession, SpeakerProfile, TranscriptSegment, TranscriptionOptions, TranscriptResult
from ..speakers import SpeakerResolver
from .turns import DiscussionTurnSegmenter
from .vad import SileroVoiceActivityDetector, SpeechWindow


class DiarizationService:
    def __init__(
        self,
        speaker_resolver: SpeakerResolver,
        turn_segmenter: DiscussionTurnSegmenter,
        vad: SileroVoiceActivityDetector,
    ) -> None:
        self.speaker_resolver = speaker_resolver
        self.turn_segmenter = turn_segmenter
        self.vad = vad

    def status(self) -> dict[str, object]:
        return {
            "enabled": True,
            "voiceActivityDetection": self.vad.status(),
            "turnSegmentation": {
                "maxGapSeconds": self.turn_segmenter.max_gap_seconds,
                "maxTurnSeconds": self.turn_segmenter.max_turn_seconds,
            },
            "speakerRecognition": self.speaker_resolver.status(),
        }

    def detect_speech(self, audio_path: Path, offset_seconds: float = 0.0) -> list[SpeechWindow] | None:
        return self.vad.detect(audio_path, offset_seconds=offset_seconds)

    def enroll_speaker(self, session: LiveSession, sample_path: Path, label: str) -> SpeakerProfile:
        return self.speaker_resolver.enroll(session, sample_path, label)

    def process_live_result(
        self,
        session: LiveSession,
        normalized_path: Path,
        result: TranscriptResult,
        options: TranscriptionOptions,
        speech_windows: list[SpeechWindow] | None = None,
    ) -> TranscriptResult:
        result.segments = _refine_segments_with_vad(result.segments, speech_windows)
        if options.diarize:
            result.speakers = self.speaker_resolver.assign(session, normalized_path, result.segments)
        else:
            result.speakers = list(session.speakers.values())
        result.segments = self.turn_segmenter.segment(result.segments)
        return result

    def process_file_result(
        self,
        normalized_path: Path,
        result: TranscriptResult,
        options: TranscriptionOptions,
        speech_windows: list[SpeechWindow] | None = None,
    ) -> TranscriptResult:
        result.segments = _refine_segments_with_vad(result.segments, speech_windows)
        if options.diarize:
            temp_session = LiveSession(session_id=f"file-{uuid4().hex}", engine_name=result.engine_name)
            result.speakers = self.speaker_resolver.assign(temp_session, normalized_path, result.segments)
        result.segments = self.turn_segmenter.segment(result.segments)
        return result


def _refine_segments_with_vad(
    segments: list[TranscriptSegment],
    speech_windows: list[SpeechWindow] | None,
) -> list[TranscriptSegment]:
    if speech_windows is None:
        return segments
    if not speech_windows:
        return []

    refined = []
    for segment in segments:
        refined.extend(_split_segment_for_windows(segment, speech_windows))
    return refined


def _split_segment_for_windows(
    segment: TranscriptSegment,
    windows: list[SpeechWindow],
) -> list[TranscriptSegment]:
    overlaps = [window for window in windows if window.overlaps(segment.start, segment.end)]
    if not overlaps:
        return []

    if segment.words:
        pieces = []
        for window in overlaps:
            words = [word for word in segment.words if _overlaps(word.start, word.end, window.start, window.end)]
            if not words:
                continue
            pieces.append(
                segment.__class__(
                    segment_id=uuid4().hex,
                    start=max(window.start, words[0].start),
                    end=min(window.end, words[-1].end),
                    text=_join_words(words),
                    confidence=segment.confidence,
                    speaker_id=segment.speaker_id,
                    speaker_name=segment.speaker_name,
                    is_final=segment.is_final,
                    source=segment.source,
                    words=list(words),
                )
            )
        if pieces:
            return pieces

    start = max(segment.start, overlaps[0].start)
    end = min(segment.end, overlaps[-1].end)
    if end <= start:
        return []

    return [
        segment.__class__(
            segment_id=uuid4().hex,
            start=start,
            end=end,
            text=segment.text,
            confidence=segment.confidence,
            speaker_id=segment.speaker_id,
            speaker_name=segment.speaker_name,
            is_final=segment.is_final,
            source=segment.source,
            words=list(segment.words),
        )
    ]


def _join_words(words) -> str:
    text = ""
    for word in words:
        part = word.text.strip()
        if not part:
            continue
        if not text:
            text = part
            continue
        if part.startswith((",", ".", "!", "?", ";", ":")):
            text = f"{text}{part}"
        else:
            text = f"{text} {part}"
    return text


def _overlaps(start: float, end: float, window_start: float, window_end: float) -> bool:
    return min(end, window_end) > max(start, window_start)
