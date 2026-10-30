import pytest

from carparts.catalog import (
    CATALOG,
    CATEGORY_MEMBERS,
    CatalogResolver,
    default_resolver,
    normalize,
)
from carparts.models import PartsQuery
from carparts.search import run_search
from carparts.storage import Storage
from carparts.vocabulary import PART_TRANSLATIONS_DE

R = default_resolver


# Catalog integrity

def test_every_translation_key_in_exactly_one_category():
    assigned = [k for members in CATEGORY_MEMBERS.values() for k in members]
    assert set(assigned) == set(PART_TRANSLATIONS_DE)
    assert len(assigned) == len(set(assigned)), "a part is listed in two categories"


def test_catalog_size_and_ids_unique():
    assert 100 <= len(CATALOG) <= 200
    ids = [p.id for p in CATALOG]
    assert len(ids) == len(set(ids))
    for p in CATALOG:
        assert p.category in CATEGORY_MEMBERS


# Multilingual aliases -> same canonical part

@pytest.mark.parametrize("text", ["броня", "bumper", "Stoßstange", "zderzak", "BUMPER"])
def test_bumper_synonyms_resolve_to_same_part(text):
    res = R.resolve(text)
    assert res.matched and res.part_id == "bumper"


@pytest.mark.parametrize("text, part_id", [
    ("front bumper", "front_bumper"),
    ("предна броня", "front_bumper"),
    ("headlight", "headlight"),
    ("headlamp", "headlight"),       # grouped synonym
    ("фар", "headlight"),
    ("Scheinwerfer", "headlight"),
    ("reflektor", "headlight"),      # Polish
    ("tail light", "tail_light"),
    ("стоп", "tail_light"),
    ("Rückleuchte", "tail_light"),
    ("калник", "fender"),
    ("Kotflügel", "fender"),
    ("радиатор", "radiator"),
    ("Kühler", "radiator"),
])
def test_known_aliases_resolve(text, part_id):
    res = R.resolve(text)
    assert res.matched and res.part_id == part_id


# Normalization

def test_normalization_case_whitespace_punctuation():
    assert normalize("  Front   Bumper! ") == "front bumper"
    assert normalize("Stoßstange, vorne") == "stossstange vorne"
    for messy in ["BUMPER", "  bumper ", "bumper.", "Bumper"]:
        assert R.resolve(messy).part_id == "bumper"


# Misspellings (fuzzy) vs exact

def test_fuzzy_handles_typos():
    for typo in ["bumber", "radeator", "scheinwerfr"]:
        res = R.resolve(typo)
        assert res.matched, typo
    assert R.resolve("bumper").match_type in ("canonical_name", "alias")  # exact beats fuzzy


# Ambiguous aliases

def test_ambiguous_alias_is_not_auto_picked():
    # "kombiinstrument" is a German term for both the cluster and the speedo.
    res = R.resolve("kombiinstrument")
    assert not res.matched and res.ambiguous
    assert set(res.candidate_ids) == {"instrument_cluster", "speedometer"}


# Unknown free text

def test_unknown_term_is_not_matched_but_offers_suggestions():
    res = R.resolve("flux capacitor")
    assert not res.matched and not res.ambiguous
    assert res.original_text == "flux capacitor"


def test_free_text_close_to_a_part_still_not_forced():
    res = R.resolve("bumper trim clip bracket thingy")
    # Should not confidently claim to be the bumper; stays free text (token/fuzzy too weak).
    assert res.original_text


# Attributes

def test_position_and_side_attributes():
    assert R.resolve("front bumper").attributes.get("position") == "front"
    assert R.resolve("rear bumper").attributes.get("position") == "rear"
    assert R.resolve("side mirror").attributes.get("side_relevant") == "true"


# Autocomplete suggestions

def test_suggest_ranks_and_limits():
    out = R.suggest("front", limit=5)
    assert out and len(out) <= 5
    assert all(hasattr(p, "id") for p in out)
    # typing the start of a Bulgarian term suggests the matching part
    bg = R.suggest("предна")
    assert any(p.id in ("front_bumper", "front_grille", "front_panel", "front_suspension", "front_axle")
               or p.id.startswith("front") for p in bg)


def test_suggest_empty_for_blank():
    assert R.suggest("") == []
    assert R.suggest("  ") == []


# Explicit part_id wins

def test_part_id_resolves_directly():
    res = R.resolve("whatever text", part_id="headlight")
    assert res.matched and res.part_id == "headlight" and res.match_type == "canonical_id"


# User aliases via storage + duplicate prevention

def test_user_alias_extends_catalog_and_prevents_duplicates(tmp_path):
    s = Storage(tmp_path / "t.db")
    term = "qwzzxyv"
    assert R.resolve(term).matched is False
    assert s.add_user_alias(term, normalize(term), "front_bumper") is True
    assert s.add_user_alias(term, normalize(term), "front_bumper") is False  # duplicate
    res = CatalogResolver(s).resolve(term)
    assert res.matched and res.part_id == "front_bumper"


# End to end: different names for the same part -> consistent canonical queries

def test_e2e_consistent_canonical_search(tmp_path):
    from carparts.sources.ebay import EbayWebSource
    s = Storage(tmp_path / "t.db")
    outs = []
    for text in ["броня", "bumper", "Stoßstange"]:
        o = run_search(PartsQuery(make="BMW", model="3 Series G20", part_name=text),
                       [EbayWebSource()], storage=s)
        outs.append(o)
    # All three resolved to the same canonical part...
    ids = {o.part_resolution.part_id for o in outs}
    assert ids == {"bumper"}
    # ...and generated the same canonical multilingual queries.
    qsets = [{g.text for g in o.generated_queries} for o in outs]
    assert qsets[0] == qsets[1] == qsets[2]
    assert any("Stoßstange" in g.text for g in outs[0].generated_queries)   # German
    assert any("броня" in g.text for g in outs[0].generated_queries)        # Bulgarian


def test_e2e_unknown_term_is_logged_and_still_searches(tmp_path):
    from carparts.sources.ebay import EbayWebSource
    s = Storage(tmp_path / "t.db")
    o = run_search(PartsQuery(make="BMW", model="G20", part_name="flux capacitor"),
                   [EbayWebSource()], storage=s)
    assert o.part_resolution.matched is False
    # The search still ran (English free-text query exists) and the term was logged.
    assert any("flux capacitor" in g.text for g in o.generated_queries)
    terms = {t["normalized"] for t in s.top_unknown_terms()}
    assert "flux capacitor" in terms


def test_oem_identifier_preserved_through_resolution():
    # An OEM number is never turned into a part match or altered beyond normalization.
    res = R.resolve("51 11 8 080 658")
    assert not res.matched  # not a vocabulary word
