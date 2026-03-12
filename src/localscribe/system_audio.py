from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from pathlib import Path

from .config import Settings


class NativeSystemAudioService:
    def __init__(self, settings: Settings, project_root: Path) -> None:
        self.settings = settings
        self.project_root = project_root
        self.package_dir = project_root / "native" / "system-audio-helper"
        configured_binary = (settings.system_audio_helper_binary or "").strip()
        self._uses_custom_binary = bool(configured_binary)
        self.binary_path = (
            Path(configured_binary).expanduser()
            if configured_binary
            else self.package_dir / ".build" / "release" / "localscribe-system-audio"
        )
        self.log_path = settings.runtime_dir / "system-audio-helper.log"
        self._process: subprocess.Popen[str] | None = None
        self._session_id: str | None = None
        self._started_at: float | None = None
        self._last_error: str | None = None
        self._log_handle = None

    @property
    def server_url(self) -> str:
        return f"http://{self.settings.host}:{self.settings.port}"

    def status(
        self,
        session_id: str | None = None,
        *,
        language: str | None = None,
        prompt: str | None = None,
        diarize: bool = True,
        chunk_millis: int | None = None,
    ) -> dict[str, object]:
        self._refresh_process_state()
        available = self._binary_is_ready()
        launch_command = self.command_string(
            session_id=session_id,
            language=language,
            prompt=prompt,
            diarize=diarize,
            chunk_millis=chunk_millis,
        )
        warning = self._last_error
        if not available:
            warning = warning or self._missing_binary_message()
        return {
            "available": available,
            "running": bool(self._process),
            "pid": self._process.pid if self._process else None,
            "sessionId": self._session_id,
            "binaryPath": str(self.binary_path),
            "packageDir": str(self.package_dir),
            "serverUrl": self.server_url,
            "buildCommand": f"cd {shlex.quote(str(self.package_dir))} && swift build -c release",
            "launchCommand": launch_command,
            "warning": warning,
            "logTail": self._read_log_tail(),
            "uptimeSeconds": max(0.0, time.time() - self._started_at) if self._started_at else None,
        }

    def start_capture(
        self,
        *,
        session_id: str,
        language: str | None = None,
        prompt: str | None = None,
        diarize: bool = True,
        chunk_millis: int | None = None,
    ) -> dict[str, object]:
        self._refresh_process_state()
        if self._process:
            if self._session_id == session_id:
                return self.status(
                    session_id=session_id,
                    language=language,
                    prompt=prompt,
                    diarize=diarize,
                    chunk_millis=chunk_millis,
                )
            raise RuntimeError("Native Mac sound capture is already running for another session.")

        self._ensure_binary_ready()

        command = self.command(
            session_id=session_id,
            language=language,
            prompt=prompt,
            diarize=diarize,
            chunk_millis=chunk_millis,
        )

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_path.open("w", encoding="utf-8")
        env = os.environ.copy()
        env["LOCALSCRIBE_SERVER_URL"] = self.server_url
        env["LOCALSCRIBE_HOST"] = self.settings.host
        env["LOCALSCRIBE_PORT"] = str(self.settings.port)

        try:
            self._process = subprocess.Popen(
                command,
                cwd=self.package_dir,
                env=env,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        except OSError as exc:
            self._close_log_handle()
            self._last_error = str(exc)
            raise RuntimeError(f"Could not start native Mac sound capture: {exc}") from exc

        self._session_id = session_id
        self._started_at = time.time()
        self._last_error = None
        return self.status(
            session_id=session_id,
            language=language,
            prompt=prompt,
            diarize=diarize,
            chunk_millis=chunk_millis,
        )

    def _ensure_binary_ready(self) -> None:
        if self._binary_is_ready():
            return

        if self._uses_custom_binary:
            raise RuntimeError(self._missing_binary_message())

        self._build_helper()

        if not self.binary_path.exists():
            self._last_error = "Native Mac sound capture helper build finished but no executable was produced."
            raise RuntimeError(self._last_error)
        if not os.access(self.binary_path, os.X_OK):
            self._last_error = "Native Mac sound capture helper was built but is not executable."
            raise RuntimeError(self._last_error)

    def _build_helper(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()

        try:
            completed = subprocess.run(
                ["swift", "build", "-c", "release"],
                cwd=self.package_dir,
                env=env,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            self._last_error = f"Could not build native Mac sound capture helper: {exc}"
            raise RuntimeError(self._last_error) from exc

        log_output = "\n".join(
            part.rstrip()
            for part in (completed.stdout, completed.stderr)
            if part and part.strip()
        ).strip()
        if log_output:
            self.log_path.write_text(f"{log_output}\n", encoding="utf-8")

        if completed.returncode != 0:
            summary = self._summarize_build_failure(log_output)
            self._last_error = f"Native Mac sound capture helper build failed. {summary}".strip()
            raise RuntimeError(self._last_error)

        self._last_error = None

    def _binary_is_ready(self) -> bool:
        return self.binary_path.exists() and os.access(self.binary_path, os.X_OK)

    def _missing_binary_message(self) -> str:
        if self._uses_custom_binary:
            return f"Native Mac sound capture helper is not available at {self.binary_path}."
        return (
            "Native Mac sound capture helper is not built yet. LocalScribe will try to build it automatically the "
            "first time you start Mac output capture."
        )

    def _summarize_build_failure(self, log_output: str) -> str:
        if not log_output:
            return "Review the helper build log for details."

        for line in reversed(log_output.splitlines()):
            text = line.strip()
            if text:
                return text
        return "Review the helper build log for details."

    def stop_capture(self) -> dict[str, object]:
        self._refresh_process_state()
        process = self._process
        if not process:
            return self.status()

        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            process.terminate()

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                process.kill()
            process.wait(timeout=2)

        self._process = None
        self._session_id = None
        self._started_at = None
        self._close_log_handle()
        return self.status()

    def shutdown(self) -> None:
        if self._process:
            self.stop_capture()

    def command(
        self,
        *,
        session_id: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
        diarize: bool = True,
        chunk_millis: int | None = None,
    ) -> list[str]:
        command = [str(self.binary_path), "--server", self.server_url]
        if session_id:
            command.extend(["--session-id", session_id])
        if language:
            command.extend(["--language", language])
        if prompt:
            command.extend(["--prompt", prompt])
        if chunk_millis:
            command.extend(["--chunk-ms", str(max(500, int(chunk_millis)))])
        if not diarize:
            command.append("--no-diarize")
        return command

    def command_string(
        self,
        *,
        session_id: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
        diarize: bool = True,
        chunk_millis: int | None = None,
    ) -> str:
        return " ".join(
            shlex.quote(part)
            for part in self.command(
                session_id=session_id,
                language=language,
                prompt=prompt,
                diarize=diarize,
                chunk_millis=chunk_millis,
            )
        )

    def _refresh_process_state(self) -> None:
        if not self._process:
            return
        return_code = self._process.poll()
        if return_code is None:
            return

        if return_code != 0:
            self._last_error = f"Native Mac sound capture exited with code {return_code}."
        self._process = None
        self._session_id = None
        self._started_at = None
        self._close_log_handle()

    def _close_log_handle(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            finally:
                self._log_handle = None

    def _read_log_tail(self, max_lines: int = 8) -> list[str]:
        if not self.log_path.exists():
            return []
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return []
        return lines[-max_lines:]
