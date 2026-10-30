"""Currency conversion behind a tiny interface.

StaticRates reads fixed rates from config.yaml. To use live rates later, write
another class with the same `to_eur` method and pass it to the search.
"""

from __future__ import annotations

from typing import Protocol

DEFAULT_RATES = {  # units of currency per 1 EUR
    "EUR": 1.0,
    "GBP": 0.85,
    "USD": 1.08,
    "BGN": 1.95583,  # fixed peg
    "PLN": 4.30,
    "CZK": 25.0,
}


class RateProvider(Protocol):
    def to_eur(self, amount: float | None, currency: str | None) -> float | None: ...


class StaticRates:
    def __init__(self, rates: dict[str, float] | None = None):
        self.rates = {k.upper(): float(v) for k, v in (rates or DEFAULT_RATES).items()}
        self.rates["EUR"] = 1.0

    def to_eur(self, amount: float | None, currency: str | None) -> float | None:
        if amount is None:
            return None
        rate = self.rates.get((currency or "EUR").upper())
        if rate is None:
            return None  # unknown currency: better no number than a wrong one
        return round(amount / rate, 2)
