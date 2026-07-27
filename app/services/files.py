import base64
import binascii
from io import BytesIO

from PIL import Image, ImageOps

from app.core.config import get_settings
from app.core.exceptions import ArkheError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def decode_base64_image(data: str) -> Image.Image:
    if data.startswith("data:"):
        _, _, data = data.partition(",")
    try:
        raw = base64.b64decode(data, validate=True)
    except binascii.Error as exc:
        raise ArkheError("ARKHE_UNSUPPORTED_IMAGE", "Imagem Base64 invalida.") from exc
    if len(raw) > get_settings().max_image_bytes:
        raise ArkheError("ARKHE_IMAGE_TOO_LARGE", "Imagem excede o limite configurado.")
    return load_image(raw)


def load_image(raw: bytes) -> Image.Image:
    if len(raw) > get_settings().max_image_bytes:
        raise ArkheError("ARKHE_IMAGE_TOO_LARGE", "Imagem excede o limite configurado.")
    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw))
        image_format = image.format
        transposed = ImageOps.exif_transpose(image)
        if image_format not in ALLOWED_FORMATS:
            raise ArkheError("ARKHE_UNSUPPORTED_IMAGE", "Formato de imagem nao suportado.")
        return transposed.convert("RGB")
    except ArkheError:
        raise
    except Exception as exc:
        raise ArkheError("ARKHE_UNSUPPORTED_IMAGE", "Imagem malformada ou nao suportada.") from exc
