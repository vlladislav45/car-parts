# Car Parts Hunter

A local tool for finding the cheapest replacement parts for repaired cars in Europe.
It runs on your machine, with no accounts, cloud services or external database.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
pytest            # optional
```

Enter the vehicle, part name and (ideally) the OEM number, then press **SEARCH PARTS**.

## What you get

- Results ranked by **match tier first, then estimated total price**, so a cheap unrelated
  part can never appear above an exact part number match. The tiers double as match-confidence
  categories:
  - **High - exact part no.**: the listing contains your OEM number (any spacing/hyphenation).
  - **Medium - vehicle+part**: the right vehicle and the full part name, with no warning signs.
  - **Low - keyword**: related, but something is off (accessory, bundle, different part number).
  - **Unrelated**: hidden behind the "Hidden results" expander.
- Item price, shipping, estimated total in EUR, and the original currency. When shipping is unknown
  the table says `Shipping: Unknown` and `€180.00 + shipping`. Totals are never invented.
- **You do not need an OEM number.** You can search by make, model/chassis, year, engine and part
  name. If you have verified an OEM number before, it is reused automatically (see OEM resolution).
- A per-source **status** so a broken or blocked integration is never mistaken for "no parts exist":
  `SUCCESS`, `NO_RESULTS`, `AUTH_REQUIRED`, `BLOCKED`, `RATE_LIMITED`, `PARSING_ERROR`, `UNAVAILABLE`,
  `NOT_SUPPORTED`, `DISABLED`. A warning appears when a source could not run a normal search.
- A debug panel with the generated queries, the normalized OEM number, each source's state, and the
  score breakdown for every result.
- Search history in SQLite (`data/carparts.db`). HTTP responses are cached for 6 hours, so
  repeating a search doesn't hit the sites again.

## Sources

| Source | Status | Notes |
|---|---|---|
| autoteile-markt.de | Working | German marketplace with many breakers and dealers. Configured in `config.yaml`. |
| bazar.bg | Working | Bulgarian classifieds, searched in Bulgarian. Only used when the country is Bulgaria, Europe or Any. Condition and shipping are rarely stated, so check the listing. |
| autoparts24.eu | Working (part numbers only) | Danish breaker network, used parts. Its search only understands part numbers, so it runs only when you enter an OEM number, and only the first results page (robots.txt disallows the rest). |
| breakeryard.com | Working | UK breakers' marketplace, prices in GBP. Searches part numbers and vehicle + part name through the site's own text search (`/online-car-parts?text=`, allowed by robots.txt; `/search/` is not). Only used when the country is UK, Europe or Any. UK parts are right-hand drive, so check drive-specific parts. Some listings are marked "Not working" (shown as unknown condition). |
| eBay (Browse API) | Working (needs keys) | Official API. Get a free Production keyset at developer.ebay.com (take the Marketplace Account Deletion exemption, "I do not persist eBay data", or the keys stay disabled), then put App ID and Cert ID in `.env` as `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET`. Until configured it offers links to eBay's own search page that you open yourself (eBay's web pages can't be scraped: robots.txt disallows `/sch/`, 403 to scripts). Verified against the live API 2026-10-15. |

Sites checked and not added (last checked 2026-10-10):
- 403 or a bot check for non-browser clients: autodoc (.de and .bg), ovoko / rrr.lt, ProxyParts, B-Parts
  (search pages), Allegro (DataDome bot check), eBay and eBay Motors (use the eBay Browse API instead),
  olx.bg, onlinecarparts, daparto, mister-auto, leebmann24, schmiedmann, ecp.de, motointegrator.
- Search disallowed by robots.txt: MEGAPARTS (megaparts.bg disallows every URL with `?`), kfzteile24,
  opisto.fr, Google and Bing web search (would need an official search API, see `carparts/sources/web_search.py`).
- Results rendered by JavaScript: autoteile24.de.
- Allegro has an official REST API (developer.allegro.pl). It is the only allowed way to search
  Allegro, but it was not added.

### Rules the HTTP client follows

`carparts/http.py` sends an honest User-Agent and checks robots.txt (including `*` and `$`
wildcards). It waits between requests to the same host (2-2.5 s). It stops a source on HTTP
403/429 or a CAPTCHA page, with no retries or workarounds. The source's status shows the reason.

## Adding a shop

Most shops can be added in `config.yaml` without code:

```yaml
  - name: my-shop.example
    type: generic_dealer
    enabled: true
    base_url: https://my-shop.example
    search_url_template: "/search?q={query}"
    query_encoding: plus          # plus | dash | percent
    currency: EUR
    countries: [PL]
    extract:
      strategy: jsonld            # if the shop embeds schema.org Product data
      # or: strategy: css, item: ".product", fields: {title: ..., url: {selector: a, attr: href}, price: ...}
