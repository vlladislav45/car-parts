"""Centralized automotive parts catalog.

This sits on top of the translation tables in `vocabulary.py`: each canonical part
points at one English key in those tables (its `en` name), so the German, Bulgarian
and Polish terms are reused rather than duplicated. Synonyms (headlight / headlamp)
are grouped into one canonical part, and every localized term becomes a searchable
alias, so "броня", "bumper" and "Stoßstange" all resolve to the same part.

The catalog is defined in code (deterministic and testable). Mutable, user-maintained
additions (aliases mapped from unknown searches) live in SQLite via `storage.py` and
are merged in at lookup time, so the vocabulary grows without editing scraper code.

Nothing here talks to a marketplace. Resolution returns a canonical identity (or
nothing, for free text); query generation stays in `queries.py`.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .models import PartResolution
from .vocabulary import PART_TRANSLATIONS, fold, translate_part

# Category id -> display name. Order is the display order.
CATEGORIES: dict[str, str] = {
    "body_exterior": "Body and exterior",
    "lighting_electrical": "Lighting and electrical",
    "engine_cooling": "Engine and cooling",
    "transmission_drivetrain": "Transmission and drivetrain",
    "suspension_steering": "Suspension and steering",
    "braking": "Braking system",
    "interior": "Interior and dashboard",
    "exhaust": "Exhaust system",
    "wheels_tires": "Wheels and tires",
    "sensors_electronics": "Sensors and electronics",
}

# Every English key in vocabulary.PART_TRANSLATIONS is assigned to exactly one category.
# (A test enforces full, non-overlapping coverage.)
CATEGORY_MEMBERS: dict[str, list[str]] = {
    "body_exterior": [
        "bonnet", "hood", "boot lid", "trunk lid", "tailgate", "bumper", "front bumper", "rear bumper",
        "bumper bracket", "bumper grille", "bumper reinforcement", "crash bar", "fender", "wing",
        "front end", "front panel", "radiator support", "fuel flap", "grille", "kidney grille",
        "quarter panel", "rocker panel", "side skirt", "spoiler", "sunroof", "undertray",
        "wheel arch liner", "door", "door handle", "door lock", "door panel", "door card", "mirror",
        "door mirror", "side mirror", "wing mirror", "mirror glass", "window regulator", "rear window",
        "side window", "windscreen", "windshield",
    ],
    "lighting_electrical": [
        "headlight", "headlamp", "tail light", "taillight", "tail lamp", "fog light", "brake light",
        "indicator", "turn signal", "xenon ballast", "ignition coil", "alternator", "starter", "battery",
        "wiring harness", "horn", "wiper motor", "wiper arm", "washer tank",
    ],
    "engine_cooling": [
        "engine", "cylinder head", "engine mount", "timing chain", "turbo", "turbocharger", "intercooler",
        "oil cooler", "oil pump", "water pump", "radiator", "radiator fan", "cooling fan", "condenser",
        "expansion tank", "air filter box", "intake manifold", "throttle body", "egr valve", "fuel pump",
        "high pressure pump", "fuel injector", "injector", "mass air flow sensor", "ecu", "heater core",
        "ac compressor", "fuel tank",
    ],
    "transmission_drivetrain": [
        "gearbox", "transmission", "clutch", "flywheel", "differential", "drive shaft", "driveshaft",
        "prop shaft", "propshaft", "cv axle", "transfer case", "gear lever", "gear selector",
    ],
    "suspension_steering": [
        "suspension", "front suspension", "rear suspension", "control arm", "wishbone", "trailing arm",
        "shock absorber", "strut", "strut mount", "shock mount", "top mount", "coil spring", "spring",
        "leaf spring", "air spring", "air suspension", "bump stop", "subframe", "front axle", "rear axle",
        "wheel bearing", "wheel hub", "steering knuckle", "ball joint", "tie rod", "tie rod end",
        "track rod", "stabilizer", "anti roll bar", "sway bar", "stabilizer link", "drop link",
        "steering rack", "steering column", "power steering pump",
    ],
    "braking": ["brake disc", "brake caliper", "brake pads", "abs pump"],
    "interior": [
        "dashboard", "instrument cluster", "speedometer", "center console", "centre console",
        "climate control panel", "glovebox", "seat", "seat belt", "airbag", "driver airbag",
        "passenger airbag", "steering wheel", "blower motor", "window switch",
    ],
    "exhaust": ["exhaust", "exhaust manifold", "muffler", "silencer", "catalytic converter", "dpf",
                "particulate filter"],
    "wheels_tires": ["wheel", "rim"],
    "sensors_electronics": ["parking sensor", "rear camera", "reversing camera", "display", "navigation",
                            "radio", "key", "key fob"],
}

# Synonyms that are the same physical part: primary English key -> secondary keys.
# Secondaries do not become separate canonical parts; they feed the primary's aliases.
SYNONYM_GROUPS: dict[str, list[str]] = {
    "headlight": ["headlamp"],
    "tail light": ["taillight", "tail lamp"],
    "bonnet": ["hood"],
    "trunk lid": ["boot lid"],
    "side mirror": ["mirror", "door mirror", "wing mirror"],
    "grille": ["kidney grille"],
    "windscreen": ["windshield"],
    "gearbox": ["transmission"],
    "turbo": ["turbocharger"],
    "fuel injector": ["injector"],
    "driveshaft": ["drive shaft"],
    "propshaft": ["prop shaft"],
    "centre console": ["center console"],
    "control arm": ["wishbone"],
    "anti roll bar": ["sway bar", "stabilizer"],
    "tie rod": ["track rod"],
    "coil spring": ["spring"],
    "muffler": ["silencer"],
    "dpf": ["particulate filter"],
    "rear camera": ["reversing camera"],
    "stabilizer link": ["drop link"],
    "indicator": ["turn signal"],
    "radiator fan": ["cooling fan"],
    "top mount": ["strut mount", "shock mount"],
    "bumper reinforcement": ["crash bar"],
    "front panel": ["radiator support"],
}

# Extra searchable aliases, abbreviations and common spelling variants, keyed by part id.
# Localized dictionary terms are added automatically; this is for the rest (colloquial
# Bulgarian plurals, transliterations, abbreviations). Typos are handled by fuzzy matching.
EXTRA_ALIASES: dict[str, list[str]] = {
    "front_bumper": ["предна брона", "брона предна", "predna brona", "предната броня", "brona"],
    "rear_bumper": ["задна брона", "zadna brona", "задната броня"],
    "bumper": ["брона", "bron", "bampер"],
    "headlight": ["фарове", "предни фарове", "far", "hedlight", "head light"],
    "tail_light": ["стопове", "задни стопове", "stop", "stopove"],
    "fog_light": ["халогени", "халоген"],
    "fender": ["калници", "kalnik"],
    "side_mirror": ["огледала", "странични огледала", "ogledalo", "огледало за кола"],
    "mirror_glass": ["стъкло за огледало", "стъкло огледало"],
    "radiator": ["радиатори", "radeator"],
    "bonnet": ["преден капак", "капак преден", "kapak"],
    "windscreen": ["предно стъкло", "стъкло предно", "windskreen"],
    "ac_compressor": ["климатик компресор", "компресор климатик", "klima kompressor", "ac compressor"],
    "dpf": ["dpf филтър", "филтър за частици", "сажди филтър"],
    "abs_pump": ["abs помпа", "абс помпа", "абс модул"],
    "catalytic_converter": ["катализатор", "katalizator"],
    "alternator": ["динамо", "dinamo", "alternater"],
    "starter": ["стартер", "стартерче"],
    "shock_absorber": ["амортисьори", "amortisior"],
    "control_arm": ["носачи", "nosach"],
    "brake_disc": ["спирачен диск", "дискове", "disk"],
    "brake_pads": ["накладки", "накладки за спирачки", "nakladki"],
    "clutch": ["съединител", "feredo", "феродо"],
    "gearbox": ["скоростна кутия", "скорости"],
    "turbo": ["турбина", "турбо"],
    "steering_rack": ["кормилна рейка", "хидравлична рейка"],
}

# Parts where the left/right side materially changes the item (used to prompt attributes).
_SIDE_KEYWORDS = {
    "mirror", "headlight", "headlamp", "fender", "wing", "door", "fog light", "tail light", "taillight",
    "control arm", "trailing arm", "quarter panel", "tie rod", "cv axle", "wheel arch", "ball joint",
}


@dataclass(frozen=True)
class CanonicalPart:
    id: str
    category: str
    en: str                         # canonical English name (a key in PART_TRANSLATIONS)
    name_bg: str = ""
    name_de: str = ""
    name_pl: str = ""
    aliases: tuple[str, ...] = ()   # every searchable surface form (not normalized)
    attributes: dict[str, str] = field(default_factory=dict)
    active: bool = True

    @property
    def category_name(self) -> str:
        return CATEGORIES.get(self.category, self.category)

    def display(self) -> str:
        """Short label for the UI: English name (Bulgarian) - Category."""
        bg = f" ({self.name_bg})" if self.name_bg else ""
        return f"{self.en}{bg}"


def normalize(text: str | None) -> str:
    """Casefold (with German umlaut/ß folding), drop punctuation, collapse whitespace.

    Cyrillic is kept as-is (lower-cased). "Stoßstange, vorne!" -> "stossstange vorne".
    """
    if not text:
        return ""
    s = fold(text)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def _category_of(en: str) -> str:
    for cat, members in CATEGORY_MEMBERS.items():
        if en in members:
            return cat
    return "body_exterior"  # should never happen (coverage test enforces assignment)


def _build_catalog() -> list[CanonicalPart]:
    secondaries = {s for group in SYNONYM_GROUPS.values() for s in group}
    parts: list[CanonicalPart] = []
    all_keys = set(PART_TRANSLATIONS["de"])  # DE and BG cover the full key set
    for en in sorted(all_keys):
        if en in secondaries:
            continue
        members = [en] + SYNONYM_GROUPS.get(en, [])
        part_id = re.sub(r"[^a-z0-9]+", "_", en.lower()).strip("_")

        def first_term(lang: str) -> str:
            for m in members:
                terms = translate_part(m, lang)
                if terms:
                    return terms[0]
            return ""

        aliases: list[str] = list(members)  # English surface forms
        for m in members:
            for lang in ("de", "bg", "pl"):
                aliases.extend(translate_part(m, lang))
        aliases.extend(EXTRA_ALIASES.get(part_id, []))

        attrs: dict[str, str] = {}
        if re.search(r"\bfront\b", en):
            attrs["position"] = "front"
        elif re.search(r"\brear\b", en):
            attrs["position"] = "rear"
        if any(k in en for k in _SIDE_KEYWORDS):
            attrs["side_relevant"] = "true"

        parts.append(CanonicalPart(
            id=part_id,
            category=_category_of(en),
            en=en,
            name_bg=first_term("bg"),
            name_de=first_term("de"),
            name_pl=first_term("pl"),
            aliases=tuple(dict.fromkeys(a for a in aliases if a)),
            attributes=attrs,
        ))
    return parts


CATALOG: list[CanonicalPart] = _build_catalog()
BY_ID: dict[str, CanonicalPart] = {p.id: p for p in CATALOG}

# Normalized indexes built once.
# Canonical-name index: the English name and each localized display name -> part id (unique).
_CANON_NAME_INDEX: dict[str, str] = {}
# Alias index: normalized alias -> set of part ids (an alias may be shared / ambiguous).
_ALIAS_INDEX: dict[str, set[str]] = {}
for _p in CATALOG:
    for _name in (_p.en, _p.name_bg, _p.name_de, _p.name_pl):
        n = normalize(_name)
        if n:
            _CANON_NAME_INDEX.setdefault(n, _p.id)
    for _a in _p.aliases:
        n = normalize(_a)
        if n:
            _ALIAS_INDEX.setdefault(n, set()).add(_p.id)
_ALL_ALIAS_KEYS: list[str] = list(_ALIAS_INDEX)


class CatalogResolver:
    """Resolve user text (or an explicit part id) to a canonical part, or free text.

    `storage`, when given, contributes user-maintained aliases (from the maintenance
    screen) on top of the built-in catalog.
    """

    def __init__(self, storage=None):
        self.storage = storage

    def _user_aliases(self) -> dict[str, set[str]]:
        if not self.storage:
            return {}
        out: dict[str, set[str]] = {}
        for row in self.storage.all_user_aliases():
            if row.get("part_id") in BY_ID:
                out.setdefault(normalize(row["alias"]), set()).add(row["part_id"])
        return out

    def resolve(self, text: str | None, part_id: str = "") -> PartResolution:
        original = (text or "").strip()
        norm = normalize(original)
        extra = self._user_aliases()

        if part_id and part_id in BY_ID:
            return self._result(BY_ID[part_id], "canonical_id", 1.0, original, norm)

        if not norm:
            return PartResolution(matched=False, match_type="none", original_text=original, normalized_text=norm)

        # 1. Exact canonical name (English or a localized display name).
        if norm in _CANON_NAME_INDEX:
            return self._result(BY_ID[_CANON_NAME_INDEX[norm]], "canonical_name", 1.0, original, norm)

        # 2. Exact alias (may be ambiguous across parts).
        hits = set(_ALIAS_INDEX.get(norm, set())) | set(extra.get(norm, set()))
        if len(hits) == 1:
            return self._result(BY_ID[next(iter(hits))], "alias", 0.95, original, norm)
        if len(hits) > 1:
            cands = sorted(hits)
            return PartResolution(matched=False, ambiguous=True, match_type="ambiguous",
                                  candidate_ids=cands, original_text=original, normalized_text=norm,
                                  note="Several parts share this term; pick one.")

        # 3. Prefix / token containment.
        ranked = self._rank(norm, extra)
        if ranked and ranked[0][1] >= 0.8:
            pid, score, mtype = ranked[0]
            if len(ranked) > 1 and abs(ranked[1][1] - score) < 1e-9 and ranked[1][0] != pid:
                return PartResolution(matched=False, ambiguous=True, match_type="ambiguous",
                                      candidate_ids=[pid, ranked[1][0]], original_text=original,
                                      normalized_text=norm, note="More than one close match; pick one.")
            return self._result(BY_ID[pid], mtype, score, original, norm)

        # 4. Free text: not in the catalog. Offer the closest entries as suggestions only.
        suggestions = [pid for pid, _, _ in ranked[:5]]
        return PartResolution(matched=False, match_type="none", original_text=original,
                              normalized_text=norm, suggestion_ids=suggestions)

    def suggest(self, text: str | None, limit: int = 8) -> list[CanonicalPart]:
        """Ranked autocomplete candidates. Never forces a choice."""
        norm = normalize(text)
        if not norm:
            return []
        extra = self._user_aliases()
        seen: set[str] = set()
        out: list[CanonicalPart] = []
        # Exact canonical name first, then exact alias, then prefix/token/fuzzy from _rank.
        if norm in _CANON_NAME_INDEX:
            out.append(BY_ID[_CANON_NAME_INDEX[norm]])
            seen.add(out[-1].id)
        for pid in sorted(set(_ALIAS_INDEX.get(norm, set())) | set(extra.get(norm, set()))):
            if pid not in seen:
                out.append(BY_ID[pid]); seen.add(pid)
        for pid, _, _ in self._rank(norm, extra):
            if pid not in seen:
                out.append(BY_ID[pid]); seen.add(pid)
            if len(out) >= limit:
                break
        return out[:limit]

    def _rank(self, norm: str, extra: dict[str, set[str]]) -> list[tuple[str, float, str]]:
        """Candidate (part_id, score, match_type), best first, one row per part."""
        best: dict[str, tuple[float, str]] = {}

        def offer(pid: str, score: float, mtype: str) -> None:
            if pid not in best or score > best[pid][0]:
                best[pid] = (score, mtype)

        tokens = set(norm.split())
        alias_sources = list(_ALIAS_INDEX.items()) + [(k, v) for k, v in extra.items()]
        for alias, pids in alias_sources:
            if not alias:
                continue
            if alias.startswith(norm) or norm.startswith(alias):
                # Closer when the lengths are similar.
                score = 0.8 + 0.15 * (min(len(alias), len(norm)) / max(len(alias), len(norm)))
                for pid in pids:
                    offer(pid, round(score, 4), "prefix")
            else:
                atoks = set(alias.split())
                if tokens and (tokens <= atoks or atoks <= tokens):
                    for pid in pids:
                        offer(pid, 0.8, "token")
        # Fuzzy on the whole phrase for typos.
        for match in difflib.get_close_matches(norm, _ALL_ALIAS_KEYS, n=8, cutoff=0.8):
            ratio = difflib.SequenceMatcher(None, norm, match).ratio()
            for pid in _ALIAS_INDEX.get(match, set()):
                offer(pid, round(0.6 + 0.3 * ratio, 4), "fuzzy")
        ranked = sorted(((pid, s, m) for pid, (s, m) in best.items()), key=lambda x: (-x[1], x[0]))
        return ranked

    def _result(self, part: CanonicalPart, mtype: str, score: float, original: str,
                norm: str) -> PartResolution:
        return PartResolution(
            matched=True, part_id=part.id, canonical_en=part.en, display_bg=part.name_bg,
            category=part.category_name, match_type=mtype, score=score,
            original_text=original, normalized_text=norm,
            attributes=dict(part.attributes),
        )


# A module-level resolver with no storage, for callers that only need the built-in catalog.
default_resolver = CatalogResolver()
