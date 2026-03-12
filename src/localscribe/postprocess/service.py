from __future__ import annotations

from dataclasses import dataclass
import difflib
import importlib
import json
import re
import threading
from typing import Protocol

import httpx

from ..models import LiveSession, SegmentWord, TranscriptResult, TranscriptSegment, TranscriptionOptions

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


class PostProcessorBackend(Protocol):
    def status(self) -> dict[str, object]: ...

    def correct(self, prompt: str) -> str: ...


@dataclass(slots=True)
class SegmentCorrection:
    segment_id: str
    text: str


@dataclass(slots=True)
class PostProcessingPlan:
    result: TranscriptResult
    replace_tail_count: int = 0
    replacement_segments: list[TranscriptSegment] | None = None


@dataclass(frozen=True, slots=True)
class PostProcessorBackendOption:
    backend_id: str
    label: str
    description: str
    default_model: str | None = None
    model_placeholder: str = ""


class NoOpPostProcessorBackend:
    def status(self) -> dict[str, object]:
        return {
            "enabled": False,
            "ready": False,
            "backend": "none",
            "model": None,
            "warning": None,
        }

    def correct(self, prompt: str) -> str:
        raise RuntimeError("Post-processing backend is disabled.")


class OllamaPostProcessorBackend:
    def __init__(self, base_url: str, model: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._last_warning: str | None = None

    def status(self) -> dict[str, object]:
        ready = self._probe()
        return {
            "enabled": True,
            "ready": ready,
            "backend": "ollama",
            "model": self.model,
            "warning": self._last_warning,
        }

    def correct(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": 0,
            },
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a transcript cleanup engine. Correct punctuation, casing, and obvious entity spelling "
                        "only when strongly supported by context. Do not invent content, do not summarize, do not "
                        "change the speaker structure, and return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
            self._last_warning = None
            data = response.json()
        except Exception as exc:
            self._last_warning = str(exc)
            raise RuntimeError(f"Ollama post-processing failed: {exc}") from exc

        message = data.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama post-processing returned an unexpected payload.")
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("Ollama post-processing returned an empty response.")
        return content

    def _probe(self) -> bool:
        try:
            with httpx.Client(timeout=min(self.timeout_seconds, 2.5)) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
            self._last_warning = None
            return True
        except Exception as exc:
            self._last_warning = str(exc)
            return False


class MLXPostProcessorBackend:
    def __init__(self, model: str, timeout_seconds: float) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._loaded = False
        self._load_error: str | None = None
        self._model = None
        self._tokenizer = None
        self._generate = None

    def status(self) -> dict[str, object]:
        ready = self._can_import()
        return {
            "enabled": True,
            "ready": ready,
            "backend": "mlx",
            "model": self.model,
            "warning": self._load_error,
        }

    def correct(self, prompt: str) -> str:
        if not self._ensure_loaded():
            raise RuntimeError(self._load_error or "MLX post-processing is not available.")

        assert self._generate is not None
        try:
            response = self._generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                max_tokens=384,
                temp=0.0,
                verbose=False,
            )
        except TypeError:
            response = self._generate(
                self._model,
                self._tokenizer,
                prompt,
                max_tokens=384,
                temp=0.0,
                verbose=False,
            )
        except Exception as exc:
            self._load_error = str(exc)
            raise RuntimeError(f"MLX post-processing failed: {exc}") from exc

        if not isinstance(response, str) or not response.strip():
            raise RuntimeError("MLX post-processing returned an empty response.")
        return response

    def _can_import(self) -> bool:
        try:
            importlib.import_module("mlx_lm")
            self._load_error = None
            return True
        except Exception as exc:
            self._load_error = str(exc)
            return False

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return True

        with self._lock:
            if self._loaded:
                return True
            try:
                mlx_lm = importlib.import_module("mlx_lm")
                load = getattr(mlx_lm, "load")
                generate = getattr(mlx_lm, "generate")
                self._model, self._tokenizer = load(self.model)
                self._generate = generate
                self._loaded = True
                self._load_error = None
                return True
            except Exception as exc:
                self._load_error = str(exc)
                return False


