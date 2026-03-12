from __future__ import annotations

from pathlib import Path

from localscribe.context import ContextRefinementService
from localscribe.config import Settings
from localscribe.engines.mock import MockEngine
from localscribe.storage import FileStore, SessionStore
from localscribe.streaming import StreamingService


class _StubDiarizationService:
    pass


def _service(tmp_path: Path) -> StreamingService:
    settings = Settings(data_dir=tmp_path, chunk_millis=2200)
    return StreamingService(
        settings=settings,
        engine=MockEngine(settings),
        session_store=SessionStore(settings.sessions_dir),
        file_store=FileStore(settings.uploads_dir),
        diarization_service=_StubDiarizationService(),
        context_refinement_service=ContextRefinementService(enabled=False),
    )


def test_update_live_settings_clamps_chunk_millis(tmp_path: Path) -> None:
    service = _service(tmp_path)

    minimum = service.update_live_settings(chunk_millis=50)
    maximum = service.update_live_settings(chunk_millis=25000)

    assert minimum["chunkMillis"] == service.MIN_CHUNK_MILLIS
    assert maximum["chunkMillis"] == service.MAX_CHUNK_MILLIS


def test_status_reports_live_chunk_bounds(tmp_path: Path) -> None:
    service = _service(tmp_path)

    status = service.status()

    assert status["chunkMillis"] == 2200
    assert status["minChunkMillis"] == service.MIN_CHUNK_MILLIS
    assert status["maxChunkMillis"] == service.MAX_CHUNK_MILLIS
