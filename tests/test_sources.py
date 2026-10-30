import json
from pathlib import Path

import httpx

from carparts.http import PoliteClient
from carparts.models import Condition, OEMResolutionStatus, PartsQuery, SourceState
from carparts.search import load_config, run_search
from carparts.sources.ebay import EbayBrowseApiSource, EbayWebSource
from carparts.sources.generic_dealer import GenericDealerSource
from carparts.storage import Storage

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


def atm_config():
    return next(s for s in load_config(ROOT / "config.yaml")["sources"] if s["name"] == "autoteile-markt.de")


def test_autoteile_markt_fixture():
    src = GenericDealerSource(atm_config(), PoliteClient())
    results = src.parse((FIXTURES / "autoteile_markt_search.html").read_text(encoding="utf-8"))
    assert len(results) == 6
    first = results[0]
    assert first.title.startswith("Stoßstange links vorne BMW 3er G20")
    assert first.url.startswith("https://www.autoteile-markt.de/shop/artikel/")
    assert (first.price, first.shipping_price, first.total_price) == (30.19, 22.49, 52.68)
    assert first.condition == Condition.USED
    assert first.oem_numbers == ["15857711", "7464273"]
    plain_link = [r for r in results if "prasco" in r.url]
    assert plain_link, "cards with a normal <a href> must parse too"
    assert all(r.price is not None for r in results)


def test_jsonld_strategy():
    cfg = {"name": "jsonld", "base_url": "https://shop.example.com", "search_url_template": "/s?q={query}",
           "extract": {"strategy": "jsonld"}}
    results = GenericDealerSource(cfg, PoliteClient()).parse((FIXTURES / "jsonld_shop.html").read_text())
    assert [r.title for r in results] == ["BMW 3er G20 Stoßstange vorne 51118080658", "Kennzeichenhalter universal"]
    a, b = results
    assert a.url == "https://shop.example.com/p/1"
    assert (a.price, a.shipping_price, a.total_price, a.condition) == (149.0, 19.9, 168.9, Condition.USED)
    assert b.price_is_minimum and b.currency == "PLN" and b.shipping_price is None


def test_generic_source_end_to_end_with_mock_site(tmp_path):
    html = (FIXTURES / "autoteile_markt_search.html").read_text(encoding="utf-8")
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /intern/\n")
        if "51118080658" in str(request.url):
            return httpx.Response(410, text="")
        return httpx.Response(200, text=html)

    storage = Storage(tmp_path / "t.db")
    client = PoliteClient(storage=storage, default_delay=0, transport=httpx.MockTransport(handler))
    cfg = dict(atm_config(), request_delay_seconds=0)
    src = GenericDealerSource(cfg, client)
    q = PartsQuery(make="BMW", model="3 Series G20", year=2021, part_name="Front bumper",
                   oem_number="51118080658", condition=Condition.USED)
    outcome = run_search(q, [src, EbayWebSource()], storage=storage)
    assert outcome.normalized_oem == "51118080658"
    assert outcome.results, "expected some relevant results"
    assert all(r.condition in (Condition.USED, Condition.UNKNOWN) for r in outcome.results)
    statuses = {s.name: s for s in outcome.statuses}
    assert not statuses["eBay (web)"].available
    assert statuses["autoteile-markt.de"].message == "OK"
    assert storage.load_search(outcome.search_id).results[0].title == outcome.results[0].title
    # Second search is served from the cache.
    n = len(seen)
    run_search(q, [GenericDealerSource(cfg, client)])
    assert len(seen) == n


def test_ebay_browse_api_adapter():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        assert request.headers["Authorization"] == "Bearer tok"
        assert request.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_DE"
        assert request.url.params["filter"] == "conditions:{USED}"
        return httpx.Response(200, json={"itemSummaries": [{
            "title": "BMW G20 Stoßstange vorne 51118080658",
            "itemWebUrl": "https://www.ebay.de/itm/1",
            "price": {"value": "120.00", "currency": "EUR"},
            "shippingOptions": [{"shippingCost": {"value": "15.00", "currency": "EUR"}}],
            "condition": "Gebraucht",
            "conditionId": "3000",
            "seller": {"username": "teilehandel"},
            "itemLocation": {"country": "DE"},
        }]})

    src = EbayBrowseApiSource("id", "secret", http=httpx.Client(transport=httpx.MockTransport(handler)))
    q = PartsQuery(make="BMW", model="G20", part_name="front bumper", oem_number="51118080658",
                   condition=Condition.USED)
    results = src.search(q)
    assert results and results[0].total_price == 135.0 and results[0].seller == "teilehandel"
    assert results[0].condition == Condition.USED
    token_calls = [c for c in calls if c.url.path.endswith("/oauth2/token")]
    assert len(token_calls) == 1  # token reused across queries