class LocalPostProcessingService:
    BACKEND_OPTIONS: tuple[PostProcessorBackendOption, ...] = (
        PostProcessorBackendOption(
            backend_id="none",
            label="Cleanup off",
            description="Skip the local cleanup pass and keep the raw transcript stitching only.",
            default_model=None,
            model_placeholder="No model needed",
        ),
        PostProcessorBackendOption(
            backend_id="ollama",
            label="Ollama",
            description="Use a local Ollama chat model after each chunk for punctuation and entity cleanup.",
            default_model="qwen2.5:3b-instruct",
            model_placeholder="qwen2.5:3b-instruct",
        ),
        PostProcessorBackendOption(
            backend_id="mlx",
            label="MLX",
            description="Use an MLX model already available on this Mac for an on-device cleanup pass.",
            default_model="mlx-community/Qwen2.5-3B-Instruct-4bit",
            model_placeholder="mlx-community/Qwen2.5-3B-Instruct-4bit",
        ),
    )

    def __init__(
        self,
        *,
        enabled: bool = False,
        backend_name: str = "none",
        model: str | None = None,
        timeout_seconds: float = 6.0,
        recent_segments: int = 4,
        max_context_chars: int = 600,
        ollama_base_url: str = "http://127.0.0.1:11434",
        backend_override: PostProcessorBackend | None = None,
    ) -> None:
        self.enabled = enabled
        self.backend_name = backend_name.strip().lower() or "none"
        self.model = (model or "").strip() or None
        self.timeout_seconds = timeout_seconds
        self.recent_segments = recent_segments
        self.max_context_chars = max_context_chars
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self._backend_override = backend_override
        self._backend_cache: dict[tuple[str, str | None], PostProcessorBackend] = {}
        self._last_warning: str | None = None

    def status(self) -> dict[str, object]:
        backend_name, model = self._resolve_selection()
        backend_status = self._backend_for_selection(backend_name, model).status()
        warning = backend_status.get("warning") or self._last_warning
        return {
            "enabled": backend_name != "none",
            "backend": backend_status.get("backend", self.backend_name),
            "ready": bool(backend_status.get("ready", False)),
            "model": backend_status.get("model", model),
            "warning": warning,
            "defaultEnabled": self.enabled,
            "timeoutSeconds": self.timeout_seconds,
        }

    def catalog(self) -> dict[str, object]:
        backends = []
        ollama_models = self._ollama_installed_models()
        for option in self.BACKEND_OPTIONS:
            resolved_model = self._default_model_for_backend(option.backend_id)
            backend_status = self._backend_for_selection(option.backend_id, resolved_model).status()
            suggested_models: list[str] = []
            if option.backend_id == "ollama":
                if option.default_model:
                    suggested_models.append(option.default_model)
                for model_name in ollama_models:
                    if model_name not in suggested_models:
                        suggested_models.append(model_name)
            elif option.default_model:
                suggested_models.append(option.default_model)

            backends.append(
                {
                    "id": option.backend_id,
                    "label": option.label,
                    "description": option.description,
                    "ready": bool(backend_status.get("ready", option.backend_id == "none")),
                    "warning": backend_status.get("warning"),
                    "defaultModel": resolved_model,
                    "modelPlaceholder": option.model_placeholder,
                    "suggestedModels": suggested_models,
                }
            )

        return {
            "defaultEnabled": self.enabled,
            "defaultBackend": self.backend_name,
            "defaultModel": self.model,
            "backends": backends,
        }

    def refine_live_result(
        self,
        session: LiveSession,
        result: TranscriptResult,
        options: TranscriptionOptions,
        *,
        replace_tail_count: int = 0,
    ) -> PostProcessingPlan:
        if not self._should_process(options, result):
            return PostProcessingPlan(result=result, replace_tail_count=replace_tail_count)

        rewrite_tail = self._rewrite_tail_window(session, trim_tail=replace_tail_count)
        recent_context = self._recent_context(session, trim_tail=replace_tail_count + len(rewrite_tail))
        current_segments = [_clone_segment(segment) for segment in result.segments]
        rewrite_segments = [_clone_segment(segment) for segment in rewrite_tail]
        combined_segments = rewrite_segments + current_segments
        self._apply_corrections(combined_segments, recent_context, options)
        result.segments = combined_segments[len(rewrite_segments) :]

        if not rewrite_segments:
            return PostProcessingPlan(result=result, replace_tail_count=replace_tail_count)

        return PostProcessingPlan(
            result=result,
            replace_tail_count=replace_tail_count + len(rewrite_segments),
            replacement_segments=combined_segments,
        )

    def refine_file_result(self, result: TranscriptResult, options: TranscriptionOptions) -> TranscriptResult:
        if not self._should_process(options, result):
            return result

        self._apply_corrections(result.segments, recent_context=None, options=options)
        return result

    def _apply_corrections(
        self,
        segments: list[TranscriptSegment],
        recent_context: str | None,
        options: TranscriptionOptions,
    ) -> None:
        prompt = _build_prompt(segments, recent_context)
        try:
            backend_name, model = self._resolve_selection(options)
            backend = self._backend_for_selection(backend_name, model)
            raw_response = backend.correct(prompt)
            corrections = _parse_corrections(raw_response)
        except Exception as exc:
            self._last_warning = str(exc)
            return

        _apply_corrections(segments, corrections)
        self._last_warning = None

    def _should_process(self, options: TranscriptionOptions, result: TranscriptResult) -> bool:
        if not options.post_process:
            return False
        if not result.segments:
            return False
        backend_name, _ = self._resolve_selection(options)
        return backend_name != "none"

    def _recent_context(self, session: LiveSession, *, trim_tail: int = 0) -> str | None:
        segments = session.segments[:-trim_tail] if trim_tail > 0 else session.segments
        texts = [segment.text.strip() for segment in segments if segment.text.strip()]
        if not texts:
            return None

        joined = " ".join(texts[-self.recent_segments :]).strip()
        if len(joined) <= self.max_context_chars:
            return joined
        return joined[-self.max_context_chars :].lstrip()

    def _rewrite_tail_window(self, session: LiveSession, *, trim_tail: int = 0) -> list[TranscriptSegment]:
        if self.recent_segments <= 0:
            return []

        segments = session.segments[:-trim_tail] if trim_tail > 0 else session.segments
        if not segments:
            return []

        rewrite_tail: list[TranscriptSegment] = []
        for segment in reversed(segments):
            if segment.manually_edited:
                break
            rewrite_tail.append(segment)
            if len(rewrite_tail) >= self.recent_segments:
                break
        rewrite_tail.reverse()
        return rewrite_tail

    def _resolve_selection(self, options: TranscriptionOptions | None = None) -> tuple[str, str | None]:
        requested_backend = self.backend_name
        requested_model = self.model
        if options is not None:
            if options.post_process_backend is not None:
                requested_backend = options.post_process_backend
            if options.post_process_model is not None:
                requested_model = options.post_process_model
        backend_name = (requested_backend or "none").strip().lower() or "none"
        model = self._default_model_for_backend(backend_name, requested_model)
        return backend_name, model

    def _default_model_for_backend(self, backend_name: str, requested_model: str | None = None) -> str | None:
        model = (requested_model or "").strip() or None
        if model is not None:
            return model
        for option in self.BACKEND_OPTIONS:
            if option.backend_id == backend_name:
                return option.default_model
        return None

    def _backend_for_selection(self, backend_name: str, model: str | None) -> PostProcessorBackend:
        if backend_name == "none":
            return NoOpPostProcessorBackend()
        cache_key = (backend_name, model)
        cached = self._backend_cache.get(cache_key)
        if cached is not None:
            return cached

        if self._backend_override is not None and backend_name == self.backend_name and model == self._default_model_for_backend(self.backend_name, self.model):
            backend = self._backend_override
        elif backend_name == "ollama":
            backend = OllamaPostProcessorBackend(self.ollama_base_url, model or "qwen2.5:3b-instruct", self.timeout_seconds)
        elif backend_name == "mlx":
            backend = MLXPostProcessorBackend(model or "mlx-community/Qwen2.5-3B-Instruct-4bit", self.timeout_seconds)
        else:
            backend = NoOpPostProcessorBackend()
        self._backend_cache[cache_key] = backend
        return backend

    def _ollama_installed_models(self) -> list[str]:
        try:
            with httpx.Client(timeout=min(self.timeout_seconds, 2.5)) as client:
                response = client.get(f"{self.ollama_base_url}/api/tags")
                response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        models: list[str] = []
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            return models
        for entry in raw_models:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            if name and name not in models:
                models.append(name)
        return models


