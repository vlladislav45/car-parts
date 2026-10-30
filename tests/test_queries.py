from carparts.models import Condition, PartsQuery
from carparts.queries import generate_queries

Q = PartsQuery(make="BMW", model="3 Series G20", year=2021, engine="320d", part_name="Front bumper",
               oem_number="51 11 8 080 658", condition=Condition.USED)


def test_expected_queries_in_order():
    texts = [g.text for g in generate_queries(Q)]
    assert texts == [
        "51118080658",
        "BMW 51118080658",
        "BMW G20 51118080658",
        "BMW G20 Front bumper",
        "BMW G20 Front bumper used",
        "BMW G20 Stoßstange vorne",
        "BMW G20 Stoßfänger vorne",
        "предна броня BMW G20",
        "zderzak przedni BMW G20",
        "BMW G20 Ersatzteile",
        "части BMW G20",
        "części BMW G20",
    ]


def test_languages_are_tagged():
    by_lang = {}
    for g in generate_queries(Q):
        by_lang.setdefault(g.language, []).append(g.text)
    assert by_lang["bg"] == ["предна броня BMW G20", "части BMW G20"]
    assert by_lang["pl"] == ["zderzak przedni BMW G20", "części BMW G20"]
    assert "BMW G20 Stoßstange vorne" in by_lang["de"]


def test_deterministic_and_capped():
    assert generate_queries(Q) == generate_queries(Q)
    assert len(generate_queries(Q, max_queries=3)) == 3


def test_without_oem():
    texts = [g.text for g in generate_queries(PartsQuery(make="VW", model="Golf", part_name="headlight"))]
    assert texts[0] == "VW Golf headlight"
    assert "VW Golf Scheinwerfer" in texts
    assert "reflektor VW Golf" in texts  # Polish


def test_polish_queries_are_tagged_and_optional():
    # A part with a Polish entry produces a pl-tagged query.
    texts = [(g.text, g.language) for g in generate_queries(PartsQuery(make="Audi", model="A4", part_name="fender"))]
    assert ("błotnik Audi A4", "pl") in texts
    # A part with no Polish entry produces no pl part query (only the generic one).
    langs = [g.language for g in generate_queries(PartsQuery(make="Audi", model="A4", part_name="flux capacitor"))]
    # "flux capacitor" has no translation in any language, so only en + generic de/bg/pl appear.
    assert "pl" in langs  # the generic "części Audi A4" is still offered


def test_side_carried_into_german_queries():
    texts = [g.text for g in generate_queries(PartsQuery(make="BMW", model="3 Series G20", part_name="Right mirror"))]
    assert "BMW G20 Außenspiegel rechts" in texts
