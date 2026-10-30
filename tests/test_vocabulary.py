import pytest

from carparts.vocabulary import (
    PART_TRANSLATIONS_BG,
    PART_TRANSLATIONS_DE,
    PART_TRANSLATIONS_PL,
    translate_part,
)


def test_every_part_name_has_german_and_bulgarian():
    assert set(PART_TRANSLATIONS_DE) == set(PART_TRANSLATIONS_BG)
    for table in (PART_TRANSLATIONS_DE, PART_TRANSLATIONS_BG, PART_TRANSLATIONS_PL):
        for name, terms in table.items():
            assert name == name.lower().strip(), name
            assert terms and all(t.strip() for t in terms), name


def test_polish_is_a_consistent_subset():
    # Polish is allowed to be partial, but every Polish key must be a real part
    # name that also exists in the German table (no typos, no orphan keys).
    extra = set(PART_TRANSLATIONS_PL) - set(PART_TRANSLATIONS_DE)
    assert not extra, f"Polish keys not present in the German table: {sorted(extra)}"


@pytest.mark.parametrize("name, de, bg", [
    ("Front bumper grille", "Stoßstangengitter", "решетка броня"),  # longest name wins over "front bumper"
    ("Left door mirror", "Außenspiegel", "огледало"),
    ("driver airbag", "Fahrerairbag", "airbag волан"),
    ("exhaust manifold", "Abgaskrümmer", "изпускателен колектор"),
    ("Throttle body", "Drosselklappe", "дроселова клапа"),
    ("rear axle", "Hinterachse", "заден мост"),
])
def test_lookup(name, de, bg):
    assert translate_part(name, "de")[0] == de
    assert translate_part(name, "bg")[0] == bg


@pytest.mark.parametrize("name, pl", [
    ("Front bumper", "zderzak przedni"),
    ("Left headlight", "reflektor"),  # side word stripped from stored term, longest key still wins
    ("rear bumper", "zderzak tylny"),
    ("Throttle body", "przepustnica"),
])
def test_polish_lookup(name, pl):
    assert translate_part(name, "pl")[0] == pl


def test_polish_unknown_name_has_no_translation():
    assert translate_part("flux capacitor", "pl") == []


@pytest.mark.parametrize("name, de, bg, pl", [
    ("rear suspension", "Fahrwerk hinten", "задно окачване", "zawieszenie tylne"),
    ("front suspension", "Fahrwerk vorne", "предно окачване", "zawieszenie przednie"),
    ("suspension", "Fahrwerk", "окачване", "zawieszenie"),
    ("ball joint", "Traggelenk", "шарнир", "sworzeń wahacza"),
    ("tie rod end", "Spurstangenkopf", "кормилен накрайник", "końcówka drążka kierowniczego"),
])
def test_suspension_terms(name, de, bg, pl):
    assert translate_part(name, "de")[0] == de
    assert translate_part(name, "bg")[0] == bg
    assert translate_part(name, "pl")[0] == pl


def test_unknown_name_has_no_translation():
    assert translate_part("flux capacitor", "de") == []
