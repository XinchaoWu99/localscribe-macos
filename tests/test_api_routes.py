from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from localscribe.api.app import create_app
from localscribe.config import Settings
from localscribe.models import TranscriptResult, TranscriptionOptions


def test_live_websocket_respects_post_process_flag(tmp_path: Path, monkeypatch) -> None:
    app = create_app(
        Settings(
            engine="mock",
            data_dir=tmp_path,
            enable_post_processing=False,
            postprocess_backend="none",
            enable_speaker_recognition=False,
        )
    )
    services = app.state.services
    session = services.streaming_service.create_session()
    captured: dict[str, bool] = {}

    def fake_ingest_live_chunk(session_id: str, request):
        captured["post_process"] = request.options.post_process
        return (
            TranscriptResult(
                engine_name="mock",
                segments=[],
                speakers=[],
                duration_seconds=0.0,
            ),
            services.streaming_service.get_session(session_id),
        )

    monkeypatch.setattr(services.streaming_service, "ingest_live_chunk", fake_ingest_live_chunk)

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/live/{session.session_id}") as websocket:
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "audio_chunk",
                    "sequence": 1,
                    "mimeType": "audio/wav",
                    "payload": base64.b64encode(b"").decode(),
                    "postProcess": False,
                }
            )
            websocket.receive_json()

    assert captured["post_process"] is False
