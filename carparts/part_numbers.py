"""Part number normalization and extraction.

Design rules:
- Only remove separators (spaces, hyphens, dots, slashes, underscores) and
  upper-case letters. Never drop, reorder or substitute alphanumeric characters
  (no O->0, no stripping of leading zeros), because that creates false matches.
- A leading brand prefix ("BMW 5111...") is removed only when the remainder
  still contains a digit, so a number like "VW123" is not turned into "123"
  unless the prefix is separated ("VW 123").
"""

from __future__ import annotations

import re

# Brand words commonly written in front of an OEM number. Only stripped when
# separated from the number by whitespace or punctuation.
BRAND_PREFIXES = {
    "BMW", "MINI", "VW", "VAG", "AUDI", "SKODA", "SEAT", "CUPRA", "PORSCHE",
    "MERCEDES", "MB", "MERCEDES-BENZ", "OPEL", "VAUXHALL", "FORD", "RENAULT",
    "PEUGEOT", "CITROEN", "DACIA", "FIAT", "ALFA", "TOYOTA", "LEXUS", "HONDA",
    "NISSAN", "MAZDA", "HYUNDAI", "KIA", "VOLVO", "OEM", "OE", "ORIGINAL",
}

_SEPARATORS = re.compile(r"[\s\-./_,:;]+")
_STRIP_EDGES = re.compile(r"^[^0-9A-Za-z]+|[^0-9A-Za-z]+$")


def normalize_part_number(raw: str | None) -> str:
    """Return a canonical form for comparison, or "" if nothing usable remains.

    >>> normalize_part_number("51 11 8 080 658")
    '51118080658'
    >>> normalize_part_number("BMW 51-11-8-080-658")
    '51118080658'
    >>> normalize_part_number("A 205 880 01 40")
    'A2058800140'
    """
    if not raw:
        return ""
    text = raw.strip().upper()
    text = _STRIP_EDGES.sub("", text)
    # Remove a separated brand prefix, e.g. "BMW 5111..." or "OE: 5111...".
    parts = re.split(r"[\s:]+", text, maxsplit=1)
    if len(parts) == 2 and parts[0] in BRAND_PREFIXES and re.search(r"\d", parts[1]):
        text = parts[1]
    text = _SEPARATORS.sub("", text)
    text = re.sub(r"[^0-9A-Z]", "", text)
    return text


def looks_like_part_number(token: str) -> bool:
    """Heuristic: 6+ chars after normalization and at least 4 digits."""
    norm = normalize_part_number(token)
    return len(norm) >= 6 and sum(c.isdigit() for c in norm) >= 4


# Candidate: runs of digits/letters possibly separated by single spaces,
# hyphens or dots, e.g. "51 11 8 080 658", "8W0-807-065", "A2058800140".
_CANDIDATE = re.compile(r"(?<![0-9A-Za-z])[0-9A-Za-z]{1,12}(?:[ \-.][0-9A-Za-z]{1,12}){0,6}(?![0-9A-Za-z])")


def extract_part_numbers(text: str | None) -> list[str]:
    """Find likely part numbers in free text and return them normalized.

    Grouped numbers with spaces ("51 11 8 080 658") are tried as a whole
    first; if the whole group is not plausible, each token is tried alone.
    """
    if not text:
        return []
    found: list[str] = []
    for match in _CANDIDATE.finditer(text):
        chunk = match.group(0)
        tokens = re.split(r"[ \-.]", chunk)
        # Only join groups that are mostly numeric (avoids gluing words together).
        if len(tokens) > 1 and all(t.isdigit() for t in tokens) and looks_like_part_number(chunk) and not _is_noise(chunk):
            found.append(normalize_part_number(chunk))
            continue
        pieces = chunk.split(" ")
        # Runs of numeric pieces inside mixed text, e.g. "vorne 51 11 8 080 658 G20".
        run: list[str] = []
        for piece in pieces + [""]:
            if piece and re.sub(r"[\-.]", "", piece).isdigit():
                run.append(piece)
                continue
            if len(run) > 1 and looks_like_part_number(" ".join(run)) and not _is_noise(" ".join(run)):
                found.append(normalize_part_number(" ".join(run)))
            run = []
        # Single pieces, including hyphenated codes like "8W0-807-065-A".
        for piece in pieces:
            if looks_like_part_number(piece) and not _is_noise(piece):
                found.append(normalize_part_number(piece))
    return _unique(found)


def part_numbers_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_part_number(a), normalize_part_number(b)
    return bool(na) and na == nb


def _is_noise(token: str) -> bool:
    # Years and year ranges ("2019-2026", "2018/2023") are not part numbers.
    token = token.strip(" .,;()")
    return bool(re.fullmatch(r"(19|20)\d{2}(\s*[-/.]\s*(19|20)\d{2})?", token))


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
