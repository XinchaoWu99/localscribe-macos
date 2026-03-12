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

    updated = service.refine_live_result(
        LiveSession(session_id="live-1"),
        result,
        TranscriptionOptions(post_process=True, live=True),
    )

    assert updated.segments[0].text == "hello, world."
    assert len(updated.segments[0].words) == 2
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
