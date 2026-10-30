import pytest

from carparts.currency import StaticRates
from carparts.prices import parse_price, parse_shipping


@pytest.mark.parametrize("text,amount,currency", [
    ("30,19\xa0€", 30.19, "EUR"),
    ("1.234,56 €", 1234.56, "EUR"),
    ("£1,234.50", 1234.50, "GBP"),
    ("120 лв.", 120.0, "BGN"),
    ("450 zł", 450.0, "PLN"),
    ("2 500 Kč", 2500.0, "CZK"),
    ("US$ 99.99", 99.99, "USD"),
    ("1.234 €", 1234.0, "EUR"),
])
def test_parse_price(text, amount, currency):
    p = parse_price(text)
    assert p.amount == amount and p.currency == currency


def test_minimum_price():
    p = parse_price("ab531,12\xa0€")
    assert p.amount == 531.12 and p.is_minimum


def test_shipping():
    assert parse_shipping("Versand: kostenlos", "EUR").amount == 0.0
    assert parse_shipping("Versand: 5,95 €", "EUR").amount == 5.95
    assert parse_shipping(None) is None
    assert parse_shipping("Versand auf Anfrage") is None


def test_currency_conversion():
    rates = StaticRates({"EUR": 1, "GBP": 0.85, "BGN": 1.95583})
    assert rates.to_eur(85, "GBP") == 100.0
    assert rates.to_eur(195.583, "BGN") == 100.0
    assert rates.to_eur(10, "XYZ") is None
