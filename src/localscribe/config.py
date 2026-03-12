from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    engine: str = "auto"
    system_audio_helper_binary: str | None = None
    whisper_server_url: str = "http://127.0.0.1:8080/v1"
    whisper_model: str = "large-v3-turbo"
    whisperkit_binary: str | None = None
    whisperkit_source_dir: Path | None = None
    whisperkit_download_model_path: Path | None = None
    whisperkit_download_tokenizer_path: Path | None = None
    whisperkit_autostart: bool = True
    whisperkit_verbose: bool = False
    whisperkit_startup_timeout_seconds: int = 180
    faster_whisper_model: str = "base"
    faster_whisper_compute_type: str = "int8"
    faster_whisper_cpu_threads: int = 4
    data_dir: Path = Path(".localscribe-data")
    chunk_millis: int = 2200
    max_upload_mb: int = 512
    enable_context_linking: bool = True
    context_prompt_segments: int = 6
    context_prompt_max_chars: int = 480
    context_merge_gap_seconds: float = 1.1
    context_merge_max_turn_seconds: float = 28.0
    enable_post_processing: bool = True
    postprocess_backend: str = "ollama"
    postprocess_model: str | None = "qwen2.5:3b-instruct"
    postprocess_timeout_seconds: float = 6.0
    postprocess_recent_segments: int = 4
    postprocess_max_context_chars: int = 600
    ollama_url: str = "http://127.0.0.1:11434"
    enable_vad: bool = True
    vad_threshold: float = 0.5
    vad_min_speech_ms: int = 250
    vad_min_silence_ms: int = 350
    vad_speech_pad_ms: int = 150
    vad_max_speech_seconds: float = 30.0
    diarization_turn_gap_seconds: float = 0.85
    diarization_max_turn_seconds: float = 18.0
    enable_speaker_recognition: bool = True
    speaker_similarity_threshold: float = 0.73

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("LOCALSCRIBE_DATA_DIR", ".localscribe-data")).expanduser()
        whisperkit_source_dir = _optional_path(os.getenv("LOCALSCRIBE_WHISPERKIT_SOURCE_DIR"))
        whisperkit_download_model_path = _optional_path(os.getenv("LOCALSCRIBE_WHISPERKIT_DOWNLOAD_MODEL_PATH"))
        whisperkit_download_tokenizer_path = _optional_path(
            os.getenv("LOCALSCRIBE_WHISPERKIT_DOWNLOAD_TOKENIZER_PATH")
        )
        return cls(
            host=os.getenv("LOCALSCRIBE_HOST", "127.0.0.1"),
            port=int(os.getenv("LOCALSCRIBE_PORT", "8765")),
            engine=os.getenv("LOCALSCRIBE_ENGINE", "auto"),
            system_audio_helper_binary=os.getenv("LOCALSCRIBE_SYSTEM_AUDIO_HELPER_BINARY") or None,
            whisper_server_url=os.getenv("LOCALSCRIBE_WHISPER_SERVER_URL", "http://127.0.0.1:8080/v1"),
            whisper_model=os.getenv("LOCALSCRIBE_WHISPER_MODEL", "large-v3-turbo"),
            whisperkit_binary=os.getenv("LOCALSCRIBE_WHISPERKIT_BINARY") or None,
            whisperkit_source_dir=whisperkit_source_dir,
            whisperkit_download_model_path=whisperkit_download_model_path,
            whisperkit_download_tokenizer_path=whisperkit_download_tokenizer_path,
            whisperkit_autostart=os.getenv("LOCALSCRIBE_WHISPERKIT_AUTOSTART", "1") not in {"0", "false", "FALSE"},
            whisperkit_verbose=os.getenv("LOCALSCRIBE_WHISPERKIT_VERBOSE", "0") in {"1", "true", "TRUE"},
            whisperkit_startup_timeout_seconds=int(
                os.getenv("LOCALSCRIBE_WHISPERKIT_STARTUP_TIMEOUT_SECONDS", "180")
            ),
            faster_whisper_model=os.getenv("LOCALSCRIBE_FASTER_WHISPER_MODEL", "base"),
            faster_whisper_compute_type=os.getenv("LOCALSCRIBE_FASTER_WHISPER_COMPUTE_TYPE", "int8"),
            faster_whisper_cpu_threads=int(os.getenv("LOCALSCRIBE_FASTER_WHISPER_CPU_THREADS", "4")),
            data_dir=data_dir,
            chunk_millis=int(os.getenv("LOCALSCRIBE_CHUNK_MILLIS", "2200")),
            max_upload_mb=int(os.getenv("LOCALSCRIBE_MAX_UPLOAD_MB", "512")),
            enable_context_linking=os.getenv("LOCALSCRIBE_ENABLE_CONTEXT_LINKING", "1")
            not in {"0", "false", "FALSE"},
            context_prompt_segments=int(os.getenv("LOCALSCRIBE_CONTEXT_PROMPT_SEGMENTS", "6")),
            context_prompt_max_chars=int(os.getenv("LOCALSCRIBE_CONTEXT_PROMPT_MAX_CHARS", "480")),
            context_merge_gap_seconds=float(os.getenv("LOCALSCRIBE_CONTEXT_MERGE_GAP_SECONDS", "1.1")),
            context_merge_max_turn_seconds=float(
                os.getenv("LOCALSCRIBE_CONTEXT_MERGE_MAX_TURN_SECONDS", "28.0")
            ),
            enable_post_processing=os.getenv("LOCALSCRIBE_ENABLE_POST_PROCESSING", "1")
            in {"1", "true", "TRUE"},
            postprocess_backend=os.getenv("LOCALSCRIBE_POSTPROCESS_BACKEND", "ollama"),
            postprocess_model=os.getenv("LOCALSCRIBE_POSTPROCESS_MODEL") or "qwen2.5:3b-instruct",
            postprocess_timeout_seconds=float(os.getenv("LOCALSCRIBE_POSTPROCESS_TIMEOUT_SECONDS", "6.0")),
            postprocess_recent_segments=int(os.getenv("LOCALSCRIBE_POSTPROCESS_RECENT_SEGMENTS", "4")),
            postprocess_max_context_chars=int(os.getenv("LOCALSCRIBE_POSTPROCESS_MAX_CONTEXT_CHARS", "600")),
            ollama_url=os.getenv("LOCALSCRIBE_OLLAMA_URL", "http://127.0.0.1:11434"),
            enable_vad=os.getenv("LOCALSCRIBE_ENABLE_VAD", "1") not in {"0", "false", "FALSE"},
            vad_threshold=float(os.getenv("LOCALSCRIBE_VAD_THRESHOLD", "0.5")),
            vad_min_speech_ms=int(os.getenv("LOCALSCRIBE_VAD_MIN_SPEECH_MS", "250")),
            vad_min_silence_ms=int(os.getenv("LOCALSCRIBE_VAD_MIN_SILENCE_MS", "350")),
            vad_speech_pad_ms=int(os.getenv("LOCALSCRIBE_VAD_SPEECH_PAD_MS", "150")),
            vad_max_speech_seconds=float(os.getenv("LOCALSCRIBE_VAD_MAX_SPEECH_SECONDS", "30.0")),
            diarization_turn_gap_seconds=float(os.getenv("LOCALSCRIBE_DIARIZATION_TURN_GAP_SECONDS", "0.85")),
            diarization_max_turn_seconds=float(os.getenv("LOCALSCRIBE_DIARIZATION_MAX_TURN_SECONDS", "18.0")),
            enable_speaker_recognition=os.getenv("LOCALSCRIBE_ENABLE_SPEAKERS", "1") in {"1", "true", "TRUE"},
            speaker_similarity_threshold=float(
                os.getenv("LOCALSCRIBE_SPEAKER_SIMILARITY_THRESHOLD", "0.73")
            ),
        )

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def speakers_dir(self) -> Path:
        return self.data_dir / "speakers"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def runtime_dir(self) -> Path:
        return self.data_dir / "runtime"

    @property
    def whisperkit_models_dir(self) -> Path:
        if self.whisperkit_download_model_path is not None:
            return self.whisperkit_download_model_path
        return self.data_dir / "models" / "whisperkit-coreml" / "models"

    @property
    def whisperkit_tokenizers_dir(self) -> Path:
        if self.whisperkit_download_tokenizer_path is not None:
            return self.whisperkit_download_tokenizer_path
        return self.data_dir / "models" / "whisperkit-coreml" / "tokenizers"


def _optional_path(raw_value: str | None) -> Path | None:
    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value:
        return None
    return Path(value).expanduser()
