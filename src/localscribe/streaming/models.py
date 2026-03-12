from __future__ import annotations

from dataclasses import dataclass

from ..models import TranscriptionOptions


@dataclass(slots=True)
class UploadTranscriptionRequest:
    filename: str
    raw_bytes: bytes
    options: TranscriptionOptions


@dataclass(slots=True)
class SpeakerEnrollmentRequest:
    filename: str
    raw_bytes: bytes
    label: str


@dataclass(slots=True)
class LiveChunkRequest:
    sequence: int
    mime_type: str
    raw_bytes: bytes
    options: TranscriptionOptions
