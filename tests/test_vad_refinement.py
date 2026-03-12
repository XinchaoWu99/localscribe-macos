from __future__ import annotations

from localscribe.diarization.service import _refine_segments_with_vad
from localscribe.diarization.vad import SpeechWindow
from localscribe.models import TranscriptSegment


def test_refine_segments_with_vad_keeps_degenerate_text_segment() -> None:
    refined = _refine_segments_with_vad(
        [
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=0.0,
                text="[INAUDIBLE]",
            )
        ],
        [SpeechWindow(start=1.4, end=2.6)],
    )

    assert len(refined) == 1
    assert refined[0].text == "[INAUDIBLE]"
    assert refined[0].start == 1.4
    assert refined[0].end == 2.6


def test_refine_segments_with_vad_still_drops_non_overlapping_timed_segment() -> None:
    refined = _refine_segments_with_vad(
        [
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=0.4,
                text="noise",
            )
        ],
        [SpeechWindow(start=1.4, end=2.6)],
    )

    assert refined == []
