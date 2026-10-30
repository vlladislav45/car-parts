"""Core data models shared by every source and by the UI."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SourceState(str, Enum):
    """Why a source produced the results it did, for the diagnostics panel.

    The distinction that matters: NO_RESULTS means the source ran and genuinely
    found nothing, while every other non-SUCCESS state means the source could not
    really answer the question (so "0 results" is not evidence of anything).
    """

    SUCCESS = "SUCCESS"              # ran and found at least one listing
    NO_RESULTS = "NO_RESULTS"        # ran cleanly, found nothing
    AUTH_REQUIRED = "AUTH_REQUIRED"  # needs credentials that are not configured
    BLOCKED = "BLOCKED"              # robots.txt disallowed, or 403/CAPTCHA
    RATE_LIMITED = "RATE_LIMITED"    # 429 / provider rate limit
    PARSING_ERROR = "PARSING_ERROR"  # fetched but could not parse (page changed?)
    UNAVAILABLE = "UNAVAILABLE"      # cannot be used at all (e.g. no legal access)
    NOT_SUPPORTED = "NOT_SUPPORTED"  # this search is out of scope (no usable query, wrong country)
    DISABLED = "DISABLED"            # turned off by the user

    @property
    def ran(self) -> bool:
        """True only when the source actually performed the search."""
        return self in (SourceState.SUCCESS, SourceState.NO_RESULTS)


class Condition(str, Enum):
    ANY = "any"
    USED = "used"
    NEW = "new"
    REFURBISHED = "refurbished"
    UNKNOWN = "unknown"


class OEMResolutionStatus(str, Enum):
    """How an OEM number was obtained, worst-to-best trust order last."""

    UNRESOLVED = "unresolved"              # nothing found; manual guidance returned
    USER_PROVIDED = "user_provided"        # the user typed it
    VERIFIED_MAPPING = "verified_mapping"  # a mapping the user verified earlier (local DB)
    CATALOG = "catalog"                    # a licensed catalog integration (optional, if configured)


class OEMResolutionResult(BaseModel):
    """Result of trying to turn a vehicle + part into an OEM number.

    Never fabricated: `oem_numbers` is only populated from the user, a mapping the
    user verified, or an authorized catalog. When nothing is found, `status` is
    UNRESOLVED and `guidance_url` points at a catalog to look it up by hand.
    """

    status: OEMResolutionStatus = OEMResolutionStatus.UNRESOLVED
    oem_numbers: list[str] = Field(default_factory=list)
    alternative_numbers: list[str] = Field(default_factory=list)  # superseded/alternatives, verified only
    source: str = ""                       # "user", "local verified mapping", catalog name
    vehicle_config: dict[str, str] = Field(default_factory=dict)  # config the numbers were verified against
    verified: bool = False
    confident: bool = True                 # False when the stored config differs from the query
    notes: list[str] = Field(default_factory=list)
    guidance_url: str | None = None
    mapping_id: int | None = None

    @property
    def resolved(self) -> bool:
        return bool(self.oem_numbers)

    @property
    def primary(self) -> str | None:
        return self.oem_numbers[0] if self.oem_numbers else None

    def all_numbers(self) -> list[str]:
        """Primary OEM numbers plus verified alternatives, de-duplicated, order kept."""
        return list(dict.fromkeys(self.oem_numbers + self.alternative_numbers))


class PartResolution(BaseModel):
    """How a user's part text mapped onto the canonical catalog (see catalog.py).

    `matched` means we found a canonical part; the original free text is always kept
    in `original_text`. An unmatched term is not an error - the search still runs on
    the original text, and `suggestion_ids` offers similar catalog entries.
    """

    matched: bool = False
    part_id: str = ""
    canonical_en: str = ""
    display_bg: str = ""
    category: str = ""
    match_type: str = "none"  # canonical_id | canonical_name | alias | prefix | token | fuzzy | ambiguous | none
    score: float = 0.0
    ambiguous: bool = False
    candidate_ids: list[str] = Field(default_factory=list)
    suggestion_ids: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    original_text: str = ""
    normalized_text: str = ""
    note: str = ""


class PartsQuery(BaseModel):
    """What the user is looking for."""

    make: str = ""
    model: str = ""
    year: int | None = None
    engine: str = ""
    part_name: str = ""
    part_id: str = ""  # canonical catalog id, set when the user picked an autocomplete suggestion
    oem_number: str = ""
    country: str = "Europe"
    condition: Condition = Condition.ANY
    drive: str = "any"  # "LHD", "RHD" or "any": left/right-hand drive of the car being repaired

    def vehicle_label(self) -> str:
        return " ".join(x for x in [self.make, self.model, str(self.year or "")] if x).strip()


class GeneratedQuery(BaseModel):
    """One search string derived from a PartsQuery.

    `kind` explains why it exists (useful in the debug panel).
    `language` lets a source pick only the queries that make sense for it.
    """

    text: str
    kind: str
    language: str = "any"  # "any", "en", "de", ...


class PartResult(BaseModel):
    """Normalized listing. Every source converts its data into this."""

    source: str
    title: str
    url: str
    price: float | None = None
    currency: str = "EUR"
    shipping_price: float | None = None  # None means unknown, 0.0 means free
    total_price: float | None = None  # only set when shipping is known
    condition: Condition = Condition.UNKNOWN
    seller: str | None = None
    part_number: str | None = None
    oem_numbers: list[str] = Field(default_factory=list)
    compatibility: str | None = None
    location: str | None = None
    image_url: str | None = None
    description: str | None = None
    price_is_minimum: bool = False  # e.g. "ab 99 EUR" / "from 99 EUR"
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Filled in by the pipeline (normalization, scoring, dedupe)
    query_used: str | None = None
    price_eur: float | None = None
    shipping_eur: float | None = None
    total_eur: float | None = None
    sort_price_eur: float | None = None  # total if known, otherwise item price (a lower bound)
    normalized_part_numbers: list[str] = Field(default_factory=list)
    relevance_score: int = 0
    relevance_reasons: list[str] = Field(default_factory=list)
    match_tier: int = 0  # 3 exact part number, 2 relevant, 1 weak, 0 likely unrelated
    duplicates: list[str] = Field(default_factory=list)  # "source | url" of merged listings

    @property
    def shipping_known(self) -> bool:
        return self.shipping_price is not None


class ExternalSearch(BaseModel):
    """A link to a marketplace's own search page, for the user to open themselves.

    Used as a fallback when a source cannot be queried programmatically (e.g. eBay
    without API credentials). These are NOT retrieved or parsed by the app: nothing
    here is a listing, a price or a compatibility claim.
    """

    source: str
    label: str
    url: str
    language: str = "any"
    note: str = ""


class SourceStatus(BaseModel):
    """Outcome of one source during one search (shown in the UI)."""

    name: str
    available: bool
    message: str = ""
    state: SourceState | None = None
    queries_run: list[str] = Field(default_factory=list)
    result_count: int = 0
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _default_state(self) -> "SourceStatus":
        # Safety net: if a caller did not set an explicit state, derive a plausible
        # one from the other fields. Callers that know better set `state` directly.
        if self.state is None:
            if not self.available:
                self.state = SourceState.UNAVAILABLE
            elif self.errors and self.result_count == 0:
                self.state = SourceState.PARSING_ERROR
            elif self.result_count > 0:
                self.state = SourceState.SUCCESS
            else:
                self.state = SourceState.NO_RESULTS
        return self


class SearchOutcome(BaseModel):
    query: PartsQuery
    generated_queries: list[GeneratedQuery]
    normalized_oem: str | None
    results: list[PartResult]
    hidden_results: list[PartResult]  # filtered by condition or tier 0
    statuses: list[SourceStatus]
    oem_resolution: OEMResolutionResult | None = None
    part_resolution: PartResolution | None = None
    external_searches: list[ExternalSearch] = Field(default_factory=list)
    search_id: int | None = None