def _build_prompt(segments: list[TranscriptSegment], recent_context: str | None) -> str:
    payload = {
        "task": (
            "Correct punctuation, casing, and obvious proper nouns when strongly supported by the context. "
            "Preserve meaning, order, and speaker boundaries. Return JSON only."
        ),
        "recentContext": recent_context,
        "segments": [
            {
                "segmentId": segment.segment_id,
                "speakerName": segment.speaker_name,
                "text": segment.text,
            }
            for segment in segments
        ],
        "outputSchema": {
            "segments": [
                {
                    "segmentId": "same as input",
                    "text": "corrected text only",
                }
            ]
        },
    }
    return json.dumps(payload, ensure_ascii=True)


def _parse_corrections(raw_response: str) -> list[SegmentCorrection]:
    start = raw_response.find("{")
    end = raw_response.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("Post-processing response did not contain JSON.")

    payload = json.loads(raw_response[start : end + 1])
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise RuntimeError("Post-processing response did not contain segment corrections.")

    corrections: list[SegmentCorrection] = []
    for entry in raw_segments:
        if not isinstance(entry, dict):
            continue
        segment_id = str(entry.get("segmentId", "")).strip()
        text = str(entry.get("text", "")).strip()
        if not segment_id or not text:
            continue
        corrections.append(SegmentCorrection(segment_id=segment_id, text=text))
    return corrections


