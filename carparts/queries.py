"""Deterministic query generation.

A handful of readable variations, always in the same order, so a search is
easy to debug. Part number queries come first because they are the most precise.
"""

from __future__ import annotations

from .models import Condition, GeneratedQuery, PartsQuery
from .part_numbers import normalize_part_number
from .vocabulary import (
    GENERIC_PARTS_WORD_BG,
    GENERIC_PARTS_WORD_DE,
    GENERIC_PARTS_WORD_PL,
    chassis_codes,
    side_terms,
    translate_part,
)

# Sources pick the languages they understand, so this is the total across languages.
MAX_QUERIES = 20


def vehicle_short(q: PartsQuery) -> str:
    """ "BMW" + chassis code if the model has one ("G20"), otherwise the model name."""
    codes = chassis_codes(q.model)
    model = codes[0] if codes else q.model.strip()
    return " ".join(x for x in (q.make.strip(), model) if x)


def generate_queries(q: PartsQuery, max_queries: int = MAX_QUERIES) -> list[GeneratedQuery]:
    out: list[GeneratedQuery] = []
    vehicle = vehicle_short(q)
    part = q.part_name.strip()
    oem = normalize_part_number(q.oem_number)

    if oem:
        out.append(GeneratedQuery(text=oem, kind="oem"))
        if q.make.strip():
            out.append(GeneratedQuery(text=f"{q.make.strip()} {oem}", kind="oem_make"))
        if vehicle and vehicle != q.make.strip():
            out.append(GeneratedQuery(text=f"{vehicle} {oem}", kind="oem_model"))

    if vehicle and part:
        out.append(GeneratedQuery(text=f"{vehicle} {part}", kind="vehicle_part_en", language="en"))
        if q.condition == Condition.USED:
            out.append(GeneratedQuery(text=f"{vehicle} {part} used", kind="vehicle_part_used", language="en"))
        side_de = " ".join(side_terms(part, "de"))
        for term in translate_part(part, "de"):
            if side_de and side_de not in term:
                term = f"{term} {side_de}"
            out.append(GeneratedQuery(text=f"{vehicle} {term}", kind="vehicle_part_de", language="de"))
        for term in translate_part(part, "bg"):
            out.append(GeneratedQuery(text=f"{term} {vehicle}", kind="vehicle_part_bg", language="bg"))
        for term in translate_part(part, "pl"):
            out.append(GeneratedQuery(text=f"{term} {vehicle}", kind="vehicle_part_pl", language="pl"))
    elif part:
        out.append(GeneratedQuery(text=part, kind="part_only", language="en"))

    if vehicle and (part or oem):
        out.append(GeneratedQuery(text=f"{vehicle} {GENERIC_PARTS_WORD_DE}", kind="vehicle_generic_de", language="de"))
        out.append(GeneratedQuery(text=f"{GENERIC_PARTS_WORD_BG} {vehicle}", kind="vehicle_generic_bg", language="bg"))
        out.append(GeneratedQuery(text=f"{GENERIC_PARTS_WORD_PL} {vehicle}", kind="vehicle_generic_pl", language="pl"))

    seen: set[str] = set()
    unique = []
    for g in out:
        key = g.text.lower()
        if key not in seen:
            seen.add(key)
            unique.append(g)
    return unique[:max_queries]
