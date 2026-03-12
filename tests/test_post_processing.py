from __future__ import annotations

import importlib
import subprocess

import httpx
from localscribe.models import LiveSession, SegmentWord, TranscriptResult, TranscriptSegment, TranscriptionOptions
from localscribe.postprocess import LocalPostProcessingService
from localscribe.postprocess.service import MLXPostProcessorBackend


class FakePostProcessorBackend:
    def __init__(self, response: str, *, ready: bool = True) -> None:
        self.response = response
        self.ready = ready
        self.calls: list[str] = []

    def status(self) -> dict[str, object]:
        return {
            "enabled": True,
            "ready": self.ready,
            "backend": "fake",
            "model": "fake-model",
            "warning": None,
        }

    def correct(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


def test_post_processing_corrects_punctuation_without_dropping_words() -> None:
    backend = FakePostProcessorBackend(
        '{"segments":[{"segmentId":"seg-1","text":"hello, world."}]}'
    )
    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        backend_override=backend,
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-1",
                start=0.0,
                end=1.0,
                text="hello world",
                words=[
                    SegmentWord(start=0.0, end=0.4, text="hello"),
                    SegmentWord(start=0.4, end=1.0, text="world"),
                ],
            )
        ],
        speakers=[],
        duration_seconds=1.0,
    )

    plan = service.refine_live_result(
        LiveSession(session_id="live-1"),
        result,
        TranscriptionOptions(post_process=True, live=True),
    )

    updated = plan.result
    assert updated.segments[0].text == "hello, world."
    assert len(updated.segments[0].words) == 2
    assert plan.replace_tail_count == 0
    assert backend.calls


def test_post_processing_clears_word_alignment_when_tokens_change() -> None:
    backend = FakePostProcessorBackend(
        '{"segments":[{"segmentId":"seg-2","text":"AcmeSoft shipped the patch."}]}'
    )
    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        backend_override=backend,
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-2",
                start=0.0,
                end=1.2,
                text="acme soft shipped the patch",
                words=[
                    SegmentWord(start=0.0, end=0.3, text="acme"),
                    SegmentWord(start=0.3, end=0.6, text="soft"),
                    SegmentWord(start=0.6, end=0.8, text="shipped"),
                    SegmentWord(start=0.8, end=1.0, text="the"),
                    SegmentWord(start=1.0, end=1.2, text="patch"),
                ],
            )
        ],
        speakers=[],
        duration_seconds=1.2,
    )

    updated = service.refine_file_result(result, TranscriptionOptions(post_process=True))

    assert updated.segments[0].text == "AcmeSoft shipped the patch."
    assert updated.segments[0].words == []


def test_post_processing_uses_requested_backend_and_model(monkeypatch) -> None:
    backend = FakePostProcessorBackend(
        '{"segments":[{"segmentId":"seg-3","text":"final sentence."}]}'
    )
    service = LocalPostProcessingService(
        enabled=False,
        backend_name="none",
    )
    selected: dict[str, str | None] = {}

    def fake_backend_for_selection(backend_name: str, model: str | None):
        selected["backend"] = backend_name
        selected["model"] = model
        return backend

    monkeypatch.setattr(service, "_backend_for_selection", fake_backend_for_selection)
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-3",
                start=0.0,
                end=1.0,
                text="final sentence",
            )
        ],
        speakers=[],
        duration_seconds=1.0,
    )

    updated = service.refine_file_result(
        result,
        TranscriptionOptions(
            post_process=True,
            post_process_backend="mlx",
            post_process_model="mlx-community/custom-cleanup-model",
        ),
    )

    assert selected == {
        "backend": "mlx",
        "model": "mlx-community/custom-cleanup-model",
    }
    assert updated.segments[0].text == "final sentence."


def test_mlx_backend_reports_missing_runtime_with_install_hint(monkeypatch) -> None:
    backend = MLXPostProcessorBackend("mlx-community/Qwen2.5-3B-Instruct-4bit", timeout_seconds=6.0)
    original_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "mlx_lm":
            raise ModuleNotFoundError("No module named 'mlx_lm'", name="mlx_lm")
        return original_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    status = backend.status()

    assert status["ready"] is False
    assert "Run uv sync once to add mlx-lm." in str(status["warning"])


