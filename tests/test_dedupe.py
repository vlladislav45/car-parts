from carparts.models import Condition, PartResult
from carparts.dedupe import dedupe, is_duplicate


def r(title, url, price, seller=None, nums=(), cond=Condition.USED):
    return PartResult(source="s", title=title, url=url, price=price, price_eur=price, seller=seller,
                      normalized_part_numbers=list(nums), condition=cond)


def test_same_url_is_duplicate():
    a = r("A", "https://www.shop.de/p/1?ref=x", 10)
    b = r("B", "https://shop.de/p/1", 12)
    assert is_duplicate(a, b)


def test_same_offer_relisted():
    a = r("BMW G20 Stoßstange vorne 51118080658", "https://s.de/1", 150, "breaker1", ["51118080658"])
    b = r("BMW G20 Stoßstange vorne 51118080658 ", "https://s.de/2", 150, "breaker1", ["51118080658"])
    out = dedupe([a, b])
    assert out == [a] and a.duplicates


def test_genuinely_different_listings_kept():
    base = r("BMW G20 Stoßstange vorne 51118080658", "https://s.de/1", 150, "breaker1", ["51118080658"])
    other_seller = r(base.title, "https://s.de/2", 150, "breaker2", ["51118080658"])
    other_price = r(base.title, "https://s.de/3", 180, "breaker1", ["51118080658"])
    other_cond = r(base.title, "https://s.de/4", 150, "breaker1", ["51118080658"], Condition.NEW)
    other_number = r("BMW G20 Stoßstange vorne 51118496503", "https://s.de/5", 150, "breaker1", ["51118496503"])
    no_strong_signal = r(base.title, "https://t.de/6", 150)  # no seller, no numbers on either
    candidates = [other_seller, other_price, other_cond, other_number]
    assert len(dedupe([base] + candidates)) == 5
    assert not is_duplicate(r(base.title, "https://a.de/1", 150), no_strong_signal)
