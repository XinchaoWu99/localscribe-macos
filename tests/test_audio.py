from __future__ import annotations

import math
from pathlib import Path
import wave

from localscribe.audio import normalize_audio, probe_duration_seconds


def test_normalize_audio_skips_ffmpeg_for_pcm16_mono_16khz_wav(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "normalized.wav"
    _write_wav(source, sample_rate=16_000, channels=1, sample_width=2, duration_ms=1200)

    normalize_audio(source, destination)

    assert destination.read_bytes() == source.read_bytes()


def test_probe_duration_seconds_uses_wav_header_without_ffprobe(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_wav(source, sample_rate=16_000, channels=1, sample_width=2, duration_ms=1500)

    duration = probe_duration_seconds(source)

    assert duration == 1.5


def _write_wav(
    path: Path,
    *,
    sample_rate: int,
    channels: int,
    sample_width: int,
    duration_ms: int,
    frequency_hz: float = 440.0,
) -> None:
    frame_count = int(sample_rate * duration_ms / 1000)
    amplitude = (2 ** (sample_width * 8 - 1)) - 1

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)

        frames = bytearray()
        for index in range(frame_count):
            value = math.sin(2 * math.pi * frequency_hz * (index / sample_rate))
            sample = int(value * amplitude * 0.35)
            encoded = sample.to_bytes(sample_width, "little", signed=True)
            for _ in range(channels):
                frames.extend(encoded)
        handle.writeframes(bytes(frames))
