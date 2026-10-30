"""Config-driven dealer/marketplace scraper.

Each site is described in config.yaml: a search URL template and either CSS
selectors or "jsonld" (schema.org Product/Offer data, which many shops embed).
No site's HTML structure is hard-coded here.

Field spec forms (under extract.fields):
    title: ".itemTitle"                              # text of first match
    url: {selector: ".itemTitle", attr: "data-href64", decode: base64}
    oem_numbers: {label: "OE:"}                      # <dt>OE:</dt><dd>value</dd>
    image_url: {selector: "img", attr: "src"}
    url: [{selector: "a.title", attr: "href"}, {selector: ".title", attr: "data-href"}]  # alternatives
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import quote, quote_plus, urljoin

from bs4 import BeautifulSoup, Tag

from ..http import PoliteClient
from ..part_numbers import looks_like_part_number
from ..models import Condition, GeneratedQuery, PartResult, PartsQuery
from ..prices import parse_price, parse_shipping
from ..vocabulary import detect_condition
from .base import BaseSource


class GenericDealerSource(BaseSource):
    def __init__(self, config: dict[str, Any], client: PoliteClient):
        self.config = config
        self.client = client
        self.name = config["name"]
        self.base_url = config["base_url"].rstrip("/") + "/"
        self.search_url_template = config["search_url_template"]
        self.query_encoding = config.get("query_encoding", "plus")
        self.currency = config.get("currency", "EUR")
        self.countries = config.get("countries", ["EU"])
        self.languages = config.get("languages", ["any", "en", "de"])
        self.max_queries = int(config.get("max_queries", 6))
        self.delay = float(config.get("request_delay_seconds", 2.0))
        self.location = config.get("location")
        # Classifieds often use 0 or 1 as a placeholder ("call me"); treat those as unknown.
        self.min_price = float(config.get("min_price", 0))
        # For sites that only sell one kind (e.g. a breaker: everything is used).
        self.default_condition = Condition(config.get("default_condition", "unknown"))
        self.extract = config.get("extract", {"strategy": "jsonld"})
        self.available = config.get("available", True)
        self.unavailable_reason = config.get("unavailable_reason", "")
        super().__init__()

    def build_url(self, text: str) -> str:
        if self.query_encoding == "plus":
            encoded = quote_plus(text)
        elif self.query_encoding == "dash":
            encoded = quote(re.sub(r"\s+", "-", text.strip()))
        else:
            encoded = quote(text)
        return urljoin(self.base_url, self.search_url_template.format(query=encoded))

    def search_text(self, generated: GeneratedQuery, query: PartsQuery) -> list[PartResult]:
        resp = self.client.get(self.build_url(generated.text), delay=self.delay)
        if resp.status in (404, 410):  # many shops answer "no results" this way
            return []
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return self.parse(resp.text, resp.url)

    # Parsing

    def parse(self, html: str, page_url: str | None = None) -> list[PartResult]:
        soup = BeautifulSoup(html, "lxml")
        strategy = self.extract.get("strategy", "auto")
        results: list[PartResult] = []
        if strategy in ("jsonld", "auto"):
            results = parse_jsonld(soup, self.name, page_url or self.base_url, self.currency)
        if not results and strategy in ("css", "auto") and self.extract.get("item"):
            results = self._parse_css(soup)
        for r in results:
            if not r.location:
                r.location = self.location
            elif self.location and self.location.lower() not in r.location.lower():
                r.location = f"{r.location}, {self.location}"
            if r.condition == Condition.UNKNOWN:
                r.condition = self.default_condition
            if r.price is not None and r.price < self.min_price:
                r.price = r.total_price = None
        return results

    def _parse_css(self, soup: BeautifulSoup) -> list[PartResult]:
        fields = self.extract.get("fields", {})
        out: list[PartResult] = []
        for item in soup.select(self.extract["item"]):
            get = lambda key: _field(item, fields.get(key))  # noqa: E731
            title = get("title")
            href = get("url")
            if not title or not href:
                continue
            price = parse_price(get("price"), self.currency)
            shipping = parse_shipping(get("shipping"), self.currency) if fields.get("shipping") else None
            cond_text = get("condition")
            oem = get("oem_numbers")
            description = get("description")
            r = PartResult(
                source=self.name,
                title=title,
                url=urljoin(self.base_url, href),
                price=price.amount if price else None,
                currency=(price.currency if price and price.currency else self.currency),
                shipping_price=shipping.amount if shipping else None,
                condition=_condition(cond_text or ""),
                seller=get("seller"),
                part_number=_clean_part_number(get("part_number")),
                oem_numbers=[x.strip() for x in re.split(r"[,;/]", oem) if x.strip()] if oem else [],
                compatibility=get("compatibility"),
                location=get("location"),
                image_url=urljoin(self.base_url, get("image_url")) if get("image_url") else None,
                description=description[:500] if description else None,
                price_is_minimum=bool(price and price.is_minimum),
            )
            if r.shipping_price is not None and r.price is not None:
                r.total_price = round(r.price + r.shipping_price, 2)
            out.append(r)
        return out


def _field(item: Tag, spec: Any) -> str | None:
    if not spec:
        return None
    if isinstance(spec, list):  # alternatives, first non-empty wins
        for alt in spec:
            value = _field(item, alt)
            if value:
                return value
        return None
    if isinstance(spec, str):
        spec = {"selector": spec}
    if "label" in spec:
        value = _labelled_value(item, spec["label"])
    else:
        el = item.select_one(spec["selector"]) if spec.get("selector") else item
        if el is None:
            return None
        attr = spec.get("attr")
        value = el.get(attr) if attr else el.get_text(" ", strip=True)
        if isinstance(value, list):
            value = " ".join(value)
    if value and spec.get("decode") == "base64":
        try:
            value = base64.b64decode(value).decode("utf-8")
        except Exception:
            return None
    if value and spec.get("strip_prefix"):
        value = re.sub(r"^\s*%s\s*" % re.escape(spec["strip_prefix"]), "", value, flags=re.I)
    return value.strip() if value else None


def _clean_part_number(value: str | None) -> str | None:
    """Some sites pack several fields into one ("|66316883865|BMW||"). Keep the number."""
    if not value:
        return None
    tokens = [t.strip() for t in re.split(r"[|;]", value) if t.strip()]
    for t in tokens:
        if looks_like_part_number(t):
            return t
    return tokens[0] if tokens else None


def _labelled_value(item: Tag, label: str) -> str | None:
    """Value next to a label: <dt>OE:</dt><dd>value</dd>, or <li><b>OE</b>: value</li>."""
    want = label.strip().lower().rstrip(":")
    for dt in item.find_all("dt"):
        if dt.get_text(" ", strip=True).lower().rstrip(":") == want:
            dd = dt.find_next_sibling("dd")
            if dd:
                return dd.get_text("\n", strip=True)
    for b in item.find_all(["b", "strong"]):
        if b.get_text(" ", strip=True).lower().rstrip(":") == want and b.parent is not None:
            rest = b.parent.get_text(" ", strip=True)[len(b.get_text(" ", strip=True)):]
            value = rest.strip().lstrip(":").strip()
            if value:
                return value
    return None


def _condition(text: str) -> Condition:
    found = detect_condition(text)
    return Condition(found) if found else Condition.UNKNOWN


# JSON-LD (schema.org) parsing, shared with any source that wants it

_SCHEMA_CONDITION = {
    "usedcondition": Condition.USED,
    "newcondition": Condition.NEW,
    "refurbishedcondition": Condition.REFURBISHED,
    "damagedcondition": Condition.USED,
}


def parse_jsonld(soup: BeautifulSoup, source: str, page_url: str, default_currency: str) -> list[PartResult]:
    products: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        _collect_products(data, products)

    out: list[PartResult] = []
    for p in products:
        name = p.get("name")
        offers = p.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if offers.get("@type") == "AggregateOffer":
            price_raw, is_min = offers.get("lowPrice"), True
        else:
            price_raw, is_min = offers.get("price"), False
        url = p.get("url") or offers.get("url")
        if not name or not url:
            continue
        price = parse_price(str(price_raw), default_currency) if price_raw not in (None, "") else None
        currency = offers.get("priceCurrency") or default_currency
        shipping = None
        details = offers.get("shippingDetails")
        if isinstance(details, list):
            details = details[0] if details else None
        if isinstance(details, dict):
            rate = details.get("shippingRate") or {}
            if rate.get("value") not in (None, ""):
                shipping = float(str(rate["value"]).replace(",", "."))
        cond_raw = str(offers.get("itemCondition") or p.get("itemCondition") or "")
        cond = _SCHEMA_CONDITION.get(cond_raw.rsplit("/", 1)[-1].lower(), Condition.UNKNOWN)
        seller = offers.get("seller")
        image = p.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("url")
        r = PartResult(
            source=source,
            title=str(name),
            url=urljoin(page_url, str(url)),
            price=price.amount if price else None,
            currency=str(currency),
            shipping_price=shipping,
            condition=cond,
            seller=seller.get("name") if isinstance(seller, dict) else (seller if isinstance(seller, str) else None),
            part_number=p.get("mpn") or p.get("sku"),
            image_url=image if isinstance(image, str) else None,
            description=(str(p.get("description"))[:500] if p.get("description") else None),
            price_is_minimum=is_min,
        )
        if r.shipping_price is not None and r.price is not None:
            r.total_price = round(r.price + r.shipping_price, 2)
        out.append(r)
    return out


def _collect_products(data: Any, out: list[dict]) -> None:
    if isinstance(data, list):
        for x in data:
            _collect_products(x, out)
        return
    if not isinstance(data, dict):
        return
    types = data.get("@type")
    types = types if isinstance(types, list) else [types]
    if "Product" in types:
        out.append(data)
    for key in ("@graph", "itemListElement", "item"):
        if key in data:
            _collect_products(data[key], out)