def test_ebay_api_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    src = EbayBrowseApiSource()
    assert not src.available and src.search(PartsQuery(part_name="x")) == []
    assert src.last_status.state == SourceState.AUTH_REQUIRED


def test_saved_mapping_unlocks_oem_only_source(tmp_path):
    """No OEM typed, but a verified mapping exists -> the part-number-only source runs."""
    cfg = next(s for s in load_config(ROOT / "config.yaml")["sources"] if s["name"] == "autoparts24.eu")
    html = (FIXTURES / "autoparts24_search.html").read_text(encoding="utf-8")

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text=html)

    storage = Storage(tmp_path / "t.db")
    storage.save_oem_mapping({"make": "VW", "model": "Passat B8", "chassis": "", "part_name": "Throttle body",
                              "oem_number": "06A133062A", "year_from": 2016, "year_to": 2020, "engine": ""})
    client = PoliteClient(storage=storage, default_delay=0, transport=httpx.MockTransport(handler))
    src = GenericDealerSource(dict(cfg, request_delay_seconds=0), client)

    # Without the mapping this source would be NOT_SUPPORTED (no OEM). With it, it resolves and runs.
    q = PartsQuery(make="VW", model="Passat B8", part_name="Throttle body")
    outcome = run_search(q, [src], storage=storage)
    assert outcome.oem_resolution.status == OEMResolutionStatus.VERIFIED_MAPPING
    assert outcome.oem_resolution.resolved
    assert outcome.normalized_oem == "06A133062A"
    assert {s.name: s.state for s in outcome.statuses}["autoparts24.eu"] == SourceState.SUCCESS
    assert any("06A133062A" in r.oem_numbers for r in outcome.results + outcome.hidden_results)


def test_ebay_web_reports_blocked():
    src = EbayWebSource()
    assert src.search(PartsQuery(part_name="x")) == []
    assert src.last_status.state == SourceState.BLOCKED


def test_ebay_browser_search_fallback():
    src = EbayWebSource(marketplace="EBAY_DE")
    links = src.browser_searches(PartsQuery(make="BMW", model="G20", part_name="Front bumper",
                                            oem_number="51 11 8 080 658"))
    urls = [l.url for l in links]
    assert any("_nkw=51118080658" in u for u in urls)  # OEM link
    assert any("ebay.de/sch" in u for u in urls)
    assert all(l.source == "eBay (web)" and "not retrieved" in l.note for l in links)


