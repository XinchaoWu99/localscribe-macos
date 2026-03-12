from __future__ import annotations

from pathlib import Path
import re

from ..audio import apply_volume_gain, audio_level_stats, normalize_audio, probe_duration_seconds
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
    LIVE_VAD_FALLBACK_RMS_NORMALIZED = 0.0025
    LIVE_VAD_FALLBACK_PEAK_NORMALIZED = 0.025
    LOW_INPUT_WARNING_RMS_NORMALIZED = 0.0015
    LOW_INPUT_WARNING_PEAK_NORMALIZED = 0.015
    LOW_INPUT_WARNING = "Input level is very low. Check the selected microphone or audio source."
    QUIET_INPUT_BOOST_WARNING = "Boosted a very quiet live input before transcription."
    LIVE_TURN_END_SILENCE_SECONDS = 0.55
    LIVE_SENTENCE_END_SILENCE_SECONDS = 0.22
    LIVE_AUTO_GAIN_TARGET_PEAK_NORMALIZED = 0.12
    LIVE_AUTO_GAIN_MAX_MULTIPLIER = 45.0

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

    def rename_session(self, session_id: str, title: str | None) -> LiveSession:
        return self.session_store.rename_session(session_id, title)

    def update_segment_text(self, session_id: str, segment_id: str, text: str):
        return self.session_store.update_segment_text(session_id, segment_id, text)

    def clear_sessions(self, *, session_type: str | None = None, exclude_session_id: str | None = None) -> int:
        return self.session_store.clear(session_type=session_type, exclude_session_id=exclude_session_id)

    def update_live_settings(self, *, chunk_millis: int | None = None) -> dict[str, object]:
        if chunk_millis is not None:
            self.settings.chunk_millis = self._normalize_chunk_millis(chunk_millis)
        return self.status()

    def transcribe_upload(self, request: UploadTranscriptionRequest) -> tuple[TranscriptResult, LiveSession]:
        self._enforce_upload_limit(len(request.raw_bytes))
        self.post_processing_service.prepare_backend(request.options)
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
        self.post_processing_service.prepare_backend(request.options)
        extension = _suffix_for_mime(request.mime_type)
        if extension == ".bin":
            extension = _suffix_for_bytes(request.raw_bytes)

        raw_path = self.session_store.chunk_path(session_id, request.sequence, extension)
        normalized_path = self.session_store.chunk_path(session_id, request.sequence, ".normalized.wav")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(request.raw_bytes)

        normalize_audio(raw_path, normalized_path)
        duration_seconds = probe_duration_seconds(normalized_path)
        chunk_end_seconds = request.options.offset_seconds + duration_seconds
        level_stats = audio_level_stats(normalized_path)
        boost_applied = self._boost_quiet_live_audio(normalized_path, level_stats)
        if boost_applied:
            level_stats = audio_level_stats(normalized_path)
        speech_windows = self.diarization_service.detect_speech(
            normalized_path,
            offset_seconds=request.options.offset_seconds,
        )
        if speech_windows == []:
            if self._should_bypass_live_vad(level_stats):
                effective_options = self.context_refinement_service.build_live_options(session, request.options)
                result = self.engine.transcribe_live_chunk(str(normalized_path), effective_options, session)
                result.warnings = list(result.warnings) + [
                    "Live speech fallback used because browser audio was below the default VAD gate.",
                ]
                speech_windows = None
            else:
                warnings = ["No speech detected in the latest audio chunk."]
                if self._is_low_input(level_stats):
                    warnings.insert(0, self.LOW_INPUT_WARNING)
                result = TranscriptResult(
                    engine_name=self.engine.name,
                    segments=[],
                    speakers=list(session.speakers.values()),
                    duration_seconds=duration_seconds,
                    warnings=warnings,
                )
        else:
            effective_options = self.context_refinement_service.build_live_options(session, request.options)
            result = self.engine.transcribe_live_chunk(str(normalized_path), effective_options, session)
        if boost_applied:
            result.warnings = [self.QUIET_INPUT_BOOST_WARNING, *result.warnings]
        result = self.diarization_service.process_live_result(
            session,
            normalized_path,
            result,
            request.options,
            speech_windows=speech_windows,
        )
        plan = self.context_refinement_service.refine_live_result(session, result, request.options)
        post_process_plan = self.post_processing_service.refine_live_result(
            session,
            plan.result,
            request.options,
            replace_tail_count=plan.replace_tail_count,
        )
        plan.result = post_process_plan.result
        plan.replace_tail_count = post_process_plan.replace_tail_count
        current_chunk_segments = post_process_plan.result.segments
        corrected_tail_segments: list = []
        if post_process_plan.replacement_segments is not None:
            current_count = len(post_process_plan.result.segments)
            if current_count > 0:
                corrected_tail_segments = post_process_plan.replacement_segments[:-current_count]
                current_chunk_segments = post_process_plan.replacement_segments[-current_count:]
            else:
                corrected_tail_segments = list(post_process_plan.replacement_segments)
                current_chunk_segments = []

        finalized_segments, draft_segments, visible_segments = self._segment_live_caption_flow(
            session,
            post_process_plan.result.__class__(
                engine_name=post_process_plan.result.engine_name,
                segments=list(current_chunk_segments),
                speakers=post_process_plan.result.speakers,
                duration_seconds=post_process_plan.result.duration_seconds,
                detected_language=post_process_plan.result.detected_language,
                warnings=list(post_process_plan.result.warnings),
            ),
            speech_windows=speech_windows,
            chunk_end_seconds=chunk_end_seconds,
        )
        plan.result.segments = visible_segments
        session = self.session_store.apply_live_result(
            session,
            request.sequence,
            duration_seconds,
            plan.result,
            draft_segments=draft_segments,
            replace_tail_count=plan.replace_tail_count,
            replacement_segments=[*corrected_tail_segments, *finalized_segments],
        )
        return plan.result, session

    def status(self) -> dict[str, object]:
        return {
            "chunkMillis": self.settings.chunk_millis,
            "minChunkMillis": self.MIN_CHUNK_MILLIS,
            "maxChunkMillis": self.MAX_CHUNK_MILLIS,
            "maxUploadMb": self.settings.max_upload_mb,
            "mimeFallbackEnabled": True,
            "voiceActivityDetectionEnabled": self.settings.enable_vad,
            "liveVadFallbackEnabled": True,
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

    def _should_bypass_live_vad(self, level_stats: dict[str, float]) -> bool:
        return (
            level_stats.get("rmsNormalized", 0.0) >= self.LIVE_VAD_FALLBACK_RMS_NORMALIZED
            or level_stats.get("peakNormalized", 0.0) >= self.LIVE_VAD_FALLBACK_PEAK_NORMALIZED
        )

    def _is_low_input(self, level_stats: dict[str, float]) -> bool:
        return (
            level_stats.get("rmsNormalized", 0.0) < self.LOW_INPUT_WARNING_RMS_NORMALIZED
            and level_stats.get("peakNormalized", 0.0) < self.LOW_INPUT_WARNING_PEAK_NORMALIZED
        )

    def _boost_quiet_live_audio(self, path: Path, level_stats: dict[str, float]) -> bool:
        peak = level_stats.get("peakNormalized", 0.0)
        if peak <= 0.0:
            return False
        if peak >= self.LIVE_VAD_FALLBACK_PEAK_NORMALIZED:
            return False

        multiplier = min(
            self.LIVE_AUTO_GAIN_MAX_MULTIPLIER,
            self.LIVE_AUTO_GAIN_TARGET_PEAK_NORMALIZED / peak,
        )
        if multiplier <= 1.5:
            return False

        apply_volume_gain(path, multiplier)
        return True

    def _segment_live_caption_flow(
        self,
        session: LiveSession,
        result: TranscriptResult,
        *,
        speech_windows,
        chunk_end_seconds: float,
    ) -> tuple[list, list, list]:
        finalized_segments: list = []
        draft_segments = [self._clone_segment(segment) for segment in session.draft_segments]
        pending = draft_segments[-1] if draft_segments else None
        visible_segments: list = []

        incoming_segments = [self._clone_segment(segment, is_final=False) for segment in result.segments if segment.text.strip()]
        for incoming in incoming_segments:
            if pending is None:
                pending = incoming
                continue

            if self._can_continue_live_turn(pending, incoming):
                pending = self._merge_live_turn(pending, incoming)
                continue

            finalized_segments.append(self._finalize_segment(pending))
            pending = incoming

        draft_segments = [pending] if pending is not None else []

        if not incoming_segments and draft_segments and self._should_finalize_live_turn(
            draft_segments[-1],
            speech_windows=speech_windows,
            chunk_end_seconds=chunk_end_seconds,
        ):
            finalized_segments.append(self._finalize_segment(draft_segments[-1]))
            draft_segments = []
        elif draft_segments and self._should_finalize_live_turn(
            draft_segments[-1],
            speech_windows=speech_windows,
            chunk_end_seconds=chunk_end_seconds,
        ):
            finalized_segments.append(self._finalize_segment(draft_segments[-1]))
            draft_segments = []

        visible_segments = [*finalized_segments, *[self._clone_segment(segment, is_final=False) for segment in draft_segments]]
        return finalized_segments, draft_segments, visible_segments

    def _should_finalize_live_turn(self, segment, *, speech_windows, chunk_end_seconds: float) -> bool:
        if not segment.text.strip():
            return False
        if speech_windows == []:
            return True
        if speech_windows is None:
            return _looks_sentence_complete(segment.text)

        trailing_silence = max(0.0, chunk_end_seconds - max(window.end for window in speech_windows))
        if trailing_silence >= self.LIVE_TURN_END_SILENCE_SECONDS:
            return True
        if trailing_silence >= self.LIVE_SENTENCE_END_SILENCE_SECONDS and _looks_sentence_complete(segment.text):
            return True
        return False

    def _merge_live_turn(self, current, incoming):
        merged = self._clone_segment(current, is_final=False)
        merged.end = max(current.end, incoming.end)
        merged.text = _merge_live_text(current.text, incoming.text)
        merged.words = [*current.words, *incoming.words]
        confidence_values = [value for value in (current.confidence, incoming.confidence) if value is not None]
        merged.confidence = sum(confidence_values) / len(confidence_values) if confidence_values else None
        merged.speaker_id = incoming.speaker_id or current.speaker_id
        merged.speaker_name = incoming.speaker_name or current.speaker_name
        return merged

    def _can_continue_live_turn(self, current, incoming) -> bool:
        turn_segmenter = getattr(self.diarization_service, "turn_segmenter", None)
        if turn_segmenter is not None and hasattr(turn_segmenter, "can_merge"):
            return turn_segmenter.can_merge(current, incoming)
        return (
            (not current.speaker_id or not incoming.speaker_id or current.speaker_id == incoming.speaker_id)
            and max(0.0, incoming.start - current.end) <= 0.85
        )

    def _finalize_segment(self, segment):
        finalized = self._clone_segment(segment, is_final=True)
        finalized.source = "live"
        return finalized

    def _clone_segment(self, segment, *, is_final=None):
        return segment.__class__(
            segment_id=segment.segment_id,
            start=segment.start,
            end=segment.end,
            text=segment.text,
            confidence=segment.confidence,
            speaker_id=segment.speaker_id,
            speaker_name=segment.speaker_name,
            is_final=segment.is_final if is_final is None else is_final,
            source=segment.source,
            manually_edited=segment.manually_edited,
            edited_at=segment.edited_at,
            words=list(segment.words),
        )


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


_SENTENCE_END_RE = re.compile(r'[.!?]["\')\]]?\s*$')


def _looks_sentence_complete(text: str) -> bool:
    return bool(_SENTENCE_END_RE.search(text.strip()))


def _merge_live_text(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if left.endswith((" ", "\n")):
        return f"{left}{right}"
    if right.startswith((",", ".", "!", "?", ";", ":", "'", '"')):
        return f"{left}{right}"
    return f"{left} {right}"
