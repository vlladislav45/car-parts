import pytest

from carparts.part_numbers import extract_part_numbers, normalize_part_number, part_numbers_match


@pytest.mark.parametrize("raw", [
    "51118080658", "51 11 8 080 658", "51-11-8-080-658", "BMW 51118080658", "bmw 51.11.8.080.658", " 51118080658 ",
])
def test_bmw_variants_normalize_identically(raw):
    assert normalize_part_number(raw) == "51118080658"


def test_no_aggressive_changes():
    assert normalize_part_number("0594592") == "0594592"  # leading zero kept
    assert normalize_part_number("8W0-807-065-A") == "8W0807065A"
    assert normalize_part_number("O594592") != normalize_part_number("0594592")  # no O->0
    assert normalize_part_number("VW123456") == "VW123456"  # glued prefix is part of the number


def test_empty():
    assert normalize_part_number(None) == ""
    assert normalize_part_number("  ") == ""
    assert not part_numbers_match("", "")


def test_extract_from_text():
    text = "Stoßstange vorne 51 11 8 080 658 G20 2021 M-Paket"
    assert "51118080658" in extract_part_numbers(text)
    assert "2021" not in extract_part_numbers(text)
    assert extract_part_numbers("Teil 8W0-807-065-A neu") == ["8W0807065A"]


def test_year_ranges_are_not_part_numbers():
    assert extract_part_numbers("Предна броня BMW G20 (2018-2023)") == []
    assert extract_part_numbers("BMW G20 M Sport. 2019-2026. 5") == []
    assert extract_part_numbers("Baujahr 2019/2023") == []
