"""eBay sources.

EbayWebSource: scraping eBay search pages is not possible within the rules.
ebay.de/ebay.co.uk robots.txt disallows /sch/ (search) for all agents and the
pages answer 403 to non-browser clients. The adapter exists so the UI can show
the status, but it never makes requests.

EbayBrowseApiSource: the official, free eBay Browse API. Enabled when
EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are set (create a free keyset at
https://developer.ebay.com, or put them in .env). Verified against the live API
on 2026-10-15 and covered by tests with a mocked transport.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any
from urllib.parse import quote_plus

import httpx

from ..models import Condition, ExternalSearch, GeneratedQuery, PartResult, PartsQuery, SourceState
from ..part_numbers import normalize_part_number
from .base import BaseSource, SourceUnavailable

# eBay marketplace id -> the site domain its search pages live on.
MARKETPLACE_DOMAINS = {
    "EBAY_DE": "ebay.de", "EBAY_GB": "ebay.co.uk", "EBAY_PL": "ebay.pl", "EBAY_AT": "ebay.at",
    "EBAY_FR": "ebay.fr", "EBAY_IT": "ebay.it", "EBAY_ES": "ebay.es", "EBAY_NL": "ebay.nl",
    "EBAY_BE": "ebay.be", "EBAY_US": "ebay.com",
}


def ebay_search_links(query: PartsQuery, marketplace: str = "EBAY_DE") -> list[ExternalSearch]:
    """Build (not fetch) eBay search-page URLs the user can open themselves.

    Prefers the OEM number when present; otherwise the vehicle + part name. These
    are plain links to eBay's public search page, never scraped by the app.
    """
    domain = MARKETPLACE_DOMAINS.get(marketplace, "ebay.de")
    terms: list[tuple[str, str]] = []
    oem = normalize_part_number(query.oem_number)
    if oem:
        terms.append((oem, "by OEM number"))
    vehicle = " ".join(x for x in (query.make.strip(), query.model.strip()) if x)
    part = query.part_name.strip()
    if vehicle and part:
        terms.append((f"{vehicle} {part}", "by vehicle and part"))
    elif part:
        terms.append((part, "by part name"))
    out: list[ExternalSearch] = []
    for text, how in terms:
        out.append(ExternalSearch(
            source="eBay (web)",
            label=f"Search {domain} {how}: {text}",
            url=f"https://www.{domain}/sch/i.html?_nkw={quote_plus(text)}",
            note="Opens eBay's search page in your browser. Results are not retrieved or checked by this app.",
        ))
    return out

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"

MARKETPLACES = {"DE": "EBAY_DE", "GB": "EBAY_GB", "UK": "EBAY_GB", "PL": "EBAY_PL", "AT": "EBAY_AT",
                "FR": "EBAY_FR", "IT": "EBAY_IT", "ES": "EBAY_ES", "NL": "EBAY_NL", "BE": "EBAY_BE"}

_CONDITIONS = {"USED": Condition.USED, "NEW": Condition.NEW}


def _condition(item: dict) -> Condition:
    """Map eBay's numeric conditionId; the text is localized ("Gebraucht" on EBAY_DE)."""
    try:
        cid = int(item.get("conditionId", ""))
    except ValueError:
        return _CONDITIONS.get(str(item.get("condition", "")).upper(), Condition.UNKNOWN)
    if cid < 2000:
        return Condition.NEW  # 1000 new, 1500 new other, 1750 new with defects
    if cid < 3000:
        return Condition.REFURBISHED
    return Condition.USED  # 3000-6000 used grades, 7000 for parts / not working


