import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageStat

from app.core.config import get_settings
from app.core.exceptions import ArkheError
from app.core.security import decrypt_bytes, encrypt_bytes


@dataclass(frozen=True)
class FaceEmbeddingResult:
    embedding: np.ndarray
    quality: float
    face_count: int
    pose_scores: dict[str, float] | None = None


class FacialService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._detector: Any = None
        self._recognizer: Any = None

    def _load_opencv(self, image: Image.Image):
        import cv2

        detector_path = Path(self.settings.face_detector_model_path)
        recognizer_path = Path(self.settings.face_recognizer_model_path)
        if not detector_path.exists() or not recognizer_path.exists():
            raise ArkheError(
                "ARKHE_INTERNAL_ERROR",
                "Modelos YuNet/SFace ausentes. Execute scripts/download_face_models.ps1.",
            )
        if self._detector is None:
            self._detector = cv2.FaceDetectorYN.create(str(detector_path), "", (image.width, image.height))
        else:
            self._detector.setInputSize((image.width, image.height))
        if self._recognizer is None:
            self._recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")
        return self._detector, self._recognizer

    def generate_embedding(self, image: Image.Image) -> FaceEmbeddingResult:
        if self.settings.face_backend == "fake":
            return self._fake_embedding(image)
        import cv2

        array = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
        detector, recognizer = self._load_opencv(image)
        _, faces = detector.detect(array)
        face_count = 0 if faces is None else len(faces)
        if face_count == 0:
            raise ArkheError("ARKHE_NO_FACE", "Nenhuma face detectada.")
        if face_count > 1:
            raise ArkheError("ARKHE_MULTIPLE_FACES", "Mais de uma face detectada.")
        quality = self._quality(image)
        if quality < 0.15:
            raise ArkheError("ARKHE_LOW_IMAGE_QUALITY", "Imagem com qualidade insuficiente.")
        aligned = recognizer.alignCrop(array, faces[0])
        embedding = np.asarray(recognizer.feature(aligned), dtype=np.float32).reshape(-1)
        return FaceEmbeddingResult(
            embedding=self._normalize(embedding),
            quality=quality,
            face_count=1,
            pose_scores=self._pose_scores_from_yunet_face(faces[0]),
        )

    def _fake_embedding(self, image: Image.Image) -> FaceEmbeddingResult:
        if image.width < 12 or image.height < 12:
            raise ArkheError("ARKHE_NO_FACE", "Nenhuma face detectada.")
        pixels = np.asarray(image.resize((16, 8))).astype(np.float32).reshape(-1)
        if pixels.std() < 1:
            raise ArkheError("ARKHE_LOW_IMAGE_QUALITY", "Imagem com qualidade insuficiente.")
        return FaceEmbeddingResult(embedding=self._normalize(pixels), quality=self._quality(image), face_count=1)

    @staticmethod
    def _pose_scores_from_yunet_face(face: np.ndarray) -> dict[str, float]:
        _, _, w, h = [float(value) for value in face[:4]]
        if w <= 0 or h <= 0:
            return {}
        landmarks = np.asarray(face[4:14], dtype=np.float32).reshape(5, 2)
        right_eye, left_eye, nose, right_mouth, left_mouth = landmarks
        eye_center = (right_eye + left_eye) / 2.0
        mouth_center = (right_mouth + left_mouth) / 2.0
        anchor_center = (eye_center + mouth_center) / 2.0

        yaw = float((nose[0] - anchor_center[0]) / w)
        pitch = float((nose[1] - anchor_center[1]) / h)
        eye_distance = float(np.linalg.norm(left_eye - right_eye) / w)
        mouth_distance = float(np.linalg.norm(left_mouth - right_mouth) / w)
        landmark_balance = max(0.0, min(1.0, (eye_distance + mouth_distance) / 0.7))

        yaw_strength = min(abs(yaw) * 5.0, 1.0)
        pitch_strength = min(abs(pitch) * 5.0, 1.0)
        frontal = max(0.15, 1.0 - (yaw_strength * 0.55) - (pitch_strength * 0.35))
        left = 0.28 + (max(yaw, 0.0) * 4.2)
        right = 0.28 + (max(-yaw, 0.0) * 4.2)
        up = 0.28 + (max(-pitch, 0.0) * 4.2)
        down = 0.28 + (max(pitch, 0.0) * 4.2)

        scores = {
            "frontal": frontal,
            "left": left,
            "right": right,
            "up": up,
            "down": down,
        }
        return {
            key: round(max(0.0, min(1.0, value * (0.65 + landmark_balance * 0.35))), 4)
            for key, value in scores.items()
        }

    @staticmethod
    def _quality(image: Image.Image) -> float:
        stat = ImageStat.Stat(image.convert("L"))
        contrast = min(stat.stddev[0] / 80.0, 1.0)
        size_score = min((image.width * image.height) / (320 * 320), 1.0)
        return round((contrast * 0.7) + (size_score * 0.3), 4)

    @staticmethod
    def _normalize(embedding: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return embedding
        return embedding / norm

    @staticmethod
    def serialize_embedding(embedding: np.ndarray) -> bytes:
        return json.dumps([round(float(value), 8) for value in embedding.tolist()]).encode("utf-8")

    @staticmethod
    def deserialize_embedding(raw: bytes) -> np.ndarray:
        return np.asarray(json.loads(raw.decode("utf-8")), dtype=np.float32)

    def encrypt_embedding(self, embedding: np.ndarray) -> str:
        encrypted = encrypt_bytes(self.serialize_embedding(embedding))
        assert encrypted is not None
        return encrypted

    def decrypt_embedding(self, encrypted: str) -> np.ndarray:
        raw = decrypt_bytes(encrypted)
        if raw is None:
            raise ArkheError("ARKHE_FACE_NOT_REGISTERED", "Referencia facial ausente.")
        return self.deserialize_embedding(raw)

    @staticmethod
    def similarity(left: np.ndarray, right: np.ndarray) -> float:
        left_n = FacialService._normalize(left)
        right_n = FacialService._normalize(right)
        cosine = float(np.dot(left_n, right_n))
        return round(max(0.0, min(1.0, (cosine + 1.0) / 2.0)), 4)

    @staticmethod
    def image_to_bytes(image: Image.Image) -> bytes:
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()