def test_unconfigured_api_offers_fallback_but_configured_does_not(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    q = PartsQuery(make="VW", model="Golf", part_name="headlight")
    assert EbayBrowseApiSource().browser_searches(q)  # no creds -> links offered
    assert EbayBrowseApiSource("id", "secret").browser_searches(q) == []  # configured -> API, no links


def test_run_search_collects_external_searches(tmp_path):
    storage = Storage(tmp_path / "t.db")
    outcome = run_search(PartsQuery(make="BMW", model="G20", part_name="Front bumper"),
                         [EbayWebSource()], storage=storage)
    assert outcome.external_searches
    assert all("ebay" in e.url for e in outcome.external_searches)


def test_states_distinguish_empty_from_not_applicable():
    cfg = next(s for s in load_config(ROOT / "config.yaml")["sources"] if s["name"] == "autoparts24.eu")

    # No OEM: the part-number-only source has no applicable query -> NOT_SUPPORTED, not NO_RESULTS.
    src = GenericDealerSource(cfg, PoliteClient())
    assert src.search(PartsQuery(make="BMW", model="G20", part_name="Front bumper")) == []
    assert src.last_status.state == SourceState.NOT_SUPPORTED

    # A clean run that genuinely finds nothing -> NO_RESULTS.
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(410, text="")  # autoparts24 answers "no results" with 410

    client = PoliteClient(default_delay=0, transport=httpx.MockTransport(handler))
    src2 = GenericDealerSource(dict(cfg, request_delay_seconds=0), client)
    assert src2.search(PartsQuery(make="BMW", model="G20", part_name="x", oem_number="51118080658")) == []
    assert src2.last_status.state == SourceState.NO_RESULTS


def test_blocked_site_is_not_reported_as_empty():
    cfg = atm_config()

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(403, text="<title>Access denied</title>")

    client = PoliteClient(default_delay=0, transport=httpx.MockTransport(handler))
    src = GenericDealerSource(dict(cfg, request_delay_seconds=0), client)
    assert src.search(PartsQuery(make="BMW", model="G20", part_name="Front bumper")) == []
    assert src.last_status.state == SourceState.BLOCKED


def test_bazar_bg_fixture():
    cfg = next(s for s in load_config(ROOT / "config.yaml")["sources"] if s["name"] == "bazar.bg")
    src = GenericDealerSource(cfg, PoliteClient())
    results = src.parse((FIXTURES / "bazar_bg_search.html").read_text(encoding="utf-8"))
    assert len(results) == 6
    first = results[0]
    assert first.title == "Предна броня за bmw g20 g21 M paket"
    assert first.url == "https://bazar.bg/obiava-53055595/predna-bronia-za-bmw-g20-g21-m-paket"
    assert (first.price, first.currency) == (120.0, "EUR")
    assert first.location == "гр. София, Bulgaria"
    assert first.image_url.startswith("https://cdn")  # protocol-relative "//cdn..." made absolute
    q = PartsQuery(make="BMW", model="3 Series G20", part_name="Front bumper", oem_number="51118080658")
    assert [g.language for g in src.select_queries(q)] == ["any", "any", "any", "bg", "bg"]


def test_autoparts24_fixture():
    cfg = next(s for s in load_config(ROOT / "config.yaml")["sources"] if s["name"] == "autoparts24.eu")
    src = GenericDealerSource(cfg, PoliteClient())
    results = src.parse((FIXTURES / "autoparts24_search.html").read_text(encoding="utf-8"))
    assert len(results) == 3
    first = results[0]
    assert first.title == "Drosselklappe VW"
    assert first.url.startswith("https://www.autoparts24.eu/item/D_0023_728414/")
    assert (first.price, first.currency) == (81.68, "EUR")
    assert first.oem_numbers == ["06A133062A"]  # from <li><b>Original Nummer (OEM)</b>: ...</li>
    assert first.condition == Condition.USED  # default_condition: breaker parts are used
    assert first.location == "Denmark"
    # Part number queries only: its free-text search does not understand vehicle + part name.
    q = PartsQuery(make="BMW", model="3 Series G20", part_name="Front bumper", oem_number="51118080658")
    assert [g.text for g in src.select_queries(q)] == ["51118080658"]
    assert src.select_queries(PartsQuery(make="BMW", model="3 Series G20", part_name="Front bumper")) == []


def test_breakeryard_fixture():
    cfg = next(s for s in load_config(ROOT / "config.yaml")["sources"] if s["name"] == "breakeryard.com")
    src = GenericDealerSource(cfg, PoliteClient())
    results = src.parse((FIXTURES / "breakeryard_search.html").read_text(encoding="utf-8"))
    assert len(results) == 3
    first = results[0]
    assert first.title == "BMW 3 G20 Front Bumper 51117471512 2020 23485477"
    assert first.url == "https://www.breakeryard.com/online-used-parts/bmw-3-g20-front-bumper-51117471512-2020-23485477"
    assert (first.price, first.shipping_price, first.total_price, first.currency) == (130.0, 200.0, 330.0, "GBP")
    assert first.seller == "Sparse Ltd Used"
    assert first.location == "United Kingdom"
    assert first.image_url is None  # robots.txt disallows the proxied image paths
    new = results[2]
    assert new.condition == Condition.NEW
    assert (new.price, new.shipping_price) == (81.28, 0.0)  # "+ Free UK Delivery"
    # Percent-encoded: the site redirects "+" in the query string.
    assert src.build_url("BMW G20 front bumper") == "https://www.breakeryard.com/online-car-parts?text=BMW%20G20%20front%20bumper"
    q = PartsQuery(make="BMW", model="3 Series G20", part_name="Front bumper", oem_number="51118080658")
    assert {g.language for g in src.select_queries(q)} <= {"any", "en"}
