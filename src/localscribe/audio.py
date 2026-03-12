from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


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
