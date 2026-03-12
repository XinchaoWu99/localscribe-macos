from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..context import ContextRefinementService
from ..diarization import DiarizationService, DiscussionTurnSegmenter, SileroVoiceActivityDetector
from ..engines import build_engine
from ..engines.base import TranscriptionEngine
from ..postprocess import LocalPostProcessingService
from ..speakers import SpeakerResolver
from ..storage import FileStore, SessionStore
from ..streaming import StreamingService
from ..system_audio import NativeSystemAudioService


@dataclass(slots=True)
class AppServices:
    settings: Settings
    engine: TranscriptionEngine
    session_store: SessionStore
    file_store: FileStore
    speaker_resolver: SpeakerResolver
    diarization_service: DiarizationService
    context_refinement_service: ContextRefinementService
    post_processing_service: LocalPostProcessingService
    streaming_service: StreamingService
    system_audio_service: NativeSystemAudioService
    static_dir: Path

    def startup(self) -> None:
        startup = getattr(self.engine, "startup", None)
        if callable(startup):
            startup()

    def shutdown(self) -> None:
        self.system_audio_service.shutdown()
        self.post_processing_service.shutdown()
        shutdown = getattr(self.engine, "shutdown", None)
        if callable(shutdown):
            shutdown()


def build_services(settings: Settings, static_dir: Path) -> AppServices:
    project_root = Path(__file__).resolve().parents[3]
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.sessions_dir.mkdir(parents=True, exist_ok=True)
    settings.speakers_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)

    engine = build_engine(settings)
    session_store = SessionStore(settings.sessions_dir)
    file_store = FileStore(settings.uploads_dir)
    speaker_resolver = SpeakerResolver(
        model_dir=settings.speakers_dir,
        enabled=settings.enable_speaker_recognition,
        similarity_threshold=settings.speaker_similarity_threshold,
    )
    diarization_service = DiarizationService(
        speaker_resolver=speaker_resolver,
        turn_segmenter=DiscussionTurnSegmenter(
            max_gap_seconds=settings.diarization_turn_gap_seconds,
            max_turn_seconds=settings.diarization_max_turn_seconds,
        ),
        vad=SileroVoiceActivityDetector(settings),
    )
    context_refinement_service = ContextRefinementService(
        enabled=settings.enable_context_linking,
        prompt_segments=settings.context_prompt_segments,
        prompt_max_chars=settings.context_prompt_max_chars,
        merge_gap_seconds=settings.context_merge_gap_seconds,
        merge_max_turn_seconds=settings.context_merge_max_turn_seconds,
    )
    post_processing_service = LocalPostProcessingService(
        enabled=settings.enable_post_processing,
        backend_name=settings.postprocess_backend,
        model=settings.postprocess_model,
        timeout_seconds=settings.postprocess_timeout_seconds,
        recent_segments=settings.postprocess_recent_segments,
        max_context_chars=settings.postprocess_max_context_chars,
        ollama_base_url=settings.ollama_url,
        runtime_dir=settings.runtime_dir,
    )
    streaming_service = StreamingService(
        settings=settings,
        engine=engine,
        session_store=session_store,
        file_store=file_store,
        diarization_service=diarization_service,
        context_refinement_service=context_refinement_service,
        post_processing_service=post_processing_service,
    )
    system_audio_service = NativeSystemAudioService(settings=settings, project_root=project_root)
    return AppServices(
        settings=settings,
        engine=engine,
        session_store=session_store,
        file_store=file_store,
        speaker_resolver=speaker_resolver,
        diarization_service=diarization_service,
        context_refinement_service=context_refinement_service,
        post_processing_service=post_processing_service,
        streaming_service=streaming_service,
        system_audio_service=system_audio_service,
        static_dir=static_dir,
    )
