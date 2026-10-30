"""OEM number resolution.

Turning a vehicle + part into an OEM number is a separate concern from scraping
marketplaces, so it lives behind one interface: `OEMResolver.resolve(query)`.

Strategies, in order (first hit wins):
  1. The user typed an OEM number.
  2. A mapping the user verified earlier, stored locally.
  3. A licensed catalog integration, only if one is configured and authorized.
  4. Otherwise: UNRESOLVED, with guidance for looking it up by hand.

We never invent a number, and never assume a part fits just because the make and
model match: a stored mapping is only reused when its vehicle configuration is
compatible with the query, and anything less than a full match is flagged
(`confident = False`) with a note saying why.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import OEMResolutionResult, OEMResolutionStatus, PartsQuery
from .part_numbers import normalize_part_number
from .storage import Storage
from .vocabulary import chassis_codes, fold, make_terms, model_without_codes

# Per-make catalog a user can open to look up an OEM number by hand. Manual reference
# only: we link to it, we do not scrape it.
CATALOG_URLS = {
    "bmw": "https://www.realoem.com/bmw/enUS/",
    "mini": "https://www.realoem.com/bmw/enUS/",
}
GENERIC_CATALOG_NOTE = (
    "No verified OEM mapping for this vehicle. Look the number up in the manufacturer's parts "
    "catalog (or a dealer), then save it here so future searches reuse it."
)

_SIDE_WORDS = {
    "front": "front", "rear": "rear", "back": "rear",
    "left": "left", "lh": "left", "right": "right", "rh": "right",
}


@runtime_checkable
class OEMCatalog(Protocol):
    """A licensed/authorized catalog. Optional; none ships with the app."""

    name: str

    def lookup(self, query: PartsQuery) -> OEMResolutionResult | None: ...


def vehicle_config(query: PartsQuery) -> dict[str, str]:
    """The identifying vehicle fields, normalized, used to store and match mappings."""
    codes = chassis_codes(query.model)
    cfg = {
        "make": query.make.strip(),
        "model": query.model.strip(),
        "chassis": codes[0] if codes else "",
        "engine": query.engine.strip(),
        "part_name": query.part_name.strip(),
        "side": " ".join(detect_sides(query.part_name)),
        "drive": query.drive if query.drive in ("LHD", "RHD") else "",
    }
    if query.year:
        cfg["year"] = str(query.year)
    return {k: v for k, v in cfg.items() if v}


def detect_sides(part_name: str | None) -> list[str]:
    """Canonical side words present in a part name, e.g. 'front', 'left'."""
    out: list[str] = []
    for w in fold(part_name).split():
        canon = _SIDE_WORDS.get(w)
        if canon and canon not in out:
            out.append(canon)
    return out


class OEMResolver:
    def __init__(self, storage: Storage | None = None, catalog: OEMCatalog | None = None):
        self.storage = storage
        self.catalog = catalog

    def resolve(self, query: PartsQuery) -> OEMResolutionResult:
        # 1. User-provided number.
        user_oem = normalize_part_number(query.oem_number)
        if user_oem:
            return OEMResolutionResult(
                status=OEMResolutionStatus.USER_PROVIDED,
                oem_numbers=[user_oem],
                source="user",
                vehicle_config=vehicle_config(query),
                verified=True,
            )

        # 2. Local verified mapping.
        if self.storage and query.make.strip() and query.part_name.strip():
            mapped = self._from_storage(query)
            if mapped:
                return mapped

        # 3. Licensed catalog (optional).
        if self.catalog:
            try:
                hit = self.catalog.lookup(query)
            except Exception as e:  # a catalog failure must not break the search
                hit = None
                note = f"Catalog '{self.catalog.name}' lookup failed: {e}"
            else:
                note = None
            if hit and hit.resolved:
                return hit
            if note:
                return self._unresolved(query, extra_note=note)

        # 4. Nothing: return guidance.
        return self._unresolved(query)

    def _from_storage(self, query: PartsQuery) -> OEMResolutionResult | None:
        candidates = self.storage.find_oem_mappings(query.make, query.part_name)
        best: tuple[bool, dict, list[str]] | None = None  # (confident, row, notes)
        for row in candidates:
            verdict, notes = _compatible(row, query)
            if verdict == "skip":
                continue
            confident = verdict == "ok"
            if best is None or (confident and not best[0]):
                best = (confident, row, notes)
            if confident:
                break
        if not best:
            return None
        confident, row, notes = best
        alts = [x.strip() for x in (row.get("alt_numbers") or "").split(",") if x.strip()]
        result = OEMResolutionResult(
            status=OEMResolutionStatus.VERIFIED_MAPPING,
            oem_numbers=[normalize_part_number(row["oem_number"])],
            alternative_numbers=[normalize_part_number(a) for a in alts],
            source="local verified mapping",
            vehicle_config={k: str(row[k]) for k in ("make", "model", "chassis", "engine", "body")
                            if row.get(k)},
            verified=True,
            confident=confident,
            notes=notes + ([row["notes"]] if row.get("notes") else []),
            mapping_id=row.get("id"),
        )
        return result

    def _unresolved(self, query: PartsQuery, extra_note: str | None = None) -> OEMResolutionResult:
        make = fold(query.make)
        url = next((CATALOG_URLS[m] for m in make_terms(query.make) if m in CATALOG_URLS),
                   CATALOG_URLS.get(make))
        notes = [GENERIC_CATALOG_NOTE]
        if extra_note:
            notes.insert(0, extra_note)
        return OEMResolutionResult(
            status=OEMResolutionStatus.UNRESOLVED,
            vehicle_config=vehicle_config(query),
            guidance_url=url,
            notes=notes,
        )


def _compatible(row: dict, query: PartsQuery) -> tuple[str, list[str]]:
    """Judge a stored mapping against the query.

    Returns ("ok"|"loose"|"skip", notes). "skip" means the mapping is for a clearly
    different part (opposite side or different generation) and must not be reused.
    "loose" means usable but flagged, because a detail differs or is unspecified.
    """
    notes: list[str] = []

    # Side: left vs right / front vs rear is a real difference -> never reuse.
    row_sides = set(detect_sides(row.get("side") or row.get("part_name")))
    q_sides = set(detect_sides(query.part_name))
    for axis in (({"left", "right"}), ({"front", "rear"})):
        rs, qs = row_sides & axis, q_sides & axis
        if rs and qs and rs != qs:
            return "skip", []

    # Chassis / generation: different code -> different car.
    row_chassis = (row.get("chassis") or "").upper()
    q_chassis = (chassis_codes(query.model)[:1] or [""])[0].upper()
    if row_chassis and q_chassis and row_chassis != q_chassis:
        return "skip", []
    if not row_chassis and row.get("model") and query.model:
        # No chassis code stored: fall back to comparing the model base name.
        if fold(model_without_codes(row["model"])) and fold(model_without_codes(query.model)) \
                and fold(model_without_codes(row["model"])) != fold(model_without_codes(query.model)):
            return "skip", []

    # Engine: mismatch is only a warning (matters for mechanical parts, not body panels).
    row_engine, q_engine = fold(row.get("engine")), fold(query.engine)
    if row_engine and q_engine and row_engine not in q_engine and q_engine not in row_engine:
        notes.append(f"verified for engine '{row['engine']}', you searched '{query.engine}' - double-check fitment")
        return "loose", notes
    if row_engine and not q_engine:
        notes.append(f"verified for engine '{row['engine']}'; you did not specify an engine")

    # Year / facelift.
    yf, yt = row.get("year_from"), row.get("year_to")
    if query.year and yf and yt and not (int(yf) <= query.year <= int(yt)):
        span = str(yf) if yf == yt else f"{yf}-{yt}"
        notes.append(f"verified for {span}, you searched {query.year} - check it also fits (facelift?)")
        return "loose", notes

    return ("loose" if notes else "ok"), notes