def _apply_corrections(segments: list[TranscriptSegment], corrections: list[SegmentCorrection]) -> None:
    correction_map = {correction.segment_id: correction.text for correction in corrections}
    for segment in segments:
        corrected = correction_map.get(segment.segment_id)
        if corrected is None:
            continue
        if not _is_safe_correction(segment.text, corrected):
            continue
        keep_words = _preserves_word_sequence(segment.text, corrected)
        segment.text = corrected
        if not keep_words:
            segment.words = []


def _is_safe_correction(original: str, corrected: str) -> bool:
    original_text = original.strip()
    corrected_text = corrected.strip()
    if not corrected_text:
        return False
    if original_text == corrected_text:
        return True

    original_tokens = _normalized_tokens(original_text)
    corrected_tokens = _normalized_tokens(corrected_text)
    if not original_tokens or not corrected_tokens:
        return False
    if abs(len(corrected_tokens) - len(original_tokens)) > max(3, len(original_tokens) // 2):
        return False

    similarity = difflib.SequenceMatcher(None, " ".join(original_tokens), " ".join(corrected_tokens)).ratio()
    return similarity >= 0.58


def _preserves_word_sequence(original: str, corrected: str) -> bool:
    return _normalized_tokens(original) == _normalized_tokens(corrected)


def _normalized_tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def _clone_segment(segment: TranscriptSegment) -> TranscriptSegment:
    return TranscriptSegment(
        segment_id=segment.segment_id,
        start=segment.start,
        end=segment.end,
        text=segment.text,
        confidence=segment.confidence,
        speaker_id=segment.speaker_id,
        speaker_name=segment.speaker_name,
        is_final=segment.is_final,
        source=segment.source,
        manually_edited=segment.manually_edited,
        edited_at=segment.edited_at,
        words=[
            SegmentWord(
                start=word.start,
                end=word.end,
                text=word.text,
                confidence=word.confidence,
            )
            for word in segment.words
        ],
    )
