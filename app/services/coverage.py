import json
from dataclasses import dataclass

import numpy as np
from PIL import Image

COVERAGE_KEYS = ("frontal", "left", "right", "up", "down")
READY_MIN_REGION = 0.65
READY_MIN_AVERAGE = 0.72
READY_MIN_QUALITY = 0.15


@dataclass(frozen=True)
class CoverageState:
    coverage: dict[str, float]
    score: float
    next_hint: str
    ready: bool


def empty_coverage() -> dict[str, float]:
    return {key: 0.0 for key in COVERAGE_KEYS}


def load_coverage(raw: str | None) -> dict[str, float]:
    if not raw:
        return empty_coverage()
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return empty_coverage()
    coverage = empty_coverage()
    for key in COVERAGE_KEYS:
        coverage[key] = round(float(loaded.get(key, 0.0)), 4)
    return coverage


def dump_coverage(coverage: dict[str, float]) -> str:
    return json.dumps({key: round(float(coverage.get(key, 0.0)), 4) for key in COVERAGE_KEYS}, sort_keys=True)


def estimate_pose_scores(image: Image.Image) -> dict[str, float]:
    """Limited local head-pose proxy until a real landmark/pose model is plugged in."""
    array = np.asarray(image.resize((24, 24)).convert("RGB"), dtype=np.float32)
    red, green, blue = [float(array[:, :, channel].mean()) for channel in range(3)]
    top = float(array[:8, :, :].mean())
    bottom = float(array[16:, :, :].mean())
    left_luma = float(array[:, :8, :].mean())
    right_luma = float(array[:, 16:, :].mean())

    horizontal = (right_luma - left_luma) / 255.0
    vertical = (top - bottom) / 255.0
    chroma = (red - blue) / 255.0

    scores = {
        "frontal": 0.55 + min(green / 255.0, 0.35),
        "left": 0.18 + max(chroma, horizontal, 0.0),
        "right": 0.18 + max(-chroma, -horizontal, 0.0),
        "up": 0.18 + max(vertical, 0.0),
        "down": 0.18 + max(-vertical, 0.0),
    }
    return {key: round(max(0.0, min(1.0, value)), 4) for key, value in scores.items()}


def update_coverage(
    current: dict[str, float],
    pose_scores: dict[str, float],
    quality: float,
    requested_hint: str | None = None,
) -> CoverageState:
    quality_weight = 0.0 if quality < READY_MIN_QUALITY else 0.75 + (max(0.0, min(1.0, quality)) * 0.25)
    updated = empty_coverage()
    target_key = hint_to_key(requested_hint)
    for key in COVERAGE_KEYS:
        accepted = max(0.0, min(1.0, pose_scores.get(key, 0.0))) * quality_weight
        if key == target_key and quality >= READY_MIN_QUALITY:
            accepted = max(accepted, min(1.0, current.get(key, 0.0) + 0.28))
        updated[key] = round(max(current.get(key, 0.0), accepted), 4)
    score = round(sum(updated.values()) / len(COVERAGE_KEYS), 4)
    weakest_key, weakest_value = min(updated.items(), key=lambda item: item[1])
    ready = min(updated.values()) >= READY_MIN_REGION and score >= READY_MIN_AVERAGE and quality >= READY_MIN_QUALITY
    next_hint = "complete" if ready else f"turn_{weakest_key}" if weakest_key != "frontal" else "center_face"
    return CoverageState(coverage=updated, score=score, next_hint=next_hint, ready=ready)


def hint_to_key(hint: str | None) -> str | None:
    return {
        "center_face": "frontal",
        "turn_left": "left",
        "turn_right": "right",
        "turn_up": "up",
        "turn_down": "down",
    }.get(hint or "")


def coverage_ready(coverage: dict[str, float], quality: float) -> bool:
    score = sum(coverage.values()) / len(COVERAGE_KEYS)
    return min(coverage.values()) >= READY_MIN_REGION and score >= READY_MIN_AVERAGE and quality >= READY_MIN_QUALITY
