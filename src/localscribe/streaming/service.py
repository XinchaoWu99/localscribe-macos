from __future__ import annotations

from pathlib import Path

from ..audio import normalize_audio, probe_duration_seconds
from ..config import Settings
from ..context import ContextRefinementService
from ..diarization import DiarizationService
from ..engines.base import TranscriptionEngine
from ..exports import TranscriptExport, build_session_export
from ..models import LiveSession, TranscriptResult
from ..postprocess import LocalPostProcessingService
from ..storage import FileStore, SessionStore
from .models import LiveChunkRequest, SpeakerEnrollmentRequest, UploadTranscriptionRequest


class StreamingService:
    MIN_CHUNK_MILLIS = 800
    MAX_CHUNK_MILLIS = 10000

    def __init__(
        self,
        settings: Settings,
        engine: TranscriptionEngine,
        session_store: SessionStore,
        file_store: FileStore,
        diarization_service: DiarizationService,
        context_refinement_service: ContextRefinementService,
        post_processing_service: LocalPostProcessingService | None = None,
    ) -> None:
        self.settings = settings
        self.engine = engine
        self.session_store = session_store
        self.file_store = file_store
        self.diarization_service = diarization_service
        self.context_refinement_service = context_refinement_service
        self.post_processing_service = post_processing_service or LocalPostProcessingService()

    def create_session(self) -> LiveSession:
        return self.session_store.create(self.engine.name)

    def list_sessions(self, limit: int = 20) -> list[LiveSession]:
        return self.session_store.list_recent(limit=limit)

    def get_session(self, session_id: str) -> LiveSession:
        return self.session_store.get(session_id)

    def export_session(self, session_id: str, format_name: str) -> TranscriptExport:
        return build_session_export(self.get_session(session_id), format_name)

    def update_live_settings(self, *, chunk_millis: int | None = None) -> dict[str, object]:
        if chunk_millis is not None:
            self.settings.chunk_millis = self._normalize_chunk_millis(chunk_millis)
        return self.status()

    def transcribe_upload(self, request: UploadTranscriptionRequest) -> tuple[TranscriptResult, LiveSession]:
        self._enforce_upload_limit(len(request.raw_bytes))
        paths = self.file_store.create_upload_paths(_suffix_for_filename(request.filename))
        paths.raw_path.write_bytes(request.raw_bytes)
        normalize_audio(paths.raw_path, paths.normalized_path)
        session = self.session_store.create(
            self.engine.name,
            session_type="upload",
            title=request.filename,
        )
        speech_windows = self.diarization_service.detect_speech(paths.normalized_path)
        if speech_windows == []:
            result = TranscriptResult(
                engine_name=self.engine.name,
                segments=[],
                speakers=[],
                duration_seconds=probe_duration_seconds(paths.normalized_path),
                warnings=["No speech detected in the uploaded audio."],
            )
            return result, self.session_store.save_result(session, result, duration_seconds=result.duration_seconds)
        result = self.engine.transcribe_file(str(paths.normalized_path), request.options)
        result = self.diarization_service.process_file_result(
            paths.normalized_path,
            result,
            request.options,
            speech_windows=speech_windows,
        )
        result = self.context_refinement_service.refine_file_result(result, request.options)
        result = self.post_processing_service.refine_file_result(result, request.options)
        session = self.session_store.save_result(session, result, duration_seconds=result.duration_seconds)
        return result, session

    def enroll_speaker(self, session_id: str, request: SpeakerEnrollmentRequest):
        self._enforce_upload_limit(len(request.raw_bytes))
        session = self.get_session(session_id)
        paths = self.file_store.create_speaker_sample_paths(
            self.session_store.session_dir(session_id),
            _suffix_for_filename(request.filename),
        )
        paths.raw_path.write_bytes(request.raw_bytes)
        normalize_audio(paths.raw_path, paths.normalized_path)
        profile = self.diarization_service.enroll_speaker(session, paths.normalized_path, request.label.strip())
        self.session_store.save(session)
        return profile, session

    def rename_speaker(self, session_id: str, speaker_id: str, label: str):
        return self.session_store.rename_speaker(session_id, speaker_id, label)

    def ingest_live_chunk(self, session_id: str, request: LiveChunkRequest) -> tuple[TranscriptResult, LiveSession]:
        session = self.get_session(session_id)
        extension = _suffix_for_mime(request.mime_type)
        if extension == ".bin":
            extension = _suffix_for_bytes(request.raw_bytes)

        raw_path = self.session_store.chunk_path(session_id, request.sequence, extension)
        normalized_path = self.session_store.chunk_path(session_id, request.sequence, ".normalized.wav")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(request.raw_bytes)

        normalize_audio(raw_path, normalized_path)
        duration_seconds = probe_duration_seconds(normalized_path)
        speech_windows = self.diarization_service.detect_speech(
            normalized_path,
            offset_seconds=request.options.offset_seconds,
        )
        if speech_windows == []:
            result = TranscriptResult(
                engine_name=self.engine.name,
                segments=[],
                speakers=list(session.speakers.values()),
                duration_seconds=duration_seconds,
                warnings=["No speech detected in the latest audio chunk."],
            )
        else:
            effective_options = self.context_refinement_service.build_live_options(session, request.options)
            result = self.engine.transcribe_live_chunk(str(normalized_path), effective_options, session)
        result = self.diarization_service.process_live_result(
            session,
            normalized_path,
            result,
            request.options,
            speech_windows=speech_windows,
        )
        plan = self.context_refinement_service.refine_live_result(session, result, request.options)
        plan.result = self.post_processing_service.refine_live_result(
            session,
            plan.result,
            request.options,
            replace_tail_count=plan.replace_tail_count,
        )
        session = self.session_store.apply_live_result(
            session,
            request.sequence,
            duration_seconds,
            plan.result,
            replace_tail_count=plan.replace_tail_count,
        )
        return result, session

    def status(self) -> dict[str, object]:
        return {
            "chunkMillis": self.settings.chunk_millis,
            "minChunkMillis": self.MIN_CHUNK_MILLIS,
            "maxChunkMillis": self.MAX_CHUNK_MILLIS,
            "maxUploadMb": self.settings.max_upload_mb,
            "mimeFallbackEnabled": True,
            "voiceActivityDetectionEnabled": self.settings.enable_vad,
            "contextLinkingEnabled": self.context_refinement_service.enabled,
            "postProcessingDefaultEnabled": self.settings.enable_post_processing,
        }

    def _enforce_upload_limit(self, byte_length: int) -> None:
        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        if byte_length > max_bytes:
            raise ValueError(f"Upload exceeds {self.settings.max_upload_mb} MB limit.")

    def _normalize_chunk_millis(self, value: int) -> int:
        normalized = int(value)
        return max(self.MIN_CHUNK_MILLIS, min(self.MAX_CHUNK_MILLIS, normalized))


def _suffix_for_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix else ".bin"


def _suffix_for_mime(mime_type: str) -> str:
    normalized = mime_type.strip().lower()
    if not normalized:
        return ".bin"
    if "wav" in normalized:
        return ".wav"
    if "webm" in normalized:
        return ".webm"
    if "ogg" in normalized:
        return ".ogg"
    if "mpeg" in normalized or "mp3" in normalized:
        return ".mp3"
    if "mp4" in normalized or "m4a" in normalized or "aac" in normalized:
        return ".m4a"
    return ".bin"


def _suffix_for_bytes(raw_chunk: bytes) -> str:
    if raw_chunk.startswith(b"RIFF") and raw_chunk[8:12] == b"WAVE":
        return ".wav"
    if raw_chunk.startswith(b"OggS"):
        return ".ogg"
    if raw_chunk.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    if raw_chunk[4:8] in {b"ftyp", b"moov", b"moof"}:
        return ".m4a"
    if raw_chunk.startswith(b"ID3") or (len(raw_chunk) > 2 and raw_chunk[0] == 0xFF and (raw_chunk[1] & 0xE0) == 0xE0):
        return ".mp3"
    return ".bin"
