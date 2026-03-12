from __future__ import annotations

from dataclasses import dataclass
import json
import re

from ..models import LiveSession


@dataclass(slots=True)
class TranscriptExport:
    content: str
    media_type: str
    filename: str


def build_session_export(session: LiveSession, format_name: str) -> TranscriptExport:
    normalized = format_name.strip().lower()
    if normalized == "txt":
        return TranscriptExport(
            content=_render_text(session),
            media_type="text/plain; charset=utf-8",
            filename=f"{_slug(session)}.txt",
        )
    if normalized == "md":
        return TranscriptExport(
            content=_render_markdown(session),
            media_type="text/markdown; charset=utf-8",
            filename=f"{_slug(session)}.md",
        )
    if normalized == "json":
        return TranscriptExport(
            content=json.dumps(session.to_payload(), indent=2),
            media_type="application/json",
            filename=f"{_slug(session)}.json",
        )
    if normalized == "srt":
        return TranscriptExport(
            content=_render_srt(session),
            media_type="application/x-subrip; charset=utf-8",
            filename=f"{_slug(session)}.srt",
        )
    if normalized == "vtt":
        return TranscriptExport(
            content=_render_vtt(session),
            media_type="text/vtt; charset=utf-8",
            filename=f"{_slug(session)}.vtt",
        )
    raise ValueError(f"Unsupported export format: {format_name}")


def _render_text(session: LiveSession) -> str:
    lines = [_heading(session)]
    for segment in session.segments:
        label = segment.speaker_name or "Speaker"
        lines.append(f"[{_clock(segment.start)}] {label}: {segment.text}")
    if not session.segments:
        lines.append("No transcript segments available.")
    return "\n".join(lines).strip() + "\n"


def _render_markdown(session: LiveSession) -> str:
    lines = [f"# {_title(session)}", "", _session_meta(session), ""]
    if session.warnings:
        lines.append("## Warnings")
        lines.extend(f"- {warning}" for warning in session.warnings)
        lines.append("")

    lines.append("## Transcript")
    if not session.segments:
        lines.append("")
        lines.append("_No transcript segments available._")
        return "\n".join(lines).strip() + "\n"

    for segment in session.segments:
        label = segment.speaker_name or "Speaker"
        lines.append("")
        lines.append(f"### {_clock(segment.start)} - {_clock(segment.end)} · {label}")
        lines.append(segment.text)
    return "\n".join(lines).strip() + "\n"


def _render_srt(session: LiveSession) -> str:
    if not session.segments:
        return ""

    blocks: list[str] = []
    for index, segment in enumerate(session.segments, start=1):
        label = segment.speaker_name or "Speaker"
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_subtitle_time(segment.start, decimal=',')} --> {_subtitle_time(segment.end, decimal=',')}",
                    f"{label}: {segment.text}".strip(),
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def _render_vtt(session: LiveSession) -> str:
    lines = ["WEBVTT", ""]
    for segment in session.segments:
        label = segment.speaker_name or "Speaker"
        lines.append(f"{_subtitle_time(segment.start, decimal='.')} --> {_subtitle_time(segment.end, decimal='.')}")
        lines.append(f"{label}: {segment.text}".strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _heading(session: LiveSession) -> str:
    return f"{_title(session)}\n{_session_meta(session)}"


def _session_meta(session: LiveSession) -> str:
    return (
        f"Session {session.session_id[:8]} · {session.session_type} · "
        f"{len(session.segments)} segments · {round(session.total_audio_seconds, 1)}s"
    )


def _title(session: LiveSession) -> str:
    if session.title:
        return session.title
    return f"{session.session_type.title()} Session {session.session_id[:8]}"


def _slug(session: LiveSession) -> str:
    base = _title(session).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not slug:
        slug = f"localscribe-{session.session_id[:8]}"
    return slug


def _clock(value: float) -> str:
    total_seconds = max(0, int(value))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _subtitle_time(value: float, decimal: str) -> str:
    milliseconds = max(0, round(value * 1000))
    hours = milliseconds // 3_600_000
    minutes = (milliseconds % 3_600_000) // 60_000
    seconds = (milliseconds % 60_000) // 1000
    millis = milliseconds % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{decimal}{millis:03d}"
