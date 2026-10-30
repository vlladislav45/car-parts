"""Parse price strings like "30,19 EUR", "1.234,56 €", "£45.00", "ab 99 €", "120 лв"."""

from __future__ import annotations

import re
from dataclasses import dataclass

CURRENCY_SYMBOLS = {
    "€": "EUR", "EUR": "EUR", "EURO": "EUR",
    "£": "GBP", "GBP": "GBP",
    "US$": "USD", "$": "USD", "USD": "USD",
    "ЛВ": "BGN", "ЛВ.": "BGN", "BGN": "BGN", "LEV": "BGN",
    "ZŁ": "PLN", "ZL": "PLN", "PLN": "PLN",
    "KČ": "CZK", "KC": "CZK", "CZK": "CZK",
}

FREE_WORDS = ("kostenlos", "gratis", "free", "frei", "versandkostenfrei", "darmowa", "zdarma", "безплатна")
MINIMUM_WORDS = ("ab", "from", "od", "от")


@dataclass
class ParsedPrice:
    amount: float
    currency: str | None
    is_minimum: bool = False


def parse_price(text: str | None, default_currency: str | None = None) -> ParsedPrice | None:
    if not text:
        return None
    raw = text.replace("\xa0", " ").strip()
    low = raw.lower()
    is_min = any(low.startswith(w) for w in MINIMUM_WORDS)
    currency = detect_currency(raw) or default_currency
    m = re.search(r"\d[\d.,' ]*", raw)
    if not m:
        return None
    amount = _parse_number(m.group(0).strip())
    if amount is None:
        return None
    return ParsedPrice(amount=amount, currency=currency, is_minimum=is_min)


def parse_shipping(text: str | None, default_currency: str | None = None) -> ParsedPrice | None:
    """Return 0.0 for free shipping, a price if one is found, None if unknown."""
    if not text:
        return None
    low = text.lower()
    if any(re.search(r"\b%s\b" % re.escape(w), low) for w in FREE_WORDS):
        return ParsedPrice(0.0, default_currency)
    return parse_price(text, default_currency)


def detect_currency(text: str) -> str | None:
    up = text.upper()
    # Longest symbols first so "US$" wins over "$".
    for sym in sorted(CURRENCY_SYMBOLS, key=len, reverse=True):
        if sym.isalpha() or sym.endswith("."):
            if re.search(r"(?<![A-ZА-Я])%s(?![A-ZА-Я])" % re.escape(sym), up):
                return CURRENCY_SYMBOLS[sym]
        elif sym in up:
            return CURRENCY_SYMBOLS[sym]
    return None


def _parse_number(s: str) -> float | None:
    s = s.replace(" ", "").replace("'", "").rstrip(".,")
    if not s:
        return None
    last_comma, last_dot = s.rfind(","), s.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        # The later separator is the decimal separator.
        if last_comma > last_dot:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif last_comma >= 0:
        decimals = len(s) - last_comma - 1
        if s.count(",") == 1 and decimals in (1, 2):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")  # thousands separator: "1,234"
    elif last_dot >= 0:
        decimals = len(s) - last_dot - 1
        if s.count(".") > 1 or decimals == 3:
            s = s.replace(".", "")  # "1.234" or "1.234.567"
    try:
        return round(float(s), 2)
    except ValueError:
        return None
