from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WhisperKitModelSpec:
    model_id: str
    label: str
    size_hint: str
    speed_hint: str
    quality_hint: str
    description: str
    recommended: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.model_id,
            "label": self.label,
            "sizeHint": self.size_hint,
            "speedHint": self.speed_hint,
            "qualityHint": self.quality_hint,
            "description": self.description,
            "recommended": self.recommended,
        }


WHISPERKIT_MODELS: tuple[WhisperKitModelSpec, ...] = (
    WhisperKitModelSpec(
        model_id="tiny",
        label="Tiny",
        size_hint="~75 MB",
        speed_hint="Fastest",
        quality_hint="Lowest",
        description="Lowest latency, best for quick checks and lightweight live capture.",
    ),
    WhisperKitModelSpec(
        model_id="base",
        label="Base",
        size_hint="~145 MB",
        speed_hint="Fast",
        quality_hint="Basic",
        description="Balanced for casual meetings when speed matters more than nuance.",
    ),
    WhisperKitModelSpec(
        model_id="small",
        label="Small",
        size_hint="~485 MB",
        speed_hint="Moderate",
        quality_hint="Good",
        description="Solid accuracy for day-to-day calls without the heavier large models.",
    ),
    WhisperKitModelSpec(
        model_id="medium",
        label="Medium",
        size_hint="~1.5 GB",
        speed_hint="Slower",
        quality_hint="Very good",
        description="Better for denser meetings, overlapping speakers, and noisier rooms.",
    ),
    WhisperKitModelSpec(
        model_id="large-v3-turbo",
        label="Large v3 Turbo",
        size_hint="~1.6 GB",
        speed_hint="Balanced",
        quality_hint="High",
        description="Recommended default for strong accuracy with better throughput than full large-v3.",
        recommended=True,
    ),
    WhisperKitModelSpec(
        model_id="large-v3",
        label="Large v3",
        size_hint="~3.1 GB",
        speed_hint="Slowest",
        quality_hint="Highest",
        description="Best accuracy for difficult recordings, long interviews, and multilingual audio.",
    ),
)

WHISPERKIT_MODEL_IDS = {spec.model_id for spec in WHISPERKIT_MODELS}


def whisperkit_model_spec(model_id: str) -> WhisperKitModelSpec | None:
    normalized = model_id.strip()
    for spec in WHISPERKIT_MODELS:
        if spec.model_id == normalized:
            return spec
    return None
