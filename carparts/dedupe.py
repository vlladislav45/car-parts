"""Duplicate detection.

Conservative on purpose: two listings are merged only when they are clearly the
same offer. Different conditions, different known sellers, clearly different
prices or non-overlapping part numbers always keep listings apart.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from urllib.parse import urlsplit

from .models import PartResult
from .vocabulary import fold

TITLE_SIMILARITY = 0.85
PRICE_TOLERANCE = 0.02  # 2 %


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}"


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, fold(a), fold(b)).ratio()


def _prices_close(a: float | None, b: float | None) -> bool | None:
    if a is None or b is None:
        return None
    hi = max(a, b)
    return hi == 0 or abs(a - b) / hi <= PRICE_TOLERANCE


def is_duplicate(a: PartResult, b: PartResult) -> bool:
    if normalize_url(a.url) == normalize_url(b.url):
        return True
    if "unknown" not in (a.condition.value, b.condition.value) and a.condition != b.condition:
        return False
    if a.seller and b.seller and fold(a.seller) != fold(b.seller):
        return False
    close = _prices_close(a.price_eur, b.price_eur)
    if close is False:
        return False
    nums_a, nums_b = set(a.normalized_part_numbers), set(b.normalized_part_numbers)
    if nums_a and nums_b and not nums_a & nums_b:
        return False
    if title_similarity(a.title, b.title) < TITLE_SIMILARITY:
        return False
    # Similar title and price alone is not enough (two sellers can list the same
    # part at the same price). Require one more strong signal.
    same_seller = bool(a.seller and b.seller)
    shared_number = bool(nums_a & nums_b)
    return close is True and (same_seller or shared_number)


def dedupe(results: list[PartResult]) -> list[PartResult]:
    """Keep the first of each duplicate group. Pass results already sorted best first."""
    kept: list[PartResult] = []
    for r in results:
        for k in kept:
            if is_duplicate(k, r):
                k.duplicates.append(f"{r.source} | {r.url}")
                break
        else:
            kept.append(r)
    return kept
