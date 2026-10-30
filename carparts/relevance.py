"""Relevance scoring.

Every rule adds or subtracts a fixed number of points and records a reason, so
the debug panel can show exactly why a listing ranks where it does.

Ranking uses `match_tier` first and price second, so a cheap unrelated part can
never outrank an exact part number match:
    3  the part number matches
    2  vehicle and full part name match, and nothing looks wrong
    1  some signal (score >= 15), e.g. a bracket for the right car
    0  likely unrelated (hidden by default)
"""

from __future__ import annotations

import re

from .models import PartResult, PartsQuery
from .part_numbers import extract_part_numbers, normalize_part_number
from .vocabulary import (
    ACCESSORY_WORDS,
    BUNDLE_WORDS,
    ENGINE_CODE_LETTERS,
    KNOWN_MAKES,
    OPPOSITES,
    TRIM_PACKAGE_RE,
    chassis_codes,
    drive_mentioned,
    fold,
    is_drive_sensitive,
    make_terms,
    location_in_country,
    model_terms,
    translate_part_all,
    words,
)

TIER_EXACT = 3
TIER_RELEVANT = 2
TIER_WEAK = 1
TIER_UNRELATED = 0

WEAK_MIN_SCORE = 15


def result_text(r: PartResult) -> str:
    parts = [r.title, r.description, r.part_number, " ".join(r.oem_numbers), r.compatibility]
    return " \n ".join(p for p in parts if p)


def collect_part_numbers(r: PartResult) -> list[str]:
    nums = [normalize_part_number(r.part_number)] + [normalize_part_number(x) for x in r.oem_numbers]
    nums += extract_part_numbers(" ".join(x for x in (r.title, r.description, r.compatibility) if x))
    return list(dict.fromkeys(n for n in nums if n))


def contains_part_number(text: str, norm: str) -> bool:
    """True if `norm` appears in text once separators are removed, with no digit glued on either side."""
    if not norm:
        return False
    compact = re.sub(r"[\s\-./_]", "", text.upper())
    for m in re.finditer(re.escape(norm), compact):
        before = compact[m.start() - 1] if m.start() > 0 else ""
        after = compact[m.end()] if m.end() < len(compact) else ""
        if not before.isdigit() and not after.isdigit():
            return True
    return False


def _has_phrase(text_folded: str, phrase: str) -> bool:
    return re.search(r"(?<!\w)%s(?!\w)" % re.escape(fold(phrase)), text_folded) is not None


def _year_matches(text: str, year: int) -> bool:
    if re.search(r"(?<!\d)%d(?!\d)" % year, text):
        return True
    # Ranges like "2019-2023", "2019 - 2023", "2019/2023" or with an en dash (written as \u2013 below).
    for a, b in re.findall(r"(?<!\d)((?:19|20)\d{2})\s*[-/\u2013]\s*((?:19|20)\d{2})(?!\d)", text):
        if int(a) <= year <= int(b):
            return True
    return False


_ACCESSORY = {fold(a) for a in ACCESSORY_WORDS}


def _is_accessory(word: str) -> bool:
    """Exact accessory word, or a German compound ending in one ("radarsensor", "stossstangenhalter")."""
    if word in _ACCESSORY:
        return True
    return any(len(a) >= 5 and len(word) > len(a) + 2 and word.endswith(a) for a in _ACCESSORY)


