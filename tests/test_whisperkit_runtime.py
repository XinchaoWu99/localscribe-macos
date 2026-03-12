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


def test_large_v3_turbo_alias_maps_to_recommended_runtime_name(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.whisper_model = "large-v3_turbo"

    runtime = WhisperKitRuntime(settings)
    catalog = runtime.model_catalog()
    command = runtime._build_serve_command(["whisperkit-cli"])

    assert runtime.request_model_name() == "large-v3_turbo"
    assert catalog["activeModel"] == "large-v3-turbo"
    assert command[command.index("--model") + 1] == "large-v3_turbo"


def test_model_catalog_detects_versioned_large_v3_turbo_installation(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    model_dir = (
        settings.whisperkit_models_dir
        / "models"
        / "argmaxinc"
        / "whisperkit-coreml"
        / "openai_whisper-large-v3-v20240930_turbo"
    )
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "AudioEncoder.mlmodelc").mkdir()

    runtime = WhisperKitRuntime(settings)
    catalog = runtime.model_catalog()

    turbo_model = next(model for model in catalog["models"] if model["id"] == "large-v3-turbo")
    assert turbo_model["installed"] is True
    assert turbo_model["installSource"] == "managed-cache"


def test_install_model_uses_runtime_turbo_repo_name(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    settings.whisper_model = "large-v3-turbo"
    runtime = WhisperKitRuntime(settings)
    captured: dict[str, object] = {}

    class DummyProcess:
        pid = 4321

        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return DummyProcess()

    monkeypatch.setattr("localscribe.engines.whisperkit_runtime.subprocess.Popen", fake_popen)

    catalog = runtime.install_model("large-v3-turbo")
    command = captured["command"]

    assert command[command.index("--model") + 1] == "large-v3_turbo"
    assert catalog["installingModel"] == "large-v3-turbo"


def test_model_catalog_detects_unversioned_large_v3_turbo_installation(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    model_dir = settings.whisperkit_models_dir / "openai_whisper-large-v3_turbo"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    runtime = WhisperKitRuntime(settings)
    catalog = runtime.model_catalog()

    turbo_model = next(model for model in catalog["models"] if model["id"] == "large-v3-turbo")
    assert turbo_model["installed"] is True
    assert turbo_model["installSource"] == "managed-cache"


def test_install_status_exposes_progress_and_log_tail(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = WhisperKitRuntime(settings)

    class DummyProcess:
        pid = 9876

        def poll(self):
            return None

    runtime.install_log_path.parent.mkdir(parents=True, exist_ok=True)
    runtime.install_log_path.write_text(
        "\n".join(
            [
                "$ whisperkit-cli transcribe --model large-v3_turbo",
                "Preparing tokenizer download",
                "Downloading model weights 63%",
                "Downloading tokenizer files 81%",
            ]
        ),
        encoding="utf-8",
    )
    runtime._install_process = DummyProcess()
    runtime._installing_model = "large-v3-turbo"

    catalog = runtime.model_catalog()

    assert catalog["installingModel"] == "large-v3-turbo"
    assert catalog["install"]["running"] is True
    assert catalog["install"]["progressPercent"] == 81
    assert catalog["install"]["progressLabel"] == "Downloading tokenizer files 81%"
    assert catalog["install"]["logTail"][-1] == "Downloading tokenizer files 81%"


def test_install_status_falls_back_to_phase_text_without_percent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = WhisperKitRuntime(settings)

    class DummyProcess:
        pid = 9877

        def poll(self):
            return None

    runtime.install_log_path.parent.mkdir(parents=True, exist_ok=True)
    runtime.install_log_path.write_text(
        "\n".join(
            [
                "$ whisperkit-cli transcribe --model large-v3_turbo",
                "Preparing tokenizer download",
                "Downloading model shards",
            ]
        ),
        encoding="utf-8",
    )
    runtime._install_process = DummyProcess()
    runtime._installing_model = "large-v3-turbo"

    status = runtime.status()

    assert status["install"]["running"] is True
    assert "progressPercent" not in status["install"]
    assert status["install"]["progressLabel"] == "Downloading model shards"
