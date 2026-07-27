import re
import unicodedata
from datetime import date

from rapidfuzz.distance import JaroWinkler

SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return SPACE_RE.sub(" ", without_accents.upper()).strip()


def text_similarity(left: str | None, right: str | None) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm and not right_norm:
        return 1.0
    if not left_norm or not right_norm:
        return 0.0
    return float(JaroWinkler.normalized_similarity(left_norm, right_norm))


def exact_text(left: str | None, right: str | None) -> bool:
    return normalize_text(left) == normalize_text(right)


def same_date(left: date | None, right: date | None) -> bool:
    return left is not None and right is not None and left.isoformat() == right.isoformat()
