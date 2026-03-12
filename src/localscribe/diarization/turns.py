from __future__ import annotations

from uuid import uuid4

from ..models import TranscriptSegment


class DiscussionTurnSegmenter:
    def __init__(self, max_gap_seconds: float = 0.85, max_turn_seconds: float = 18.0) -> None:
        self.max_gap_seconds = max_gap_seconds
        self.max_turn_seconds = max_turn_seconds

    def segment(self, segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
        ordered = sorted(segments, key=lambda item: (item.start, item.end, item.segment_id))
        if not ordered:
            return []

        turns: list[TranscriptSegment] = []
        current = self._clone(ordered[0])
        merged_count = 1

        for segment in ordered[1:]:
            gap = max(0.0, segment.start - current.end)
            if self._should_merge(current, segment, gap):
                current.end = max(current.end, segment.end)
                current.text = _merge_text(current.text, segment.text)
                current.words.extend(segment.words)
                current.confidence = _merge_confidence(current.confidence, segment.confidence)
                merged_count += 1
                if merged_count > 1:
                    current.segment_id = uuid4().hex
                continue

            turns.append(current)
            current = self._clone(segment)
            merged_count = 1

        turns.append(current)
        return turns

    def _should_merge(self, current: TranscriptSegment, incoming: TranscriptSegment, gap: float) -> bool:
        duration = incoming.end - current.start
        return (
            gap <= self.max_gap_seconds
            and duration <= self.max_turn_seconds
            and _compatible_speakers(current, incoming)
        )

    def _clone(self, segment: TranscriptSegment) -> TranscriptSegment:
        return TranscriptSegment(
            segment_id=segment.segment_id,
            start=segment.start,
            end=segment.end,
            text=segment.text,
            confidence=segment.confidence,
            speaker_id=segment.speaker_id,
            speaker_name=segment.speaker_name,
            is_final=segment.is_final,
            source=segment.source,
            words=list(segment.words),
        )


def _merge_text(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if left.endswith((" ", "\n")):
        return f"{left}{right}"
    if right.startswith((",", ".", "!", "?", ";", ":")):
        return f"{left}{right}"
    return f"{left} {right}"


def _merge_confidence(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _compatible_speakers(left: TranscriptSegment, right: TranscriptSegment) -> bool:
    if left.speaker_id and right.speaker_id:
        return left.speaker_id == right.speaker_id
    if left.speaker_name and right.speaker_name:
        return left.speaker_name == right.speaker_name
    return True
