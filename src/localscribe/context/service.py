from __future__ import annotations

from dataclasses import dataclass, replace
import re

from ..models import LiveSession, SegmentWord, TranscriptResult, TranscriptSegment, TranscriptionOptions

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
_SENTENCE_ENDINGS = (".", "!", "?")


@dataclass(slots=True)
class ContextRefinementPlan:
    result: TranscriptResult
    replace_tail_count: int = 0


class ContextRefinementService:
    def __init__(
        self,
        *,
        enabled: bool = True,
        prompt_segments: int = 6,
        prompt_max_chars: int = 480,
        merge_gap_seconds: float = 1.1,
        merge_max_turn_seconds: float = 28.0,
    ) -> None:
        self.enabled = enabled
        self.prompt_segments = prompt_segments
        self.prompt_max_chars = prompt_max_chars
        self.merge_gap_seconds = merge_gap_seconds
        self.merge_max_turn_seconds = merge_max_turn_seconds

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "promptSegments": self.prompt_segments,
            "promptMaxChars": self.prompt_max_chars,
            "mergeGapSeconds": self.merge_gap_seconds,
            "mergeMaxTurnSeconds": self.merge_max_turn_seconds,
        }

    def build_live_options(self, session: LiveSession, options: TranscriptionOptions) -> TranscriptionOptions:
        if not self.enabled or not options.link_context:
            return options

        recent_context = self._recent_context(session)
        prompt = _compose_prompt(options.prompt, recent_context, self.prompt_max_chars)
        if prompt == options.prompt:
            return options
        return replace(options, prompt=prompt)

    def refine_live_result(
        self,
        session: LiveSession,
        result: TranscriptResult,
        options: TranscriptionOptions,
    ) -> ContextRefinementPlan:
        if not self.enabled or not options.link_context:
            return ContextRefinementPlan(result=result, replace_tail_count=0)

        segments = self._coalesce_segments([_clone_segment(segment) for segment in result.segments])
        replace_tail_count = 0
        if session.segments and segments:
            previous = _clone_segment(session.segments[-1])
            first = segments[0]
            overlap_trimmed = _trim_boundary_overlap(previous, first)
            if not first.text.strip():
                segments = segments[1:]
            elif previous.manually_edited:
                segments = self._coalesce_segments(segments)
            elif self._should_merge(previous, first, overlap_trimmed):
                segments[0] = _merge_segments(previous, first)
                replace_tail_count = 1
                segments = self._coalesce_segments(segments)

        result.segments = segments
        return ContextRefinementPlan(result=result, replace_tail_count=replace_tail_count)

    def refine_file_result(self, result: TranscriptResult, options: TranscriptionOptions) -> TranscriptResult:
        if not self.enabled or not options.link_context:
            return result
        result.segments = self._coalesce_segments([_clone_segment(segment) for segment in result.segments])
        return result

    def _recent_context(self, session: LiveSession) -> str | None:
        texts = [segment.text.strip() for segment in session.segments if segment.text.strip()]
        if not texts:
            return None

        joined = " ".join(texts[-self.prompt_segments :]).strip()
        if not joined:
            return None
        if len(joined) <= self.prompt_max_chars:
            return joined
        return joined[-self.prompt_max_chars :].lstrip()

    def _coalesce_segments(self, segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
        ordered = sorted(segments, key=lambda item: (item.start, item.end, item.segment_id))
        if not ordered:
            return []

        merged: list[TranscriptSegment] = []
        current = ordered[0]

        for incoming in ordered[1:]:
            overlap_trimmed = _trim_boundary_overlap(current, incoming)
            if not incoming.text.strip():
                continue
            if self._should_merge(current, incoming, overlap_trimmed):
                current = _merge_segments(current, incoming)
                continue
            merged.append(current)
            current = incoming

        merged.append(current)
        return merged

    def _should_merge(
        self,
        current: TranscriptSegment,
        incoming: TranscriptSegment,
        overlap_trimmed: bool,
    ) -> bool:
        gap = max(0.0, incoming.start - current.end)
        if gap > self.merge_gap_seconds:
            return False
        if incoming.end - current.start > self.merge_max_turn_seconds:
            return False
        if not _compatible_speakers(current, incoming):
            return False
        if overlap_trimmed:
            return True
        if not current.text.strip():
            return True
        if current.text.rstrip().endswith((",", ";", ":")):
            return True
        if not current.text.rstrip().endswith(_SENTENCE_ENDINGS):
            return True
        stripped = incoming.text.lstrip()
        if not stripped:
            return True
        return _starts_lowercase_phrase(stripped)


def _compose_prompt(base_prompt: str | None, recent_context: str | None, max_chars: int) -> str | None:
    base = (base_prompt or "").strip()
    context = (recent_context or "").strip()
    if not base and not context:
        return None
    if not context:
        return base or None
    if not base:
        return context[-max_chars:] if len(context) > max_chars else context

    reserved = min(len(base), max(80, max_chars // 3))
    tail_budget = max_chars - reserved - 1
    if tail_budget <= 0:
        return base[:max_chars].strip() or None
    context_tail = context[-tail_budget:].lstrip()
    return f"{base[:reserved].strip()} {context_tail}".strip() or None


def _compatible_speakers(left: TranscriptSegment, right: TranscriptSegment) -> bool:
    if left.speaker_id and right.speaker_id:
        return left.speaker_id == right.speaker_id
    if left.speaker_name and right.speaker_name:
        return left.speaker_name == right.speaker_name
    return True


def _starts_lowercase_phrase(text: str) -> bool:
    for char in text:
        if char.isalpha():
            return char.islower()
    return False


def _trim_boundary_overlap(previous: TranscriptSegment, incoming: TranscriptSegment) -> bool:
    if previous.words and incoming.words:
        overlap = _find_overlap(
            [word.text for word in previous.words],
            [word.text for word in incoming.words],
        )
        if overlap <= 0:
            return False
        incoming.words = incoming.words[overlap:]
        if incoming.words:
            incoming.start = incoming.words[0].start
            incoming.text = _join_words(incoming.words)
        else:
            incoming.text = ""
        return True

    previous_tokens = previous.text.split()
    incoming_tokens = incoming.text.split()
    overlap = _find_overlap(previous_tokens, incoming_tokens)
    if overlap <= 0:
        return False
    incoming.text = " ".join(incoming_tokens[overlap:]).strip()
    return True


def _find_overlap(left_tokens: list[str], right_tokens: list[str], max_overlap: int = 8) -> int:
    if not left_tokens or not right_tokens:
        return 0

    normalized_left = [_normalize_token(token) for token in left_tokens if _normalize_token(token)]
    normalized_right = [_normalize_token(token) for token in right_tokens if _normalize_token(token)]
    if not normalized_left or not normalized_right:
        return 0

    limit = min(len(normalized_left), len(normalized_right), max_overlap)
    for size in range(limit, 0, -1):
        if normalized_left[-size:] != normalized_right[:size]:
            continue
        if size >= 2:
            return size
        if normalized_right[0] and len(normalized_right[0]) >= 7:
            return size
    return 0


def _normalize_token(token: str) -> str:
    match = _TOKEN_RE.search(token.lower())
    if match is None:
        return ""
    return match.group(0)


def _merge_segments(left: TranscriptSegment, right: TranscriptSegment) -> TranscriptSegment:
    words = list(left.words) + list(right.words)
    return TranscriptSegment(
        segment_id=left.segment_id,
        start=min(left.start, right.start),
        end=max(left.end, right.end),
        text=_merge_text(left.text, right.text),
        confidence=_merge_confidence(left.confidence, right.confidence),
        speaker_id=left.speaker_id or right.speaker_id,
        speaker_name=left.speaker_name or right.speaker_name,
        is_final=left.is_final and right.is_final,
        source=right.source,
        manually_edited=left.manually_edited or right.manually_edited,
        edited_at=left.edited_at or right.edited_at,
        words=words,
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


def _join_words(words: list[SegmentWord]) -> str:
    text = ""
    for word in words:
        part = word.text.strip()
        if not part:
            continue
        if not text:
            text = part
        elif part.startswith((",", ".", "!", "?", ";", ":")):
            text = f"{text}{part}"
        else:
            text = f"{text} {part}"
    return text


def _clone_segment(segment: TranscriptSegment) -> TranscriptSegment:
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
        manually_edited=segment.manually_edited,
        edited_at=segment.edited_at,
        words=[
            SegmentWord(
                start=word.start,
                end=word.end,
                text=word.text,
                confidence=word.confidence,
            )
            for word in segment.words
        ],
    )
