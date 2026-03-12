from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
import wave
from urllib.parse import urlparse

import httpx

from ..config import Settings
from .whisperkit_models import WHISPERKIT_MODELS, WhisperKitModelSpec, whisperkit_model_spec

_PROGRESS_PERCENT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)%")
_PROGRESS_HINT_RE = re.compile(
    r"(download|downloading|fetch|fetching|extract|extracting|prepare|preparing|convert|converting|tokenizer|model)",
    re.IGNORECASE,
)


class WhisperKitRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._log_handle = None
        self._install_process: subprocess.Popen | None = None
        self._install_log_handle = None
        self._installing_model: str | None = None
        self._last_install_warning: str | None = None
        self._last_warning: str | None = None
        self._parsed_url = urlparse(settings.whisper_server_url)
        self.host = self._parsed_url.hostname or "127.0.0.1"
        self.port = self._parsed_url.port or (443 if self._parsed_url.scheme == "https" else 80)
        self.base_path = self._parsed_url.path.rstrip("/") or "/v1"

    @property
    def log_path(self) -> Path:
        return self.settings.runtime_dir / "whisperkit-server.log"

    @property
    def install_log_path(self) -> Path:
        return self.settings.runtime_dir / "whisperkit-model-install.log"

    @property
    def bootstrap_audio_path(self) -> Path:
        return self.settings.runtime_dir / "whisperkit-install-bootstrap.wav"

    def can_manage(self) -> bool:
        return self._is_local_target() and self._resolve_runner_spec() is not None

    def status(self) -> dict[str, object]:
        with self._lock:
            self._refresh_install_process_locked()
            ready = self.is_ready()
            launch_spec = self._resolve_launch_spec()
            managed = launch_spec is not None and self._is_local_target()
            active_model = self._active_model_spec()
            payload: dict[str, object] = {
                "managed": managed,
                "autoStart": self.settings.whisperkit_autostart,
                "ready": ready,
                "running": self._is_process_alive(),
                "serverUrl": self.settings.whisper_server_url,
                "logPath": str(self.log_path),
                "currentModel": active_model.model_id if active_model is not None else self.settings.whisper_model,
                "modelsDir": str(self.settings.whisperkit_models_dir),
                "tokenizersDir": str(self.settings.whisperkit_tokenizers_dir),
            }
            if self._process is not None and self._is_process_alive():
                payload["pid"] = self._process.pid
            if launch_spec is not None:
                payload["launchCommand"] = launch_spec.command
                if launch_spec.cwd is not None:
                    payload["launchCwd"] = str(launch_spec.cwd)
            install_status = self._install_status_payload_locked()
            if install_status is not None:
                payload["install"] = install_status
            warning = self._warning_for_status(ready, managed)
            if warning is not None:
                payload["warning"] = warning
            return payload

    def startup(self) -> None:
        if not self.settings.whisperkit_autostart:
            return
        try:
            self.ensure_running()
        except Exception as exc:
            self._last_warning = str(exc)

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown_process_locked()

    def ensure_running(self) -> None:
        with self._lock:
            if self.is_ready():
                return
            if not self._is_local_target():
                raise RuntimeError(
                    "WhisperKit autostart only supports localhost targets. "
                    "Set LOCALSCRIBE_WHISPER_SERVER_URL to a local address or disable autostart."
                )
            launch_spec = self._resolve_launch_spec()
            if launch_spec is None:
                raise RuntimeError(
                    "WhisperKit CLI was not found. Install `whisperkit-cli` or set "
                    "LOCALSCRIBE_WHISPERKIT_BINARY / LOCALSCRIBE_WHISPERKIT_SOURCE_DIR."
                )
            if self._is_process_alive():
                self._wait_for_ready()
                return

            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings.whisperkit_models_dir.mkdir(parents=True, exist_ok=True)
            self.settings.whisperkit_tokenizers_dir.mkdir(parents=True, exist_ok=True)
            self._log_handle = self.log_path.open("a", encoding="utf-8")
            env = os.environ.copy()
            env.update(launch_spec.env)
            self._process = subprocess.Popen(
                launch_spec.command,
                cwd=str(launch_spec.cwd) if launch_spec.cwd is not None else None,
                env=env,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            try:
                self._wait_for_ready()
            except Exception:
                self._shutdown_process_locked()
                raise

    def is_ready(self) -> bool:
        probe_targets = [
            self.settings.whisper_server_url.rstrip("/") + "/models",
            self._server_root_url() + "/openapi.json",
            self._server_root_url() + "/health",
        ]
        with httpx.Client(timeout=httpx.Timeout(2.0), follow_redirects=True) as client:
            for target in probe_targets:
                try:
                    response = client.get(target)
                except httpx.HTTPError:
                    continue
                if response.status_code < 500:
                    self._last_warning = None
                    return True
        if self._tcp_ready():
            self._last_warning = None
            return True
        return False

    def model_catalog(self) -> dict[str, object]:
        with self._lock:
            self._refresh_install_process_locked()
            runtime_ready = self.is_ready()
            active_model = self._active_model_spec()
            models = []
            for spec in WHISPERKIT_MODELS:
                installed = self._is_model_installed_locked(spec)
                install_source = "managed-cache"
                if not installed and runtime_ready and active_model is not None and spec.model_id == active_model.model_id:
                    installed = True
                    install_source = "runtime-cache"
                if not installed:
                    install_source = "download-required"
                models.append(
                    {
                        **spec.to_payload(),
                        "installed": installed,
                        "active": active_model is not None and spec.model_id == active_model.model_id,
                        "installing": self._installing_model == spec.model_id and self._is_install_process_alive(),
                        "installSource": install_source,
                    }
                )

            payload: dict[str, object] = {
                "supported": self.can_manage(),
                "activeModel": active_model.model_id if active_model is not None else self.settings.whisper_model,
                "models": models,
                "installingModel": self._installing_model if self._is_install_process_alive() else None,
                "modelsDir": str(self.settings.whisperkit_models_dir),
                "tokenizersDir": str(self.settings.whisperkit_tokenizers_dir),
            }
            install_status = self._install_status_payload_locked()
            if install_status is not None:
                payload["install"] = install_status
            return payload

    def install_model(self, model_id: str) -> dict[str, object]:
        spec = whisperkit_model_spec(model_id)
        if spec is None:
            raise RuntimeError(f"Unknown WhisperKit model: {model_id}")

        with self._lock:
            self._refresh_install_process_locked()
            if self._is_model_installed_locked(spec):
                self._last_install_warning = None
                return self.model_catalog()
            if self._is_install_process_alive():
                if self._installing_model == spec.model_id:
                    return self.model_catalog()
                raise RuntimeError(
                    f"Another model install is already running for {self._installing_model}. Wait for it to finish first."
                )

            runner_spec = self._resolve_runner_spec()
            if runner_spec is None:
                raise RuntimeError(
                    "WhisperKit CLI was not found. Install `whisperkit-cli` or set "
                    "LOCALSCRIBE_WHISPERKIT_BINARY / LOCALSCRIBE_WHISPERKIT_SOURCE_DIR."
                )

            bootstrap_audio = self._ensure_bootstrap_audio_locked()
            self.install_log_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings.whisperkit_models_dir.mkdir(parents=True, exist_ok=True)
            self.settings.whisperkit_tokenizers_dir.mkdir(parents=True, exist_ok=True)
            self._install_log_handle = self.install_log_path.open("w", encoding="utf-8")
            env = os.environ.copy()
            env.update(runner_spec.env)
            command = [
                *runner_spec.prefix,
                "transcribe",
                "--model",
                spec.runtime_name,
                "--download-model-path",
                str(self.settings.whisperkit_models_dir),
                "--download-tokenizer-path",
                str(self.settings.whisperkit_tokenizers_dir),
                "--audio-path",
                str(bootstrap_audio),
            ]
            if self.settings.whisperkit_verbose:
                command.append("--verbose")

            self._install_log_handle.write(f"$ {' '.join(command)}\n")
            self._install_log_handle.flush()

            self._install_process = subprocess.Popen(
                command,
                cwd=str(runner_spec.cwd) if runner_spec.cwd is not None else None,
                env=env,
                stdout=self._install_log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            self._installing_model = spec.model_id
            self._last_install_warning = None
            return self.model_catalog()

    def select_model(self, model_id: str) -> dict[str, object]:
        spec = whisperkit_model_spec(model_id)
        if spec is None:
            raise RuntimeError(f"Unknown WhisperKit model: {model_id}")

        with self._lock:
            self._refresh_install_process_locked()
            if self._is_install_process_alive():
                raise RuntimeError("Wait for the current model download to finish before switching models.")
            active_model = self._active_model_spec()
            if active_model is not None and spec.model_id == active_model.model_id:
                return self.model_catalog()
            if active_model is None or spec.model_id != active_model.model_id:
                if not self._is_model_installed_locked(spec):
                    raise RuntimeError(f"{spec.label} is not installed yet. Install it first, then switch.")

            should_restart = self._is_process_alive() or self.is_ready() or self.settings.whisperkit_autostart
            self.settings.whisper_model = spec.model_id
            self._shutdown_process_locked()
            if should_restart:
                self.ensure_running()
            return self.model_catalog()

    def request_model_name(self) -> str:
        spec = self._active_model_spec()
        if spec is None:
            return self.settings.whisper_model
        return spec.runtime_name

    def _active_model_spec(self) -> WhisperKitModelSpec | None:
        return whisperkit_model_spec(self.settings.whisper_model)

    def _candidate_model_roots_locked(self) -> tuple[Path, ...]:
        root = self.settings.whisperkit_models_dir
        candidates: list[Path] = [root]
        nested_roots = (
            root / "models" / "argmaxinc" / "whisperkit-coreml",
            root / "argmaxinc" / "whisperkit-coreml",
        )
        for candidate in nested_roots:
            if candidate.exists():
                candidates.append(candidate)
        return tuple(candidates)

    def _model_dir_ready(self, model_dir: Path) -> bool:
        if not model_dir.is_dir():
            return False
        if (model_dir / "config.json").exists():
            return True
        return any(child.name != ".cache" for child in model_dir.iterdir())

    def _find_installed_model_dir_locked(self, spec: WhisperKitModelSpec) -> Path | None:
        for root in self._candidate_model_roots_locked():
            for pattern in spec.model_install_globs:
                for candidate in root.glob(pattern):
                    if self._model_dir_ready(candidate):
                        return candidate
        return None

    def _is_model_installed_locked(self, model: WhisperKitModelSpec | str) -> bool:
        spec = model if isinstance(model, WhisperKitModelSpec) else whisperkit_model_spec(model)
        if spec is None:
            model_dir = self.settings.whisperkit_models_dir / f"openai_whisper-{str(model).strip()}"
            return self._model_dir_ready(model_dir)
        return self._find_installed_model_dir_locked(spec) is not None

    def _wait_for_ready(self) -> None:
        deadline = time.monotonic() + self.settings.whisperkit_startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.is_ready():
                return
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(
                    f"WhisperKit server exited before becoming ready. See {self.log_path} for details."
                )
            time.sleep(1.0)
        raise RuntimeError(
            f"WhisperKit server did not become ready within "
            f"{self.settings.whisperkit_startup_timeout_seconds} seconds. See {self.log_path}."
        )

    def _warning_for_status(self, ready: bool, managed: bool) -> str | None:
        if ready:
            return None
        if not self._is_local_target():
            return "WhisperKit runtime management is disabled for non-local server URLs."
        if not managed:
            return (
                "WhisperKit CLI was not found. Install `whisperkit-cli` or set "
                "LOCALSCRIBE_WHISPERKIT_BINARY / LOCALSCRIBE_WHISPERKIT_SOURCE_DIR."
            )
        if not self.settings.whisperkit_autostart:
            return "WhisperKit autostart is disabled. Start the server manually or enable autostart."
        if self._last_warning is not None:
            return self._last_warning
        return f"WhisperKit is not ready yet. Server logs: {self.log_path}"

    def _resolve_runner_spec(self):
        explicit_binary = self.settings.whisperkit_binary
        if explicit_binary:
            binary_path = Path(explicit_binary).expanduser()
            if binary_path.exists():
                return _RunnerSpec(
                    prefix=[str(binary_path)],
                    cwd=None,
                    env={},
                )

        discovered_binary = shutil.which("whisperkit-cli")
        if discovered_binary is not None:
            return _RunnerSpec(
                prefix=[discovered_binary],
                cwd=None,
                env={},
            )

        if self.settings.whisperkit_source_dir is not None:
            source_dir = self.settings.whisperkit_source_dir
            if not source_dir.exists():
                return None
            return _RunnerSpec(
                prefix=["swift", "run", "whisperkit-cli"],
                cwd=source_dir,
                env={"BUILD_ALL": "1"},
            )
        return None

    def _resolve_launch_spec(self):
        runner_spec = self._resolve_runner_spec()
        if runner_spec is None:
            return None
        return _LaunchSpec(
            command=self._build_serve_command(runner_spec.prefix),
            cwd=runner_spec.cwd,
            env=runner_spec.env,
        )

    def _build_serve_command(self, prefix: list[str]) -> list[str]:
        command = [
            *prefix,
            "serve",
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--model",
            self.request_model_name(),
            "--download-model-path",
            str(self.settings.whisperkit_models_dir),
            "--download-tokenizer-path",
            str(self.settings.whisperkit_tokenizers_dir),
            "--word-timestamps",
            "--chunking-strategy",
            "vad",
        ]
        if self.settings.whisperkit_verbose:
            command.append("--verbose")
        return command

    def _is_local_target(self) -> bool:
        return self.host in {"127.0.0.1", "localhost", "::1"}

    def _server_root_url(self) -> str:
        root = self.base_path.removesuffix("/v1")
        if not root:
            root = ""
        return f"{self._parsed_url.scheme}://{self.host}:{self.port}{root}"

    def _is_process_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _is_install_process_alive(self) -> bool:
        return self._install_process is not None and self._install_process.poll() is None

    def _tcp_ready(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=1.0):
                return True
        except OSError:
            return False

    def _shutdown_process_locked(self) -> None:
        if self._process is not None and self._is_process_alive():
            self._process.terminate()
            try:
                self._process.wait(timeout=8.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3.0)
        self._process = None
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def _refresh_install_process_locked(self) -> None:
        if self._install_process is None or self._is_install_process_alive():
            return
        return_code = self._install_process.poll()
        completed_model = self._installing_model
        self._install_process = None
        self._installing_model = None
        if self._install_log_handle is not None:
            self._install_log_handle.close()
            self._install_log_handle = None

        if return_code == 0:
            self._last_install_warning = None
            return

        if completed_model is None:
            self._last_install_warning = f"WhisperKit model install failed. See {self.install_log_path}."
            return
        self._last_install_warning = (
            f"WhisperKit model install failed for {completed_model}. See {self.install_log_path}."
        )

    def _install_status_payload_locked(self) -> dict[str, object] | None:
        if self._install_process is None and self._last_install_warning is None:
            return None
        payload: dict[str, object] = {
            "logPath": str(self.install_log_path),
        }
        if self._is_install_process_alive():
            payload["running"] = True
            payload["model"] = self._installing_model
            if self._install_process is not None:
                payload["pid"] = self._install_process.pid
        else:
            payload["running"] = False
        log_text = self._read_install_log_text_locked()
        if log_text:
            log_tail = _tail_log_lines(log_text, max_lines=6)
            if log_tail:
                payload["logTail"] = log_tail
            progress_percent, progress_label = _parse_install_progress(log_text)
            if progress_percent is not None:
                payload["progressPercent"] = progress_percent
            if progress_label is not None:
                payload["progressLabel"] = progress_label
        if payload.get("running") and "progressLabel" not in payload:
            model_name = self._installing_model or "selected model"
            payload["progressLabel"] = f"Starting download for {model_name}."
        if self._last_install_warning is not None:
            payload["warning"] = self._last_install_warning
        return payload

    def _read_install_log_text_locked(self, max_bytes: int = 32768) -> str:
        path = self.install_log_path
        if not path.exists():
            return ""
        try:
            raw = path.read_bytes()
        except OSError:
            return ""
        if len(raw) > max_bytes:
            raw = raw[-max_bytes:]
        return raw.decode("utf-8", errors="ignore")

    def _ensure_bootstrap_audio_locked(self) -> Path:
        bootstrap_audio = self.bootstrap_audio_path
        if bootstrap_audio.exists():
            return bootstrap_audio

        bootstrap_audio.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(bootstrap_audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 8000)
        return bootstrap_audio

class _LaunchSpec:
    def __init__(self, command: list[str], cwd: Path | None, env: dict[str, str]) -> None:
        self.command = command
        self.cwd = cwd
        self.env = env


class _RunnerSpec:
    def __init__(self, prefix: list[str], cwd: Path | None, env: dict[str, str]) -> None:
        self.prefix = prefix
        self.cwd = cwd
        self.env = env


def _tail_log_lines(log_text: str, *, max_lines: int) -> list[str]:
    lines = [line.rstrip() for line in log_text.splitlines() if line.strip()]
    if not lines:
        return []
    return lines[-max_lines:]


def _parse_install_progress(log_text: str) -> tuple[int | None, str | None]:
    lines = _tail_log_lines(log_text, max_lines=40)
    fallback_line: str | None = None
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("$"):
            continue
        percent_match = None
        for candidate in _PROGRESS_PERCENT_RE.finditer(stripped):
            percent_match = candidate
        if percent_match is not None:
            progress = max(0, min(100, round(float(percent_match.group(1)))))
            return progress, stripped
        if fallback_line is None and _PROGRESS_HINT_RE.search(stripped):
            fallback_line = stripped
    return None, fallback_line
