from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..audio import extract_clip
from ..models import LiveSession, SpeakerProfile, TranscriptSegment


class SpeakerResolver:
    def __init__(self, model_dir: Path, enabled: bool, similarity_threshold: float) -> None:
        self.model_dir = model_dir
        self.enabled = enabled
        self.similarity_threshold = similarity_threshold
        self._import_error: str | None = None
        self._runtime_warning: str | None = None
        self._classifier = None

        if not enabled:
            self._import_error = "Speaker recognition is disabled."
            return

        try:
            _apply_torchaudio_compat_shims()
            from speechbrain.inference.speaker import EncoderClassifier
            import torch
            import torch.nn.functional as functional
        except Exception as exc:  # pragma: no cover - optional dependency path
            self._import_error = str(exc)
            return

        self._EncoderClassifier = EncoderClassifier
        self._torch = torch
        self._functional = functional

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "ready": self._import_error is None and self._runtime_warning is None,
            "warning": self._runtime_warning or self._import_error,
        }

    def enroll(self, session: LiveSession, sample_path: Path, label: str) -> SpeakerProfile:
        embedding = self._embedding_for_file(sample_path)
        speaker_id = uuid4().hex
        profile = SpeakerProfile(speaker_id=speaker_id, label=label, enrolled=True, samples=1)
        session.speakers[speaker_id] = profile
        session.speaker_embeddings[speaker_id] = embedding
        session.speaker_counts[speaker_id] = 1
        return profile

    def assign(self, session: LiveSession, audio_path: Path, segments: list[TranscriptSegment]) -> list[SpeakerProfile]:
        if not segments:
            return list(session.speakers.values())

        if not self.enabled or self._import_error is not None:
            return self._fallback_assign(session, segments)

        clips_dir = audio_path.parent / "speaker-clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        try:
            for segment in segments:  # pragma: no cover - optional dependency path
                clip_path = clips_dir / f"{segment.segment_id}.wav"
                extract_clip(audio_path, clip_path, segment.start, segment.end)
                embedding = self._embedding_for_file(clip_path)
                speaker_id, similarity = self._resolve(session, embedding)
                if speaker_id is None:
                    speaker_id = uuid4().hex
                    label = f"Speaker {len(session.speakers) + 1}"
                    session.speakers[speaker_id] = SpeakerProfile(
                        speaker_id=speaker_id,
                        label=label,
                        enrolled=False,
                        samples=1,
                        similarity=similarity,
                    )
                    session.speaker_embeddings[speaker_id] = embedding
                    session.speaker_counts[speaker_id] = 1
                else:
                    current_count = session.speaker_counts.get(speaker_id, 1)
                    centroid = session.speaker_embeddings[speaker_id]
                    merged = (centroid * current_count + embedding) / (current_count + 1)
                    session.speaker_embeddings[speaker_id] = self._functional.normalize(merged, dim=-1)
                    session.speaker_counts[speaker_id] = current_count + 1
                    session.speakers[speaker_id].samples = current_count + 1
                    session.speakers[speaker_id].similarity = similarity

                profile = session.speakers[speaker_id]
                segment.speaker_id = speaker_id
                segment.speaker_name = profile.label
        except Exception as exc:
            self._runtime_warning = (
                "Speaker recognition fell back to simple labels because the voiceprint model failed to run: "
                f"{exc}"
            )
            return self._fallback_assign(session, segments)

        self._runtime_warning = None
        return list(session.speakers.values())

    def _fallback_assign(self, session: LiveSession, segments: list[TranscriptSegment]) -> list[SpeakerProfile]:
        profile = session.speakers.get("speaker-1")
        if profile is None:
            profile = SpeakerProfile(speaker_id="speaker-1", label="Speaker 1", enrolled=False, samples=0)
        profile.samples += len(segments)
        session.speakers[profile.speaker_id] = profile
        for segment in segments:
            segment.speaker_id = segment.speaker_id or profile.speaker_id
            segment.speaker_name = segment.speaker_name or profile.label
        return list(session.speakers.values())

    def _get_classifier(self):
        if self._import_error is not None:
            raise RuntimeError(self._import_error)
        if self._classifier is None:  # pragma: no cover - optional dependency path
            self.model_dir.mkdir(parents=True, exist_ok=True)
            self._classifier = self._EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=str(self.model_dir / "speechbrain-ecapa"),
                run_opts={"device": "cpu"},
            )
        return self._classifier

    def _embedding_for_file(self, audio_path: Path):
        classifier = self._get_classifier()
        return classifier.encode_file(str(audio_path))

    def _resolve(self, session: LiveSession, embedding):
        if not session.speaker_embeddings:  # pragma: no cover - optional dependency path
            return None, None

        best_id = None
        best_similarity = None
        for speaker_id, centroid in session.speaker_embeddings.items():
            value = self._functional.cosine_similarity(embedding, centroid).item()
            if best_similarity is None or value > best_similarity:
                best_id = speaker_id
                best_similarity = value

        if best_similarity is not None and best_similarity >= self.similarity_threshold:
            return best_id, best_similarity
        return None, best_similarity


def _apply_torchaudio_compat_shims() -> None:
    import torchaudio

    if not hasattr(torchaudio, "list_audio_backends"):
        torchaudio.list_audio_backends = lambda: ["ffmpeg"]  # type: ignore[attr-defined]
    if not hasattr(torchaudio, "get_audio_backend"):
        torchaudio.get_audio_backend = lambda: "ffmpeg"  # type: ignore[attr-defined]
    if not hasattr(torchaudio, "set_audio_backend"):
        torchaudio.set_audio_backend = lambda _backend=None: None  # type: ignore[attr-defined]
