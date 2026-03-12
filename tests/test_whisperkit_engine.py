from __future__ import annotations

import pytest

from localscribe.config import Settings
from localscribe.engines.whisperkit import WhisperKitServerEngine


def test_segments_from_payload_fits_out_of_bounds_timestamps_to_clip(tmp_path) -> None:
    engine = WhisperKitServerEngine(Settings(data_dir=tmp_path))

    segments = engine._segments_from_payload(  # noqa: SLF001
        {
            "segments": [
                {
                    "start": 4.22,
                    "end": 5.62,
                    "text": " [INAUDIBLE]",
                }
            ]
        },
        offset_seconds=0.0,
        source="live",
        clip_duration_seconds=2.6453125,
    )

    assert len(segments) == 1
    assert segments[0].text == "[INAUDIBLE]"
    assert segments[0].start == pytest.approx(1.2453125)
    assert segments[0].end == pytest.approx(2.6453125)