class EbayWebSource(BaseSource):
    name = "eBay (web)"
    available = False
    unavailable_state = SourceState.BLOCKED
    unavailable_reason = (
        "Unavailable for scraping: eBay robots.txt disallows /sch/ and returns HTTP 403 to non-browser "
        "clients. Offers browser-search links instead; set EBAY_CLIENT_ID / EBAY_CLIENT_SECRET for the API."
    )

    def __init__(self, marketplace: str = "EBAY_DE"):
        self.marketplace = marketplace
        super().__init__()

    def browser_searches(self, query: PartsQuery) -> list[ExternalSearch]:
        return ebay_search_links(query, self.marketplace)


class EbayBrowseApiSource(BaseSource):
    name = "eBay (Browse API)"
    countries = ["EU"]
    languages = ["any", "en", "de"]
    max_queries = 4

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 marketplace: str = "EBAY_DE", http: httpx.Client | None = None, limit: int = 50):
        self.client_id = client_id or os.environ.get("EBAY_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("EBAY_CLIENT_SECRET", "")
        self.marketplace = marketplace
        self.http = http or httpx.Client(timeout=20)
        self.limit = limit
        self._token: str | None = None
        self._token_expires = 0.0
        self.available = bool(self.client_id and self.client_secret)
        self.unavailable_reason = "" if self.available else "Not configured: set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET."
        self.unavailable_state = SourceState.SUCCESS if self.available else SourceState.AUTH_REQUIRED
        super().__init__()

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        resp = self.http.post(
            TOKEN_URL,
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": SCOPE},
        )
        if resp.status_code in (401, 403):
            raise SourceUnavailable(f"eBay token rejected: HTTP {resp.status_code} (check credentials)",
                                    SourceState.AUTH_REQUIRED)
        if resp.status_code != 200:
            raise SourceUnavailable(f"eBay token request failed: HTTP {resp.status_code}")
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + float(data.get("expires_in", 7200))
        return self._token

    def browser_searches(self, query: PartsQuery) -> list[ExternalSearch]:
        # When the API is not configured, still offer manual search links so the
        # user is not left with nothing while waiting for credentials.
        return [] if self.available else ebay_search_links(query, self.marketplace)

    def search_text(self, generated: GeneratedQuery, query: PartsQuery) -> list[PartResult]:
        params: dict[str, Any] = {"q": generated.text, "limit": self.limit}
        if query.condition in (Condition.USED, Condition.NEW):
            params["filter"] = f"conditions:{{{query.condition.value.upper()}}}"
        resp = self.http.get(
            SEARCH_URL,
            params=params,
            headers={"Authorization": f"Bearer {self._get_token()}", "X-EBAY-C-MARKETPLACE-ID": self.marketplace},
        )
        if resp.status_code == 429:
            raise SourceUnavailable("eBay API rate limit reached", SourceState.RATE_LIMITED)
        if resp.status_code != 200:
            raise RuntimeError(f"eBay API HTTP {resp.status_code}")
        return [self._to_result(item) for item in resp.json().get("itemSummaries", [])]

    def _to_result(self, item: dict) -> PartResult:
        price = item.get("price") or {}
        shipping = None
        ship_currency = None
        for opt in item.get("shippingOptions") or []:
            cost = opt.get("shippingCost")
            if cost and cost.get("value") is not None:
                shipping, ship_currency = float(cost["value"]), cost.get("currency")
                break
        currency = price.get("currency", "EUR")
        if ship_currency and ship_currency != currency:
            shipping = None  # don't mix currencies in one total
        amount = float(price["value"]) if price.get("value") is not None else None
        loc = item.get("itemLocation") or {}
        r = PartResult(
            source=self.name,
            title=item.get("title", ""),
            url=item.get("itemWebUrl", ""),
            price=amount,
            currency=currency,
            shipping_price=shipping,
            condition=_condition(item),
            seller=(item.get("seller") or {}).get("username"),
            location=", ".join(x for x in (loc.get("city"), loc.get("country")) if x) or None,
            image_url=(item.get("image") or {}).get("imageUrl"),
        )
        if amount is not None and shipping is not None:
            r.total_price = round(amount + shipping, 2)
        return r
