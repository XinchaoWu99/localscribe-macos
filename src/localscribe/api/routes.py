from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from ..engines.whisperkit import WhisperKitServerEngine
from ..models import TranscriptionOptions
from ..streaming import LiveChunkRequest, SpeakerEnrollmentRequest, UploadTranscriptionRequest
from .services import AppServices


def register_routes(app: FastAPI, services: AppServices) -> None:
    @app.get("/")
    async def home() -> FileResponse:
        return FileResponse(services.static_dir / "index.html")

    @app.get("/api/status")
    async def status() -> dict[str, object]:
        return {
            "app": "LocalScribe",
            "engine": services.streaming_service.engine.status(),
            "diarization": services.diarization_service.status(),
            "contextRefinement": services.context_refinement_service.status(),
            "postProcessing": services.post_processing_service.status(),
            "speakerRecognition": services.speaker_resolver.status(),
            "systemAudio": services.system_audio_service.status(),
            "settings": services.streaming_service.status(),
        }

    @app.get("/api/system-audio")
    async def system_audio_status(
        session_id: str | None = Query(default=None, alias="sessionId"),
        language: str | None = Query(default=None),
        prompt: str | None = Query(default=None),
        diarize: bool = Query(default=True),
        chunk_millis: int | None = Query(default=None, alias="chunkMillis"),
    ) -> dict[str, object]:
        return {
            "systemAudio": services.system_audio_service.status(
                session_id=session_id,
                language=_clean(language),
                prompt=_clean(prompt),
                diarize=diarize,
                chunk_millis=chunk_millis,
            )
        }

    @app.post("/api/system-audio/start")
    async def start_system_audio(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, object]:
        session_id = "" if payload is None else str(payload.get("sessionId", "")).strip()
        if not session_id:
            raise HTTPException(status_code=400, detail="sessionId is required.")
        try:
            chunk_millis = (
                int(payload.get("chunkMillis"))
                if payload and payload.get("chunkMillis") is not None
                else None
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="chunkMillis must be an integer.") from exc

        session = _get_session_or_404(services, session_id)
        await _to_thread(
            services.post_processing_service.prepare_backend,
            TranscriptionOptions(
                post_process=True,
                post_process_backend=_clean(payload.get("postProcessBackend") if payload else None),
                post_process_model=_clean(payload.get("postProcessModel") if payload else None),
                live=True,
            ),
        )
        try:
            system_audio = await _to_thread(
                services.system_audio_service.start_capture,
                session_id=session_id,
                language=_clean(payload.get("language") if payload else None),
                prompt=_clean(payload.get("prompt") if payload else None),
                diarize=_parse_bool(payload.get("diarize") if payload else None, default=True),
                chunk_millis=chunk_millis,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        return {
            "session": session.to_payload(),
            "systemAudio": system_audio,
        }

    @app.post("/api/system-audio/stop")
    async def stop_system_audio() -> dict[str, object]:
        system_audio = await _to_thread(services.system_audio_service.stop_capture)
        return {"systemAudio": system_audio}

    @app.get("/api/postprocess/catalog")
    async def postprocess_catalog() -> dict[str, object]:
        return services.post_processing_service.catalog()

    @app.post("/api/postprocess/prepare")
    async def prepare_postprocess(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, object]:
        status = await _to_thread(
            services.post_processing_service.prepare_backend,
            TranscriptionOptions(
                post_process=True,
                post_process_backend=_clean(payload.get("backend") if payload else None),
                post_process_model=_clean(payload.get("model") if payload else None),
                live=True,
            ),
        )
        return {
            "postProcessing": status,
            "catalog": services.post_processing_service.catalog(),
        }

    @app.patch("/api/settings/live")
    async def update_live_settings(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, object]:
        raw_chunk_millis = None if payload is None else payload.get("chunkMillis")
        if raw_chunk_millis is None:
            return {"settings": services.streaming_service.status()}

        try:
            chunk_millis = int(raw_chunk_millis)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="chunkMillis must be an integer.") from exc

        return {"settings": services.streaming_service.update_live_settings(chunk_millis=chunk_millis)}

    @app.get("/api/models")
    async def list_models() -> dict[str, object]:
        engine = _get_whisperkit_engine_or_none(services)
        if engine is None:
            return {
                "supported": False,
                "reason": "Model management is only available when LocalScribe is using WhisperKit.",
                "models": [],
            }
        return engine.model_catalog()

    @app.post("/api/models/install")
    async def install_model(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, object]:
        model_id = _read_model_id(payload)
        engine = _get_whisperkit_engine(services)
        try:
            return engine.install_model(model_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/models/select")
    async def select_model(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, object]:
        model_id = _read_model_id(payload)
        engine = _get_whisperkit_engine(services)
        try:
            return engine.select_model(model_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/sessions")
    async def create_session() -> dict[str, object]:
        session = services.streaming_service.create_session()
        return {
            "session": session.to_payload(),
            "engine": services.streaming_service.engine.status(),
        }

    @app.get("/api/sessions")
    async def list_sessions(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        sessions = services.streaming_service.list_sessions(limit=limit)
        return {"sessions": [session.to_summary_payload() for session in sessions]}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, object]:
        session = _get_session_or_404(services, session_id)
        return {"session": session.to_payload()}

    @app.patch("/api/sessions/{session_id}")
    async def update_session(
        session_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, object]:
        title = None if payload is None else _clean(payload.get("title"))
        try:
            session = await _to_thread(services.streaming_service.rename_session, session_id, title)
            return {"session": session.to_payload()}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/sessions")
    async def clear_sessions(
        session_type: str | None = Query(default=None, alias="sessionType"),
        exclude_session_id: str | None = Query(default=None, alias="excludeSessionId"),
    ) -> dict[str, object]:
        deleted = await _to_thread(
            services.streaming_service.clear_sessions,
            session_type=session_type,
            exclude_session_id=exclude_session_id,
        )
        return {"deleted": deleted}

    @app.get("/api/sessions/{session_id}/export")
    async def export_session(
        session_id: str,
        format: str = Query(default="txt"),
    ) -> Response:
        try:
            exported = await _to_thread(services.streaming_service.export_session, session_id, format)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return Response(
            content=exported.content,
            media_type=exported.media_type,
            headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
        )

    @app.post("/api/transcribe/file")
    async def transcribe_file(
        file: UploadFile = File(...),
        language: str | None = Form(default=None),
        diarize: str = Form(default="true"),
        link_context: str = Form(default="true"),
        post_process: str = Form(default="true"),
        post_process_backend: str | None = Form(default=None),
        post_process_model: str | None = Form(default=None),
        prompt: str | None = Form(default=None),
    ) -> dict[str, object]:
        try:
            raw_bytes = await file.read()
            request = UploadTranscriptionRequest(
                filename=file.filename or "upload.wav",
                raw_bytes=raw_bytes,
                options=TranscriptionOptions(
                    language=_clean(language),
                    diarize=_parse_bool(diarize, default=True),
                    prompt=_clean(prompt),
                    link_context=True,
                    post_process=_parse_bool(post_process, default=True),
                    post_process_backend=_clean(post_process_backend),
                    post_process_model=_clean(post_process_model),
                    live=False,
                ),
            )
            result, session = await _to_thread(services.streaming_service.transcribe_upload, request)
            payload = result.to_payload()
            payload["session"] = session.to_payload()
            return payload
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/speakers")
    async def enroll_speaker(
        session_id: str,
        label: str = Form(...),
        sample: UploadFile = File(...),
    ) -> dict[str, object]:
        if not services.settings.enable_speaker_recognition:
            raise HTTPException(status_code=400, detail="Speaker recognition is disabled.")

        try:
            raw_bytes = await sample.read()
            request = SpeakerEnrollmentRequest(
                filename=sample.filename or "speaker.wav",
                raw_bytes=raw_bytes,
                label=label.strip(),
            )
            profile, session = await _to_thread(services.streaming_service.enroll_speaker, session_id, request)
            return {
                "speaker": profile.to_payload(),
                "session": session.to_payload(),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.patch("/api/sessions/{session_id}/speakers/{speaker_id}")
    async def rename_speaker(
        session_id: str,
        speaker_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, object]:
        label = "" if payload is None else str(payload.get("label", "")).strip()
        if not label:
            raise HTTPException(status_code=400, detail="label is required.")

        try:
            profile, session = await _to_thread(services.streaming_service.rename_speaker, session_id, speaker_id, label)
            return {
                "speaker": profile.to_payload(),
                "session": session.to_payload(),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/sessions/{session_id}/segments/{segment_id}")
    async def update_segment_text(
        session_id: str,
        segment_id: str,
        payload: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, object]:
        text = "" if payload is None else str(payload.get("text", ""))
        try:
            segment, session = await _to_thread(services.streaming_service.update_segment_text, session_id, segment_id, text)
            return {
                "segment": segment.to_payload(),
                "session": session.to_payload(),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket("/ws/live/{session_id}")
    async def live_socket(websocket: WebSocket, session_id: str) -> None:
        session = _get_session_or_404(services, session_id)
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "session_state",
                "session": session.to_payload(),
                "engine": services.streaming_service.engine.status(),
            }
        )

        try:
            while True:
                payload = json.loads(await websocket.receive_text())
                message_type = payload.get("type")

                if message_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if message_type == "stop":
                    await websocket.send_json({"type": "session_state", "session": session.to_payload()})
                    continue

                if message_type != "audio_chunk":
                    await websocket.send_json({"type": "error", "detail": f"Unsupported message type: {message_type}"})
                    continue

                try:
                    request = LiveChunkRequest(
                        sequence=int(payload.get("sequence", session.chunk_count + 1)),
                        mime_type=str(payload.get("mimeType", "")),
                        raw_bytes=base64.b64decode(payload.get("payload", "")),
                        options=TranscriptionOptions(
                            language=_clean(payload.get("language")),
                            diarize=_parse_bool(payload.get("diarize"), default=True),
                            prompt=_clean(payload.get("prompt")),
                            link_context=True,
                            post_process=_parse_bool(payload.get("postProcess"), default=True),
                            post_process_backend=_clean(payload.get("postProcessBackend")),
                            post_process_model=_clean(payload.get("postProcessModel")),
                            live=True,
                            offset_seconds=session.total_audio_seconds,
                        ),
                    )
                    latest, session = await _to_thread(services.streaming_service.ingest_live_chunk, session_id, request)
                except Exception as exc:
                    await websocket.send_json({"type": "error", "detail": str(exc)})
                    continue

                await websocket.send_json(
                    {
                        "type": "chunk_processed",
                        "latestSegments": [segment.to_payload() for segment in latest.segments],
                        "session": session.to_payload(),
                    }
                )
        except WebSocketDisconnect:
            return


async def _to_thread(func, *args, **kwargs):
    import asyncio

    return await asyncio.to_thread(func, *args, **kwargs)


def _get_session_or_404(services: AppServices, session_id: str):
    try:
        return services.streaming_service.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _read_model_id(payload: dict[str, Any] | None) -> str:
    model_id = "" if payload is None else str(payload.get("modelId", "")).strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="modelId is required.")
    return model_id


def _get_whisperkit_engine_or_none(services: AppServices) -> WhisperKitServerEngine | None:
    engine = services.streaming_service.engine
    if isinstance(engine, WhisperKitServerEngine):
        return engine
    return None


def _get_whisperkit_engine(services: AppServices) -> WhisperKitServerEngine:
    engine = _get_whisperkit_engine_or_none(services)
    if engine is None:
        raise HTTPException(
            status_code=400,
            detail="Model management is only available when LocalScribe is using WhisperKit.",
        )
    return engine
