from __future__ import annotations

from localscribe.context import ContextRefinementService
from localscribe.models import LiveSession, SegmentWord, TranscriptResult, TranscriptSegment, TranscriptionOptions


def test_build_live_options_includes_recent_context() -> None:
    service = ContextRefinementService(enabled=True, prompt_segments=2, prompt_max_chars=120)
    session = LiveSession(
        session_id="live-1",
        segments=[
            TranscriptSegment(segment_id="a", start=0.0, end=1.0, text="Welcome to the design review."),
            TranscriptSegment(segment_id="b", start=1.1, end=2.0, text="We are discussing LocalScribe today."),
        ],
    )

    options = service.build_live_options(session, TranscriptionOptions(prompt="Product names: LocalScribe"))

    assert options.prompt is not None
    assert "Product names: LocalScribe" in options.prompt
    assert "design review" in options.prompt
    assert "LocalScribe today" in options.prompt


def test_refine_live_result_merges_boundary_overlap() -> None:
    service = ContextRefinementService(enabled=True, merge_gap_seconds=1.2, merge_max_turn_seconds=20.0)
    session = LiveSession(
        session_id="live-2",
        segments=[
            TranscriptSegment(
                segment_id="prev",
                start=0.0,
                end=2.1,
                text="We need to support live model switching",
                words=[
                    SegmentWord(start=0.0, end=0.3, text="We"),
                    SegmentWord(start=0.3, end=0.6, text="need"),
                    SegmentWord(start=0.6, end=0.8, text="to"),
                    SegmentWord(start=0.8, end=1.1, text="support"),
                    SegmentWord(start=1.1, end=1.5, text="live"),
                    SegmentWord(start=1.5, end=1.8, text="model"),
                    SegmentWord(start=1.8, end=2.1, text="switching"),
                ],
            )
        ],
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="next",
                start=2.15,
                end=4.0,
                text="live model switching without stopping the session.",
                words=[
                    SegmentWord(start=2.15, end=2.4, text="live"),
                    SegmentWord(start=2.4, end=2.7, text="model"),
                    SegmentWord(start=2.7, end=3.0, text="switching"),
                    SegmentWord(start=3.0, end=3.3, text="without"),
                    SegmentWord(start=3.3, end=3.5, text="stopping"),
                    SegmentWord(start=3.5, end=3.8, text="the"),
                    SegmentWord(start=3.8, end=4.0, text="session."),
                ],
            )
        ],
        speakers=[],
        duration_seconds=1.85,
    )

    plan = service.refine_live_result(session, result, TranscriptionOptions(link_context=True, live=True))

    assert plan.replace_tail_count == 1
    assert len(plan.result.segments) == 1
    assert plan.result.segments[0].text == "We need to support live model switching without stopping the session."


def test_refine_live_result_preserves_manually_edited_tail() -> None:
    service = ContextRefinementService(enabled=True, merge_gap_seconds=1.2, merge_max_turn_seconds=20.0)
    session = LiveSession(
        session_id="live-3",
        segments=[
            TranscriptSegment(
                segment_id="prev",
                start=0.0,
                end=2.1,
                text="AcmeSoft launched the update",
                manually_edited=True,
                edited_at="2026-03-12T00:00:00+00:00",
            )
        ],
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="next",
                start=2.15,
                end=3.0,
                text="the update yesterday.",
            )
        ],
        speakers=[],
        duration_seconds=0.85,
    )

    plan = service.refine_live_result(session, result, TranscriptionOptions(link_context=True, live=True))

    assert plan.replace_tail_count == 0
    assert len(plan.result.segments) == 1
    assert plan.result.segments[0].segment_id == "next"
    assert plan.result.segments[0].text == "yesterday."