def test_post_processing_rewrites_previous_tail_and_current_chunk() -> None:
    backend = FakePostProcessorBackend(
        (
            '{"segments":['
            '{"segmentId":"seg-prev","text":"AcmeSoft launched the update."},'
            '{"segmentId":"seg-new","text":"It reached the beta team yesterday."}'
            "]}"
        )
    )
    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        backend_override=backend,
        recent_segments=2,
    )
    session = LiveSession(
        session_id="live-2",
        segments=[
            TranscriptSegment(
                segment_id="seg-prev",
                start=0.0,
                end=1.5,
                text="acme soft launched the update",
                source="live",
            )
        ],
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-new",
                start=1.5,
                end=3.0,
                text="it reached the beta team yesterday",
                source="live",
            )
        ],
        speakers=[],
        duration_seconds=1.5,
    )

    plan = service.refine_live_result(
        session,
        result,
        TranscriptionOptions(post_process=True, live=True),
    )

    assert plan.replace_tail_count == 1
    assert plan.replacement_segments is not None
    assert [segment.segment_id for segment in plan.replacement_segments] == ["seg-prev", "seg-new"]
    assert plan.replacement_segments[0].text == "AcmeSoft launched the update."
    assert plan.result.segments[0].text == "It reached the beta team yesterday."
    assert backend.calls


def test_prepare_backend_autostarts_ollama(monkeypatch, tmp_path) -> None:
    state = {
        "ready": False,
        "launch_cmd": None,
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"models": []}

    class FakeClient:
        def __init__(self, timeout):  # noqa: ANN001
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def get(self, url: str):  # noqa: ARG002
            if not state["ready"]:
                raise httpx.ConnectError("Connection refused")
            return FakeResponse()

    class FakePopen:
        def __init__(self, cmd, stdout, stderr, text, start_new_session, env):  # noqa: ANN001
            state["launch_cmd"] = cmd
            state["ready"] = True
            self.pid = 2468

        def poll(self):
            return None

        def wait(self, timeout=None):  # noqa: ANN001
            return 0

        def terminate(self):
            return None

        def kill(self):
            return None

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        runtime_dir=tmp_path,
        ollama_binary="/opt/homebrew/bin/ollama",
    )

    status = service.prepare_backend(
        TranscriptionOptions(
            post_process=True,
            post_process_backend="ollama",
            post_process_model="qwen2.5:3b-instruct",
            live=True,
        )
    )

    assert state["launch_cmd"] == ["/opt/homebrew/bin/ollama", "serve"]
    assert status["ready"] is True
    assert status["backend"] == "ollama"


def test_startup_prepares_default_backend(monkeypatch) -> None:
    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        model="qwen2.5:3b-instruct",
    )
    selected: dict[str, str | None] = {}

    def fake_prepare(options=None):  # noqa: ANN001
        backend_name, model = service._resolve_selection(options)
        selected["backend"] = backend_name
        selected["model"] = model
        return {
            "enabled": True,
            "backend": backend_name,
            "ready": True,
            "model": model,
            "warning": None,
        }

    monkeypatch.setattr(service, "prepare_backend", fake_prepare)

    status = service.startup()

    assert selected == {
        "backend": "ollama",
        "model": "qwen2.5:3b-instruct",
    }
    assert status["ready"] is True


def test_post_processing_skips_manually_edited_tail_rewrites() -> None:
    backend = FakePostProcessorBackend(
        (
            '{"segments":['
            '{"segmentId":"seg-prev","text":"AcmeSoft launched the update."},'
            '{"segmentId":"seg-new","text":"It reached the beta team yesterday."}'
            "]}"
        )
    )
    service = LocalPostProcessingService(
        enabled=True,
        backend_name="ollama",
        backend_override=backend,
        recent_segments=2,
    )
    session = LiveSession(
        session_id="live-3",
        segments=[
            TranscriptSegment(
                segment_id="seg-prev",
                start=0.0,
                end=1.5,
                text="AcmeSoft launched the update.",
                source="live",
                manually_edited=True,
                edited_at="2026-03-12T00:00:00+00:00",
            )
        ],
    )
    result = TranscriptResult(
        engine_name="whisperkit-server",
        segments=[
            TranscriptSegment(
                segment_id="seg-new",
                start=1.5,
                end=3.0,
                text="it reached the beta team yesterday",
                source="live",
            )
        ],
        speakers=[],
        duration_seconds=1.5,
    )

    plan = service.refine_live_result(
        session,
        result,
        TranscriptionOptions(post_process=True, live=True),
    )

    assert plan.replace_tail_count == 0
    assert plan.replacement_segments is None
    assert plan.result.segments[0].segment_id == "seg-new"
