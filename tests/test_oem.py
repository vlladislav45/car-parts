from carparts.models import OEMResolutionStatus, PartsQuery
from carparts.oem import OEMResolver, detect_sides, vehicle_config
from carparts.storage import Storage


def mk_storage(tmp_path):
    return Storage(tmp_path / "t.db")


def save(storage, **kw):
    row = {"make": "BMW", "part_name": "Front bumper", "oem_number": "51118080658"}
    row.update(kw)
    return storage.save_oem_mapping(row)


def test_user_provided_wins(tmp_path):
    r = OEMResolver(mk_storage(tmp_path)).resolve(
        PartsQuery(make="BMW", model="G20", part_name="Front bumper", oem_number="51 11 8 080 658"))
    assert r.status == OEMResolutionStatus.USER_PROVIDED
    assert r.oem_numbers == ["51118080658"] and r.verified and r.confident


def test_unresolved_returns_guidance(tmp_path):
    r = OEMResolver(mk_storage(tmp_path)).resolve(
        PartsQuery(make="BMW", model="G20", part_name="Front bumper"))
    assert r.status == OEMResolutionStatus.UNRESOLVED
    assert not r.resolved
    assert r.guidance_url and "realoem" in r.guidance_url
    assert r.notes


def test_verified_mapping_exact(tmp_path):
    s = mk_storage(tmp_path)
    save(s, chassis="G20", year_from=2019, year_to=2022, engine="320d",
         alt_numbers="51117464721", notes="verified on a 2021 car")
    r = OEMResolver(s).resolve(PartsQuery(make="BMW", model="3 Series G20", year=2021,
                                          engine="320d", part_name="Front bumper"))
    assert r.status == OEMResolutionStatus.VERIFIED_MAPPING
    assert r.oem_numbers == ["51118080658"]
    assert "51117464721" in r.all_numbers()
    assert r.confident


def test_mapping_not_reused_for_different_chassis(tmp_path):
    s = mk_storage(tmp_path)
    save(s, chassis="G20")
    r = OEMResolver(s).resolve(PartsQuery(make="BMW", model="3 Series E90", part_name="Front bumper"))
    assert r.status == OEMResolutionStatus.UNRESOLVED  # G20 mapping must not be used for E90


def test_mapping_not_reused_for_opposite_side(tmp_path):
    s = mk_storage(tmp_path)
    save(s, part_name="Left headlight", side="left", oem_number="63117426523")
    r = OEMResolver(s).resolve(PartsQuery(make="BMW", model="G20", part_name="Left headlight"))
    assert r.resolved  # same side: fine
    r2 = OEMResolver(s).resolve(PartsQuery(make="BMW", model="G20", part_name="Right headlight"))
    # right vs left stored under part_name "Left headlight": find_oem_mappings is by exact part_name,
    # so a different part name simply has no candidate.
    assert not r2.resolved


def test_year_mismatch_is_flagged_not_blocked(tmp_path):
    s = mk_storage(tmp_path)
    save(s, chassis="G20", year_from=2019, year_to=2022)
    r = OEMResolver(s).resolve(PartsQuery(make="BMW", model="G20", year=2024, part_name="Front bumper"))
    assert r.resolved and not r.confident
    assert any("2024" in n for n in r.notes)


def test_engine_mismatch_is_flagged(tmp_path):
    s = mk_storage(tmp_path)
    save(s, chassis="G20", engine="320d")
    r = OEMResolver(s).resolve(PartsQuery(make="BMW", model="G20", engine="330i", part_name="Front bumper"))
    assert r.resolved and not r.confident
    assert any("320d" in n for n in r.notes)


def test_vehicle_config_and_sides():
    cfg = vehicle_config(PartsQuery(make="BMW", model="3 Series G20", year=2021,
                                    engine="320d", part_name="Front left fender"))
    assert cfg["chassis"] == "G20" and cfg["year"] == "2021" and cfg["engine"] == "320d"
    assert set(cfg["side"].split()) == {"front", "left"}
    assert detect_sides("rear right door") == ["rear", "right"]
