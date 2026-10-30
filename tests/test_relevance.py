from carparts.models import Condition, PartResult, PartsQuery
from carparts.relevance import score_result, sort_key
from carparts.search import enrich
from carparts.currency import StaticRates

Q = PartsQuery(make="BMW", model="3 Series G20", year=2021, engine="320d", part_name="Front bumper",
               oem_number="51118080658", condition=Condition.USED)


def make(title, price, shipping=None, **kw):
    r = PartResult(source="t", title=title, url=f"https://x.test/{abs(hash(title))}", price=price,
                   shipping_price=shipping, **kw)
    enrich(r, StaticRates())
    return score_result(r, Q)


def test_cheap_unrelated_never_beats_exact_match():
    exact = make("BMW 3er G20 Stoßstange vorne 51 11 8 080 658", 150, 20)
    unrelated = make("Kennzeichenhalter Halterung universal", 50, 0)
    other_car = make("Audi A4 B9 Stoßstange vorne", 40, 0)
    ranked = sorted([unrelated, other_car, exact], key=sort_key)
    assert ranked[0] is exact
    assert exact.match_tier == 3
    assert unrelated.match_tier == 0 and other_car.match_tier < 2


def test_normalized_number_match():
    r = make("Stoßstange", 100, oem_numbers=["51-11-8-080-658"])
    assert r.match_tier == 3
    assert any("normalized" in x for x in r.relevance_reasons)


def test_rear_bumper_penalized():
    front = make("BMW 3er G20 Stoßstange vorne", 200)
    rear = make("BMW 3er G20 Stoßstange hinten", 200)
    assert front.relevance_score > rear.relevance_score
    assert any("opposite" in x for x in rear.relevance_reasons)


def test_other_chassis_penalized():
    g20 = make("BMW 3er G20 Stoßstange vorne", 200)
    f30 = make("BMW 3er F30 Stoßstange vorne", 200)
    assert g20.relevance_score - f30.relevance_score >= 25


def test_engine_code_is_not_a_chassis():
    r = make("BMW 3er G20 B47 Stoßstange vorne", 200)
    assert not any("chassis" in x for x in r.relevance_reasons)


def test_accessory_penalized():
    bumper = make("BMW G20 Stoßstange vorne", 200)
    grille = make("BMW G20 Gitter Stoßstange vorne", 30)
    assert grille.relevance_score < bumper.relevance_score


def test_same_tier_sorted_by_total_and_unknown_shipping_is_lower_bound():
    a = make("BMW 3er G20 Stoßstange vorne 51118080658", 150, 30)  # 180 total
    b = make("BMW 3er G20 Stoßstange vorne 51118080658", 170, None)  # 170 + shipping
    assert a.total_eur == 180 and b.total_eur is None and b.sort_price_eur == 170
    assert sorted([a, b], key=sort_key)[0] is b


def test_real_part_outranks_cheap_trim_and_bundle():
    bumper = make("Stoßstange vorne BMW 3er G20 51117422247", 180, 0, description="Ausführung: Limousine")
    trim = make("Front Bumper Center Moulding BMW 3 (G20)", 36, 0)
    sensor = make("Radarsensor SWA Stoßstange BMW 3er G20", 20, 0)
    bundle = make("Teilepaket Front BMW 3er G20 Stoßstange vorne", 100, 0)
    assert bumper.match_tier == 2
    assert {trim.match_tier, sensor.match_tier, bundle.match_tier} == {1}
    assert sorted([trim, sensor, bundle, bumper], key=sort_key)[0] is bumper


def test_bulgarian_listings():
    bumper = make("Предна броня за bmw g20 g21 M paket", 120.0)
    assert bumper.match_tier == 2, bumper.relevance_reasons  # "M paket" is a trim, not a bundle
    bracket = make("Основа лява за предна броня на BMW G20 320", 35.0)
    rear = make("Задна броня BMW G20", 50.0)
    assert bracket.match_tier < 2 and rear.match_tier < 2
    assert sorted([rear, bracket, bumper], key=sort_key)[0] is bumper


def test_m_package_is_not_a_bundle_but_a_parts_package_is():
    assert not any("bundle" in x for x in make("BMW G20 Stoßstange vorne M-Paket", 200.0).relevance_reasons)
    assert any("bundle" in x for x in make("BMW G20 Stoßstange vorne Teilepaket", 200.0).relevance_reasons)


def test_preferred_country_matches_country_name():
    r = PartResult(source="t", title="Предна броня BMW G20", url="https://x.test/bg", price=100.0,
                   location="гр. София, Bulgaria")
    assert "+5 preferred country" in score_result(r, Q, "BG").relevance_reasons
    assert "+5 preferred country" not in score_result(r, Q, "DE").relevance_reasons


def test_left_right():
    q = PartsQuery(make="BMW", model="3 Series G20", part_name="Left headlight")

    def scored(title):
        return score_result(PartResult(source="t", title=title, url=f"https://x.test/{title}", price=100.0), q)

    left, right, bg_left, unknown = (scored(t) for t in (
        "Scheinwerfer links BMW G20", "Scheinwerfer rechts BMW G20", "Фар ляв BMW G20", "Scheinwerfer BMW G20 LED"))
    assert left.match_tier == bg_left.match_tier == unknown.match_tier == 2
    assert right.match_tier < 2
    assert left.relevance_score > unknown.relevance_score


def test_left_and_right_hand_drive():
    q = PartsQuery(make="BMW", model="3 Series G20", part_name="Left headlight", drive="LHD")

    def scored(title, query=q):
        return score_result(PartResult(source="t", title=title, url=f"https://x.test/{title}", price=100.0), query)

    rhd = scored("BMW G20 headlight left RHD UK")
    lhd = scored("BMW G20 Scheinwerfer links Linkslenker")
    plain = scored("BMW G20 Scheinwerfer links")
    assert rhd.match_tier < 2 and lhd.match_tier == plain.match_tier == 2
    assert lhd.relevance_score > plain.relevance_score
    # A bumper is the same part on LHD and RHD cars: tiny note, not a demotion.
    bumper = scored("BMW G20 front bumper RHD", PartsQuery(make="BMW", model="3 Series G20",
                                                           part_name="Front bumper", drive="LHD"))
    assert bumper.match_tier == 2
    # "any" ignores drive completely.
    assert scored("BMW G20 headlight left RHD", PartsQuery(make="BMW", model="3 Series G20",
                                                           part_name="Left headlight")).match_tier == 2
