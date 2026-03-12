from __future__ import annotations

from localscribe.diarization import DiscussionTurnSegmenter
from localscribe.models import TranscriptSegment


def test_turn_segmenter_merges_same_speaker_continuations() -> None:
    segmenter = DiscussionTurnSegmenter(max_gap_seconds=0.9, max_turn_seconds=12.0)

    turns = segmenter.segment(
        [
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=1.0,
                text="Hello everyone",
                speaker_id="speaker-a",
                speaker_name="Speaker 1",
            ),
            TranscriptSegment(
                segment_id="seg-2",
                start=1.15,
                end=2.4,
                text="thanks for joining",
                speaker_id="speaker-a",
                speaker_name="Speaker 1",
            ),
        ]
    )

    assert len(turns) == 1
    assert turns[0].text == "Hello everyone thanks for joining"


def test_turn_segmenter_keeps_different_speakers_separate() -> None:
    segmenter = DiscussionTurnSegmenter(max_gap_seconds=0.9, max_turn_seconds=12.0)

    turns = segmenter.segment(
        [
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=1.0,
                text="Hello everyone",
                speaker_id="speaker-a",
                speaker_name="Speaker 1",
            ),
            TranscriptSegment(
                segment_id="seg-2",
                start=1.15,
                end=2.4,
                text="thanks for the intro",
                speaker_id="speaker-b",
                speaker_name="Speaker 2",
            ),
        ]
    )

    assert len(turns) == 2
    assert turns[0].speaker_name == "Speaker 1"
    assert turns[1].speaker_name == "Speaker 2"
