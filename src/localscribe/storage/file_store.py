from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(slots=True)
class StoredAudioPaths:
    root_dir: Path
    raw_path: Path
    normalized_path: Path


class FileStore:
    def __init__(self, uploads_dir: Path) -> None:
        self.uploads_dir = uploads_dir
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def create_upload_paths(self, suffix: str) -> StoredAudioPaths:
        upload_id = uuid4().hex
        root_dir = self.uploads_dir / upload_id
        root_dir.mkdir(parents=True, exist_ok=True)
        return StoredAudioPaths(
            root_dir=root_dir,
            raw_path=root_dir / f"source{suffix}",
            normalized_path=root_dir / "normalized.wav",
        )

    def create_speaker_sample_paths(self, session_dir: Path, suffix: str) -> StoredAudioPaths:
        root_dir = session_dir / "enrollment" / uuid4().hex
        root_dir.mkdir(parents=True, exist_ok=True)
        return StoredAudioPaths(
            root_dir=root_dir,
            raw_path=root_dir / f"source{suffix}",
            normalized_path=root_dir / "sample.wav",
        )
