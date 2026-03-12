from __future__ import annotations

from pathlib import Path

from localscribe.config import Settings
from localscribe.engines.whisperkit_runtime import WhisperKitRuntime


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        whisper_model="tiny",
        whisperkit_binary="/bin/echo",
        whisperkit_autostart=True,
    )


def test_model_catalog_marks_managed_installations(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    model_dir = settings.whisperkit_models_dir / "openai_whisper-base"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "weights.bin").write_text("ok", encoding="utf-8")

    runtime = WhisperKitRuntime(settings)
    catalog = runtime.model_catalog()

    base_model = next(model for model in catalog["models"] if model["id"] == "base")
    tiny_model = next(model for model in catalog["models"] if model["id"] == "tiny")

    assert catalog["supported"] is True
    assert base_model["installed"] is True
    assert base_model["installSource"] == "managed-cache"
    assert tiny_model["active"] is True


def test_select_model_restarts_runtime_when_switching(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    model_dir = settings.whisperkit_models_dir / "openai_whisper-small"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "weights.bin").write_text("ok", encoding="utf-8")

    runtime = WhisperKitRuntime(settings)
    calls = {"shutdown": 0, "ensure": 0}

    def fake_shutdown() -> None:
        calls["shutdown"] += 1

    def fake_ensure() -> None:
        calls["ensure"] += 1

    monkeypatch.setattr(runtime, "_shutdown_process_locked", fake_shutdown)
    monkeypatch.setattr(runtime, "ensure_running", fake_ensure)
    monkeypatch.setattr(runtime, "_is_process_alive", lambda: True)
    monkeypatch.setattr(runtime, "is_ready", lambda: True)

    catalog = runtime.select_model("small")

    assert settings.whisper_model == "small"
    assert catalog["activeModel"] == "small"
    assert calls == {"shutdown": 1, "ensure": 1}


def test_selecting_active_model_is_a_noop(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    runtime = WhisperKitRuntime(settings)
    calls = {"shutdown": 0, "ensure": 0}

    monkeypatch.setattr(runtime, "_shutdown_process_locked", lambda: calls.__setitem__("shutdown", calls["shutdown"] + 1))
    monkeypatch.setattr(runtime, "ensure_running", lambda: calls.__setitem__("ensure", calls["ensure"] + 1))

    catalog = runtime.select_model("tiny")

    assert catalog["activeModel"] == "tiny"
    assert calls == {"shutdown": 0, "ensure": 0}