def score_result(r: PartResult, q: PartsQuery, country_code: str | None = None) -> PartResult:
    """Fill relevance_score, relevance_reasons, match_tier and normalized_part_numbers on `r`."""
    text = result_text(r)
    tf = fold(text)
    tw = words(text)
    score = 0
    reasons: list[str] = []
    oem_match = vehicle_match = full_part_match = penalized = False

    def add(points: int, why: str) -> None:
        nonlocal score
        score += points
        reasons.append(f"{points:+d} {why}")

    r.normalized_part_numbers = collect_part_numbers(r)
    oem_norm = normalize_part_number(q.oem_number)
    if oem_norm:
        raw = q.oem_number.strip()
        if raw and raw.lower() in text.lower():
            add(50, f"exact part number '{raw}'")
            oem_match = True
        elif oem_norm in r.normalized_part_numbers or contains_part_number(text, oem_norm):
            add(40, f"normalized part number {oem_norm}")
            oem_match = True
        elif r.normalized_part_numbers:
            add(-10, "lists other part numbers, not ours")

    mk = make_terms(q.make)
    if mk and any(_has_phrase(tf, m) for m in mk):
        add(10, "make")
        vehicle_match = True
    mt = model_terms(q.model)
    if mt and any(_has_phrase(tf, m) for m in mt):
        add(10, "model")
        vehicle_match = True
    if q.year and _year_matches(text, q.year):
        add(5, "year")
    if q.engine.strip() and _has_phrase(tf, q.engine.strip()):
        add(3, "engine")

    part_terms = [q.part_name] + translate_part_all(q.part_name) if q.part_name.strip() else []
    if part_terms:
        if any(_has_phrase(tf, t) or set(words(t)) <= tw for t in part_terms):
            add(20, "part name")
            full_part_match = True
        elif any(w in tw for t in part_terms for w in words(t) if len(w) >= 4):
            add(10, "part name (partial)")

    # Negative signals look at the title only: seller descriptions are long and noisy.
    title_f = fold(r.title)
    title_w = words(r.title)
    query_words = words(" ".join([q.part_name, q.model, q.make] + translate_part_all(q.part_name)))
    accessory = sorted(w for w in title_w - query_words if _is_accessory(w))
    if accessory:
        add(-10, f"accessory words: {', '.join(accessory[:3])}")
        penalized = True
    bundle = sorted((words(TRIM_PACKAGE_RE.sub(" ", r.title)) & BUNDLE_WORDS) - query_words)
    if bundle:
        add(-5, f"bundle ({', '.join(bundle)})")
        penalized = True

    for side_a, side_b in OPPOSITES:
        a, b = {fold(x) for x in side_a}, {fold(x) for x in side_b}
        for wanted, other in ((a, b), (b, a)):
            if not query_words & wanted:
                continue
            if title_w & other and not title_w & wanted:
                add(-25, f"opposite position ({', '.join(sorted(title_w & other))})")
                penalized = True
            elif title_w & wanted and wanted & words(q.part_name):
                add(5, f"position ({', '.join(sorted(title_w & wanted))})")

    wanted_drive = (q.drive or "any").upper()
    if wanted_drive in ("LHD", "RHD"):
        said = drive_mentioned(text)
        other = "RHD" if wanted_drive == "LHD" else "LHD"
        if other in said and wanted_drive not in said:
            if is_drive_sensitive(q.part_name):
                add(-25, f"{other} part, you need {wanted_drive}")
                penalized = True
            else:
                add(-3, f"from a {other} car (this part is usually the same)")
        elif wanted_drive in said and is_drive_sensitive(q.part_name):
            add(5, wanted_drive)

    if mk and not any(_has_phrase(tf, m) for m in mk):
        others = [m for m in KNOWN_MAKES if fold(m) not in mk and _has_phrase(title_f, m)]
        if others:
            add(-40, f"different make ({others[0]})")
            penalized = True

    ours = chassis_codes(q.model)
    if ours:
        skip = ENGINE_CODE_LETTERS.get(fold(q.make).strip(), "")
        title_codes = {c for c in chassis_codes(re.sub(r"[^\w]+", " ", r.title)) if c[0] not in skip}
        if title_codes and not (title_codes & set(ours)):
            add(-25, f"different chassis ({', '.join(sorted(title_codes)[:3])})")
            penalized = True

    if location_in_country(r.location, country_code):
        add(5, "preferred country")

    r.relevance_score = score
    r.relevance_reasons = reasons
    if oem_match:
        r.match_tier = TIER_EXACT
    elif vehicle_match and full_part_match and not penalized:
        r.match_tier = TIER_RELEVANT
    elif score >= WEAK_MIN_SCORE:
        r.match_tier = TIER_WEAK
    else:
        r.match_tier = TIER_UNRELATED
    return r


def sort_key(r: PartResult) -> tuple:
    price = r.sort_price_eur if r.sort_price_eur is not None else float("inf")
    return (-r.match_tier, price, -r.relevance_score)
