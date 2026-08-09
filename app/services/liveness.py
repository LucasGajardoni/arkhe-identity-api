from dataclasses import dataclass

from app.services.facial import FaceEmbeddingResult


@dataclass(frozen=True)
class LivenessResult:
    score: float
    passed: bool
    provider: str
    limited: bool


class PassiveLivenessService:
    """Deterministic placeholder, not a production anti-spoofing model."""

    provider = "passive-quality-v1"
    minimum_score = 0.50

    def evaluate(self, face: FaceEmbeddingResult) -> LivenessResult:
        score = round(min(1.0, max(0.0, 0.45 + (face.quality * 0.5))), 4)
        return LivenessResult(
            score=score,
            passed=score >= self.minimum_score and face.face_count == 1,
            provider=self.provider,
            limited=True,
        )
