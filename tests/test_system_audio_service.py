from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from localscribe.config import Settings
from localscribe.system_audio import NativeSystemAudioService


def test_system_audio_status_reports_build_command_when_binary_missing(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / ".localscribe-data")
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    service = NativeSystemAudioService(settings=settings, project_root=tmp_path)

    status = service.status(session_id="abc123", language="en", prompt="Quarterly review", diarize=True, chunk_millis=2600)

    assert status["available"] is False
    assert "swift build -c release" in str(status["buildCommand"])
    assert "--session-id" in str(status["launchCommand"])
    assert "abc123" in str(status["launchCommand"])
    assert "build it automatically" in str(status["warning"])


def test_system_audio_command_uses_current_server_and_options(tmp_path: Path) -> None:
    binary_path = tmp_path / "helper-bin"
    binary_path.write_text("", encoding="utf-8")
    binary_path.chmod(0o755)
    settings = Settings(
        host="0.0.0.0",
        port=9001,
        system_audio_helper_binary=str(binary_path),
        data_dir=tmp_path / ".localscribe-data",
    )
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    service = NativeSystemAudioService(settings=settings, project_root=tmp_path)

    command = service.command(
        session_id="session-1",
        language="en",
        prompt="Atlas and WhisperKit",
        diarize=False,
        chunk_millis=3100,
    )

    assert command[:4] == [str(binary_path), "--server", "http://0.0.0.0:9001", "--session-id"]
    assert "--language" in command
    assert "--prompt" in command
    assert "--chunk-ms" in command
    assert "--no-diarize" in command


def test_system_audio_start_capture_builds_helper_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(data_dir=tmp_path / ".localscribe-data")
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    package_dir = tmp_path / "native" / "system-audio-helper"
    package_dir.mkdir(parents=True, exist_ok=True)
    service = NativeSystemAudioService(settings=settings, project_root=tmp_path)

    recorded: dict[str, object] = {}

    def fake_run(cmd, cwd, env, capture_output, text):  # noqa: ANN001
        recorded["build_cmd"] = cmd
        recorded["build_cwd"] = cwd
        binary_path = service.binary_path
        binary_path.parent.mkdir(parents=True, exist_ok=True)
        binary_path.write_text("", encoding="utf-8")
        binary_path.chmod(0o755)
        return subprocess.CompletedProcess(cmd, 0, stdout="Build complete!\n", stderr="")

    class FakePopen:
        def __init__(self, cmd, cwd, env, stdout, stderr, text, start_new_session):  # noqa: ANN001
            recorded["launch_cmd"] = cmd
            recorded["launch_cwd"] = cwd
            self.pid = 4321

        def poll(self):
            return None

        def wait(self, timeout=None):  # noqa: ANN001
            return 0

        def terminate(self):
            return None

        def kill(self):
            return None

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    status = service.start_capture(
        session_id="session-1",
        language="en",
        prompt="Atlas and WhisperKit",
        diarize=True,
        chunk_millis=3100,
    )

    assert recorded["build_cmd"] == ["swift", "build", "-c", "release"]
    assert recorded["build_cwd"] == package_dir
    assert recorded["launch_cwd"] == package_dir
    assert status["available"] is True
    assert status["running"] is True
    assert status["sessionId"] == "session-1"