```

Field specs support a CSS selector string, `{selector, attr}`, `{label: "OE:"}` (a `<dt>`/`<dd>` pair),
`decode: base64`, and a list of alternatives where the first non-empty one wins.
See the autoteile-markt.de entry for a full example. Check the shop's `robots.txt` first; the client
refuses disallowed URLs anyway.

To add a source that needs code (e.g. an API), subclass `BaseSource` in `carparts/sources/` and
implement `search_text(generated_query, query) -> list[PartResult]`. Then register it in
`carparts/sources/__init__.py`. `EbayBrowseApiSource` is the template for API-backed sources.

## OEM resolution (searching without a part number)

`carparts/oem.py` turns a vehicle + part into an OEM number, trying in order:

1. **An OEM number you typed** - used as-is.
2. **A mapping you verified earlier**, stored locally in SQLite (`oem_mappings`).
3. **A licensed catalog** - only if you wire one up (`OEMCatalog` interface). None ships with the app.
4. **Nothing found** - the search still runs on vehicle + part name, and the UI links you to the
   manufacturer's catalog (RealOEM for BMW/Mini) to look the number up by hand.

Numbers are never invented. A saved mapping is only reused when its vehicle configuration is
compatible: an opposite side (left vs right) or a different chassis/generation is never reused, while
a different engine, year or facelift is still offered but flagged with a warning. When you confirm an
OEM number that fits, save it with **Save a verified OEM mapping** - future searches reuse it, and it
makes part-number-only sources (like autoparts24.eu) usable without retyping the number.

## Parts vocabulary, autocomplete and free text

`carparts/catalog.py` is a centralized catalog of ~140 canonical parts across 10 categories
(body and exterior, lighting and electrical, engine and cooling, transmission and drivetrain,
suspension and steering, braking, interior, exhaust, wheels and tires, sensors and electronics).

- **One identity per part.** Synonyms are grouped: `headlight` and `headlamp` are the same canonical
  part `headlight`; `броня`, `bumper`, `Stoßstange` and `zderzak` all resolve to `bumper`. The catalog
  reuses the German/Bulgarian/Polish terms from `vocabulary.py` as searchable aliases, so it is not a
  second copy of the translations - it points at them.
- **Autocomplete.** The "Find a part" box above the search form suggests ranked canonical parts as you
  type, in any language, showing the Bulgarian name and category. Click one to fill the part field; you
  can still edit it. (Streamlit has no native combobox, so this is a suggestion box that fills the field
  rather than an inline dropdown.)
- **Free text always works.** You are never forced to pick a suggestion. An unknown term (e.g. a part
  the catalog does not know) is searched verbatim, your original text is preserved, and the term is
  logged to `unknown_search_terms` for later. The UI shows whether your text matched a canonical part,
  was ambiguous, or is being searched as free text (with "did you mean" hints).
- **Layered matching:** canonical id (from a picked suggestion) → exact canonical name → exact alias →
  prefix/token → fuzzy (typos) → free-text fallback. Deterministic; no LLM or external API.
- **Attributes, not more parts.** Side (left/right) and position (front/rear) are modelled as attributes
  rather than separate catalog entries, and a matched part never implies vehicle fitment on its own.

### Adding and maintaining vocabulary

- **No code (runtime):** open **Vocabulary maintenance** in the sidebar. Review frequently-seen unknown
  terms, map one to a canonical part (this saves a reusable alias), or add/remove aliases by hand. These
  live in SQLite (`user_aliases`) and extend the catalog immediately, without touching adapters.
- **In code:** add a translation to `PART_TRANSLATIONS_{DE,BG,PL}` in `vocabulary.py` (it becomes a
  searchable alias automatically), assign new English keys to a category in `CATEGORY_MEMBERS`, group
  synonyms in `SYNONYM_GROUPS`, and add colloquial/transliterated aliases or abbreviations in
  `EXTRA_ALIASES`, all in `catalog.py`. A test enforces that every translation key is assigned to exactly
  one category.

Marketplace adapters never see the catalog: `search.py` resolves the part to a canonical English name and
the existing query generator produces the per-language queries, so the vocabulary grows without editing
any scraper.

## How matching works

- `normalize_part_number` only uppercases and removes separators and a separated brand prefix:
  `51118080658`, `51 11 8 080 658`, `51-11-8-080-658` and `BMW 51118080658` are all equal.
  It never strips leading zeros or swaps letters for digits.
- Queries are generated deterministically: the OEM number, `BMW <oem>`, `BMW G20 <oem>`,
  `BMW G20 Front bumper`, `... used`, German terms (`Stoßstange vorne`, `Stoßfänger vorne`),
  Bulgarian terms (`предна броня BMW G20`), Polish terms (`zderzak przedni BMW G20`),
  `BMW G20 Ersatzteile`, `части BMW G20` and `części BMW G20`.
  Each source only runs the languages listed under `languages` in `config.yaml`, so Polish
  queries are generated and used for relevance scoring but are not dispatched until a source
  declares `languages: [..., pl]`. Translations live in `PART_TRANSLATIONS_DE`,
  `PART_TRANSLATIONS_BG` and `PART_TRANSLATIONS_PL` in `carparts/vocabulary.py`; German and
  Bulgarian cover every part name, Polish is a verified subset you can grow.
- Side: put it in the part name ("Left headlight"). Listings for the other side drop to weak matches.
- Drive: listings that explicitly say the other drive (RHD, Rechtslenker, десен волан, ...) drop to
  weak matches for drive-specific parts (headlights, dashboard, steering, wipers, heater...). For other
  parts it is only a small note. The lists are `DRIVE_PHRASES` and `DRIVE_SENSITIVE_PARTS` in `vocabulary.py`.
- Relevance rules live in `carparts/relevance.py`. Each rule adds or subtracts fixed points and records why.
- Duplicates (`carparts/dedupe.py`) are merged only on the same URL, or on a near-identical title
  plus the same price plus the same seller or part number. Different condition, seller, price or
  part number always keeps listings apart.

## Exchange rates

Static rates live in `config.yaml` (`exchange_rates`, units per 1 EUR). For live rates, write a class with
`to_eur(amount, currency)` (see `carparts/currency.py`) and pass it to `run_search`.

## Layout

```
app.py                     Streamlit UI
config.yaml                rates, HTTP settings, sources
carparts/
  models.py                PartsQuery, PartResult, ...
  part_numbers.py          normalization and extraction
  prices.py, currency.py   price parsing and conversion
  queries.py               query generation
  vocabulary.py            translations (de/bg/pl), aliases, keyword lists
  catalog.py               canonical parts, categories, autocomplete + resolution
  oem.py                   OEM resolution (user / verified mapping / catalog / guidance)
  relevance.py, dedupe.py  scoring and duplicate merging
  http.py                  polite client, robots.txt, cache
  storage.py               SQLite (searches, http cache, OEM mappings, unknown terms, user aliases)
  search.py                orchestration
  sources/                 base, generic_dealer, ebay, web_search
tests/                     pytest suite with HTML fixtures
```

## Publishing on Streamlit Community Cloud (free)

1. Push this folder to a GitHub repository (private is fine). `.gitignore` keeps `.env`,
   `.venv/` and `data/*.db` out of it.
2. Sign in at [share.streamlit.io](https://share.streamlit.io) with GitHub, click **Create app**,
   pick the repository, branch `main`, main file `app.py`, and pick a subdomain
   (`<name>.streamlit.app`).
3. Under **Advanced settings**, choose Python 3.13 and paste your secrets in the format shown in
   `.streamlit/secrets.toml.example`. Top-level secrets become environment variables, so the eBay
   keys work with no code changes.
4. Set `APP_PASSWORD` there so only people with the password can run searches. Without it (as
   when running locally) there is no login screen.

Limits of the free hosting:
- The app sleeps after a period without visitors; the first visit wakes it up.
- The disk is reset whenever the app restarts, so search history, the HTTP cache, saved OEM
  mappings, user aliases and source on/off toggles start empty and don't last. Your local
  `data/carparts.db` is not uploaded.
- Shops are more likely to report `BLOCKED` or `RATE_LIMITED` for cloud server IPs than for a home
  connection.
