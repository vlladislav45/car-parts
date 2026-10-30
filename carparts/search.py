"""Search orchestration: run sources, normalize prices, score, filter, dedupe, sort."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from .catalog import CatalogResolver
from .currency import RateProvider, StaticRates
from .dedupe import dedupe
from .models import (
    Condition,
    PartResult,
    PartsQuery,
    SearchOutcome,
    SourceState,
    SourceStatus,
)
from .oem import OEMResolver
from .part_numbers import normalize_part_number
from .queries import generate_queries
from .relevance import TIER_UNRELATED, score_result, sort_key
from .storage import Storage

# UI country choice -> ISO code used by sources' `countries` lists.
COUNTRIES = {
    "Any": None, "Europe": None, "Germany": "DE", "Austria": "AT", "UK": "GB", "France": "FR",
    "Italy": "IT", "Spain": "ES", "Netherlands": "NL", "Belgium": "BE", "Poland": "PL",
    "Czechia": "CZ", "Lithuania": "LT", "Bulgaria": "BG",
}


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def source_matches_country(source: Any, country: str) -> bool:
    code = COUNTRIES.get(country)
    if code is None:
        return True
    countries = [c.upper() for c in getattr(source, "countries", ["EU"])]
    # Europe-wide sources ship everywhere in Europe, so keep them for any European country.
    return code in countries or "EU" in countries


def enrich(r: PartResult, rates: RateProvider) -> PartResult:
    r.price_eur = rates.to_eur(r.price, r.currency)
    r.shipping_eur = rates.to_eur(r.shipping_price, r.currency)
    if r.price_eur is not None and r.shipping_eur is not None:
        r.total_eur = round(r.price_eur + r.shipping_eur, 2)
    # Unknown shipping: sort by item price, which is a lower bound of the real total.
    r.sort_price_eur = r.total_eur if r.total_eur is not None else r.price_eur
    return r


def condition_ok(r: PartResult, wanted: Condition) -> bool:
    if wanted == Condition.ANY or r.condition == Condition.UNKNOWN:
        return True  # unknown condition is kept; the user can check the listing
    return r.condition == wanted


def run_search(
    query: PartsQuery,
    sources: list[Any],
    rates: RateProvider | None = None,
    storage: Storage | None = None,
    max_workers: int = 4,
    resolver: OEMResolver | None = None,
    part_resolver: CatalogResolver | None = None,
) -> SearchOutcome:
    rates = rates or StaticRates()

    # Resolve the part text against the catalog. If it maps to a canonical part, search
    # by that part's canonical name (so query generation produces all-language terms);
    # otherwise keep the user's exact free text. The original is always preserved.
    part_resolver = part_resolver or CatalogResolver(storage)
    part_resolution = part_resolver.resolve(query.part_name, part_id=query.part_id)
    if part_resolution.matched and part_resolution.canonical_en:
        query = query.model_copy(update={"part_name": part_resolution.canonical_en})
    elif storage and query.part_name.strip() and not part_resolution.matched:
        storage.log_unknown_term(part_resolution.original_text, part_resolution.normalized_text)

    # Resolve an OEM number before searching. If the user gave none but a verified
    # mapping exists, searches (and OEM-only sources) run against that number.
    resolver = resolver or OEMResolver(storage)
    resolution = resolver.resolve(query)
    if resolution.resolved and not normalize_part_number(query.oem_number):
        query = query.model_copy(update={"oem_number": resolution.primary})

    country_code = COUNTRIES.get(query.country)
    statuses: list[SourceStatus] = []
    active = []
    for s in sources:
        if source_matches_country(s, query.country):
            active.append(s)
        else:
            statuses.append(SourceStatus(name=s.name, available=getattr(s, "available", True),
                                         state=SourceState.NOT_SUPPORTED,
                                         message=f"Skipped: does not serve {query.country}"))

    def run_one(source: Any) -> tuple[list[PartResult], SourceStatus]:
        try:
            found = source.search(query)
        except Exception as e:
            return [], SourceStatus(name=source.name, available=False, state=SourceState.PARSING_ERROR,
                                    message=f"Crashed: {e}", errors=[str(e)])
        status = getattr(source, "last_status", None) or SourceStatus(
            name=source.name, available=True, message="OK", result_count=len(found))
        return found, status

    raw: list[PartResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for found, status in pool.map(run_one, active):
            raw.extend(found)
            statuses.append(status)

    shown: list[PartResult] = []
    hidden: list[PartResult] = []
    for r in raw:
        enrich(r, rates)
        score_result(r, query, country_code)
        if not condition_ok(r, query.condition):
            r.relevance_reasons.append("hidden: condition does not match")
            hidden.append(r)
        elif r.match_tier == TIER_UNRELATED:
            r.relevance_reasons.append("hidden: likely unrelated")
            hidden.append(r)
        else:
            shown.append(r)

    shown = dedupe(sorted(shown, key=sort_key))
    hidden = sorted(hidden, key=sort_key)

    # Browser-search fallback links from any source that offers them (e.g. eBay with
    # no API key). Collected for every passed source, so a source that could not run
    # still gives the user a way forward.
    external: list[Any] = []
    seen_urls: set[str] = set()
    for s in sources:
        for link in getattr(s, "browser_searches", lambda q: [])(query):
            if link.url not in seen_urls:
                seen_urls.add(link.url)
                external.append(link)

    outcome = SearchOutcome(
        query=query,
        generated_queries=generate_queries(query),
        normalized_oem=normalize_part_number(query.oem_number) or None,
        results=shown,
        hidden_results=hidden,
        statuses=statuses,
        oem_resolution=resolution,
        part_resolution=part_resolution,
        external_searches=external,
    )
    if storage:
        outcome.search_id = storage.save_search(outcome)
    return outcome
