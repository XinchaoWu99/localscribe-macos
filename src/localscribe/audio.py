from __future__ import annotations

import math
from array import array
import shutil
import subprocess
import tempfile
from pathlib import Path
import wave


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "unknown ffmpeg error"
        raise RuntimeError(stderr)


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required but was not found on PATH.")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe is required but was not found on PATH.")


def normalize_audio(source: Path, destination: Path) -> None:
    require_ffmpeg()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(destination),
        ]
    )


def apply_volume_gain(path: Path, gain_multiplier: float) -> None:
    require_ffmpeg()
    path.parent.mkdir(parents=True, exist_ok=True)
    multiplier = max(1.0, float(gain_multiplier))
    if multiplier <= 1.01:
        return

    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".wav", delete=False) as handle:
        temp_path = Path(handle.name)

    try:
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(path),
                "-vn",
                "-af",
                f"volume={multiplier:.4f}",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-sample_fmt",
                "s16",
                str(temp_path),
            ]
        )
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def probe_duration_seconds(path: Path) -> float:
    require_ffmpeg()
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "unknown ffprobe error"
        raise RuntimeError(stderr)
    try:
        return float(completed.stdout.strip())
    except ValueError:
        return 0.0


def extract_clip(source: Path, destination: Path, start_seconds: float, end_seconds: float) -> None:
    require_ffmpeg()
    destination.parent.mkdir(parents=True, exist_ok=True)
    start = max(start_seconds, 0.0)
    end = max(end_seconds, start + 0.1)
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(destination),
        ]
    )


def audio_level_stats(path: Path) -> dict[str, float]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        raw = handle.readframes(handle.getnframes())

    if channels != 1:
        raise RuntimeError(f"Audio level analysis expects mono WAV input, got {channels} channels in {path}.")
    if sample_width != 2:
        raise RuntimeError(f"Audio level analysis expects 16-bit PCM WAV input, got {sample_width * 8}-bit audio.")

    pcm = array("h")
    pcm.frombytes(raw)
    if not pcm:
        return {
            "rms": 0.0,
            "peak": 0.0,
            "rmsNormalized": 0.0,
            "peakNormalized": 0.0,
        }

    peak = max(abs(value) for value in pcm)
    rms = math.sqrt(sum(value * value for value in pcm) / len(pcm))
    return {
        "rms": rms,
        "peak": float(peak),
        "rmsNormalized": rms / 32768.0,
        "peakNormalized": peak / 32768.0,
    }
