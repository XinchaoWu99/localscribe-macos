from __future__ import annotations

from localscribe.models import LiveSession, SegmentWord, TranscriptResult, TranscriptSegment, TranscriptionOptions
from localscribe.postprocess import LocalPostProcessingService


class FakePostProcessorBackend:
    def __init__(self, response: str, *, ready: bool = True) -> None:
        self.response = response
        self.ready = ready
        self.calls: list[str] = []

    def status(self) -> dict[str, object]:
        return {
            "enabled": True,
            "ready": self.ready,
            "backend": "fake",
            "model": "fake-model",
            "warning": None,
        }

    def correct(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


def test_post_processing_corrects_punctuation_without_dropping_words() -> None:
    backend = FakePostProcessorBackend(
        '{"segments":[{"segmentId":"seg-1","text":"hello, world."}]}'
    )
    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        backend_override=backend,
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=1.0,
                text="hello world",
                words=[
                    SegmentWord(start=0.0, end=0.4, text="hello"),
                    SegmentWord(start=0.4, end=1.0, text="world"),
                ],
            )
        ],
        speakers=[],
        duration_seconds=1.0,
    )

    plan = service.refine_live_result(
        LiveSession(session_id="live-1"),
        result,
        TranscriptionOptions(post_process=True, live=True),
    )

    updated = plan.result
    assert updated.segments[0].text == "hello, world."
    assert len(updated.segments[0].words) == 2
    assert plan.replace_tail_count == 0
    assert backend.calls


def test_post_processing_clears_word_alignment_when_tokens_change() -> None:
    backend = FakePostProcessorBackend(
        '{"segments":[{"segmentId":"seg-2","text":"AcmeSoft shipped the patch."}]}'
    )
    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        backend_override=backend,
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-2",
                start=0.0,
                end=1.2,
                text="acme soft shipped the patch",
                words=[
                    SegmentWord(start=0.0, end=0.3, text="acme"),
                    SegmentWord(start=0.3, end=0.6, text="soft"),
                    SegmentWord(start=0.6, end=0.8, text="shipped"),
                    SegmentWord(start=0.8, end=1.0, text="the"),
                    SegmentWord(start=1.0, end=1.2, text="patch"),
                ],
            )
        ],
        speakers=[],
        duration_seconds=1.2,
    )

    updated = service.refine_file_result(result, TranscriptionOptions(post_process=True))

    assert updated.segments[0].text == "AcmeSoft shipped the patch."
    assert updated.segments[0].words == []


def test_post_processing_uses_requested_backend_and_model(monkeypatch) -> None:
    backend = FakePostProcessorBackend(
        '{"segments":[{"segmentId":"seg-3","text":"final sentence."}]}'
    )
    service = LocalPostProcessingService(
        enabled=False,
        backend_name="none",
    )
    selected: dict[str, str | None] = {}

    def fake_backend_for_selection(backend_name: str, model: str | None):
        selected["backend"] = backend_name
        selected["model"] = model
        return backend

    monkeypatch.setattr(service, "_backend_for_selection", fake_backend_for_selection)
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-3",
                start=0.0,
                end=1.0,
                text="final sentence",
            )
        ],
        speakers=[],
        duration_seconds=1.0,
    )

    updated = service.refine_file_result(
        result,
        TranscriptionOptions(
            post_process=True,
            post_process_backend="mlx",
            post_process_model="mlx-community/custom-cleanup-model",
        ),
    )

    assert selected == {
        "backend": "mlx",
        "model": "mlx-community/custom-cleanup-model",
    }
    assert updated.segments[0].text == "final sentence."


def test_post_processing_rewrites_previous_tail_and_current_chunk() -> None:
    backend = FakePostProcessorBackend(
        (
            '{"segments":['
            '{"segmentId":"seg-prev","text":"AcmeSoft launched the update."},'
            '{"segmentId":"seg-new","text":"It reached the beta team yesterday."}'
            "]}"
        )
    )
    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        backend_override=backend,
        recent_segments=2,
    )
    session = LiveSession(
        session_id="live-2",
        segments=[
            TranscriptSegment(
                segment_id="seg-prev",
                start=0.0,
                end=1.5,
                text="acme soft launched the update",
                source="live",
            )
        ],
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-new",
                start=1.5,
                end=3.0,
                text="it reached the beta team yesterday",
                source="live",
            )
        ],
        speakers=[],
        duration_seconds=1.5,
    )

    plan = service.refine_live_result(
        session,
        result,
        TranscriptionOptions(post_process=True, live=True),
    )

    assert plan.replace_tail_count == 1
    assert plan.replacement_segments is not None
    assert [segment.segment_id for segment in plan.replacement_segments] == ["seg-prev", "seg-new"]
    assert plan.replacement_segments[0].text == "AcmeSoft launched the update."
    assert plan.result.segments[0].text == "It reached the beta team yesterday."
    assert backend.calls


def test_post_processing_skips_manually_edited_tail_rewrites() -> None:
    backend = FakePostProcessorBackend(
        (
            '{"segments":['
            '{"segmentId":"seg-prev","text":"AcmeSoft launched the update."},'
            '{"segmentId":"seg-new","text":"It reached the beta team yesterday."}'
            "]}"
        )
    )
    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        backend_override=backend,
        recent_segments=2,
    )
    session = LiveSession(
        session_id="live-3",
        segments=[
            TranscriptSegment(
                segment_id="seg-prev",
                start=0.0,
                end=1.5,
                text="AcmeSoft launched the update.",
                source="live",
                manually_edited=True,
                edited_at="2026-03-12T00:00:00+00:00",
            )
        ],
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-new",
                start=1.5,
                end=3.0,
                text="it reached the beta team yesterday",
                source="live",
            )
        ],
        speakers=[],
        duration_seconds=1.5,
    )

    plan = service.refine_live_result(
        session,
        result,
        TranscriptionOptions(post_process=True, live=True),
    )

    assert plan.replace_tail_count == 0
    assert plan.replacement_segments is None
    assert plan.result.segments[0].segment_id == "seg-new"
