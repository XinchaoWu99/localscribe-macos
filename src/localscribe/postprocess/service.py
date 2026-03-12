from __future__ import annotations

from dataclasses import dataclass
import difflib
import importlib
import json
import re
import threading
from typing import Protocol

import httpx

from ..models import LiveSession, TranscriptResult, TranscriptSegment, TranscriptionOptions

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


class PostProcessorBackend(Protocol):
    def status(self) -> dict[str, object]: ...

    def correct(self, prompt: str) -> str: ...


@dataclass(slots=True)
class SegmentCorrection:
    segment_id: str
    text: str


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
        self._backend = backend_override or self._build_backend(ollama_base_url)
        self._last_warning: str | None = None

    def status(self) -> dict[str, object]:
        backend_status = self._backend.status()
        warning = backend_status.get("warning") or self._last_warning
        return {
            "enabled": self.enabled and self.backend_name != "none",
            "backend": backend_status.get("backend", self.backend_name),
            "ready": bool(backend_status.get("ready", False)),
            "model": backend_status.get("model", self.model),
            "warning": warning,
            "defaultEnabled": self.enabled,
            "timeoutSeconds": self.timeout_seconds,
        }

    def refine_live_result(
        self,
        session: LiveSession,
        result: TranscriptResult,
        options: TranscriptionOptions,
        *,
        replace_tail_count: int = 0,
    ) -> TranscriptResult:
        if not self._should_process(options, result):
            return result

        recent_context = self._recent_context(session, trim_tail=replace_tail_count)
        self._apply_corrections(result, recent_context)
        return result

    def refine_file_result(self, result: TranscriptResult, options: TranscriptionOptions) -> TranscriptResult:
        if not self._should_process(options, result):
            return result

        self._apply_corrections(result, recent_context=None)
        return result

    def _apply_corrections(self, result: TranscriptResult, recent_context: str | None) -> None:
        prompt = _build_prompt(result.segments, recent_context)
        try:
            raw_response = self._backend.correct(prompt)
            corrections = _parse_corrections(raw_response)
        except Exception as exc:
            self._last_warning = str(exc)
            return

        _apply_corrections(result.segments, corrections)
        self._last_warning = None

    def _should_process(self, options: TranscriptionOptions, result: TranscriptResult) -> bool:
        if not self.enabled or self.backend_name == "none":
            return False
        if not options.post_process:
            return False
        if not result.segments:
            return False
        return True

    def _recent_context(self, session: LiveSession, *, trim_tail: int = 0) -> str | None:
        segments = session.segments[:-trim_tail] if trim_tail > 0 else session.segments
        texts = [segment.text.strip() for segment in segments if segment.text.strip()]
        if not texts:
            return None

        joined = " ".join(texts[-self.recent_segments :]).strip()
        if len(joined) <= self.max_context_chars:
            return joined
        return joined[-self.max_context_chars :].lstrip()

    def _build_backend(self, ollama_base_url: str) -> PostProcessorBackend:
        if self.backend_name == "ollama":
            model = self.model or "qwen2.5:3b-instruct"
            return OllamaPostProcessorBackend(ollama_base_url, model, self.timeout_seconds)
        if self.backend_name == "mlx":
            model = self.model or "mlx-community/Qwen2.5-3B-Instruct-4bit"
            return MLXPostProcessorBackend(model, self.timeout_seconds)
        return NoOpPostProcessorBackend()


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
