"""Car Parts Hunter - Streamlit UI.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from carparts.catalog import BY_ID, CATALOG, CatalogResolver, normalize
from carparts.currency import StaticRates
from carparts.http import PoliteClient
from carparts.models import Condition, PartResult, PartsQuery, SearchOutcome, SourceState, SourceStatus
from carparts.search import COUNTRIES, load_config, run_search
from carparts.sources import build_sources
from carparts.storage import Storage

ROOT = Path(__file__).parent


def load_dotenv(path: Path) -> None:
    """Read KEY=value lines from .env into the environment; real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key, value.strip().strip("\"'"))


load_dotenv(ROOT / ".env")
TOGGLES_FILE = ROOT / "data" / "source_toggles.json"  # remembers which sources are switched off
DRIVES = {"Left-hand (EU)": "LHD", "Right-hand (UK/IE)": "RHD", "Any": "any"}
# Match-confidence categories (see README / relevance.py): High = exact part number,
# Medium = vehicle + part name match, Low = keyword only, and tier 0 is hidden.
TIER_LABELS = {3: "High · exact part no.", 2: "Medium · vehicle+part", 1: "Low · keyword", 0: "Unrelated"}

# How each diagnostic state reads in the UI, and whether it is a problem the user should notice.
STATE_INFO = {
    SourceState.SUCCESS: ("✅", "Found listings"),
    SourceState.NO_RESULTS: ("🔍", "Ran, found nothing"),
    SourceState.AUTH_REQUIRED: ("🔑", "Needs credentials"),
    SourceState.BLOCKED: ("🚫", "Blocked / not permitted"),
    SourceState.RATE_LIMITED: ("⏳", "Rate limited"),
    SourceState.PARSING_ERROR: ("⚠️", "Could not parse (page changed?)"),
    SourceState.UNAVAILABLE: ("⛔", "Unavailable"),
    SourceState.NOT_SUPPORTED: ("➖", "Not applicable to this search"),
    SourceState.DISABLED: ("🔌", "Turned off"),
}


def state_of(s: SourceStatus) -> SourceState:
    return s.state or SourceState.NO_RESULTS


def state_label(s: SourceStatus) -> str:
    icon, text = STATE_INFO.get(state_of(s), ("", state_of(s).value))
    return f"{icon} {text}"

st.set_page_config(page_title="Car Parts Hunter", layout="wide")


def require_password() -> None:
    """Stop the page until the visitor enters APP_PASSWORD; no gate when it is unset (local use)."""
    expected = os.environ.get("APP_PASSWORD", "")
    if not expected or st.session_state.get("authenticated"):
        return
    with st.form("login"):
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            if hmac.compare_digest(password.encode(), expected.encode()):
                st.session_state["authenticated"] = True
                st.rerun()
            st.error("Wrong password.")
    st.stop()


require_password()


@st.cache_resource
def get_app():
    config = load_config(ROOT / "config.yaml")
    http_cfg = config.get("http", {})
    storage = Storage(ROOT / config.get("database", "data/carparts.db"))
    client = PoliteClient(
        storage=storage,
        user_agent=http_cfg.get("user_agent", "CarPartsHunter/0.1 (personal local research tool)"),
        default_delay=float(http_cfg.get("default_delay_seconds", 2.0)),
        timeout=float(http_cfg.get("timeout_seconds", 20)),
        cache_ttl_seconds=float(http_cfg.get("cache_ttl_hours", 6)) * 3600,
    )
    sources = build_sources(config, client)
    rates = StaticRates(config.get("exchange_rates"))
    resolver = CatalogResolver(storage)
    return storage, sources, rates, resolver


def load_toggles() -> dict[str, bool]:
    try:
        return json.loads(TOGGLES_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_toggles(toggles: dict[str, bool]) -> None:
    TOGGLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOGGLES_FILE.write_text(json.dumps(toggles, indent=2))


def money(amount: float | None, currency: str) -> str:
    if amount is None:
        return "?"
    symbol = {"EUR": "€", "GBP": "£", "USD": "$"}.get(currency, "")
    return f"{symbol}{amount:,.2f}" if symbol else f"{amount:,.2f} {currency}"


def total_label(r: PartResult) -> str:
    if r.price_eur is None:
        return "Unknown"
    prefix = "from " if r.price_is_minimum else ""
    if r.total_eur is not None:
        return f"{prefix}{money(r.total_eur, 'EUR')}"
    return f"{prefix}{money(r.price_eur, 'EUR')} + shipping"


def to_table(results: list[PartResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "Link": r.url,
            "Match": TIER_LABELS[r.match_tier],
            "Title": r.title,
            "Estimated total (EUR)": total_label(r),
            "Item price": ("from " if r.price_is_minimum else "") + money(r.price, r.currency),
            "Shipping": shipping_label(r),
            "Currency": r.currency,
            "Condition": r.condition.value,
            "Part numbers": ", ".join(r.normalized_part_numbers[:4]),
            "Seller": r.seller or "",
            "Location": r.location or "",
            "Source": r.source,
            "Score": r.relevance_score,
            "Dupes": len(r.duplicates),
        })
    return pd.DataFrame(rows)


def shipping_label(r: PartResult) -> str:
    if r.shipping_price is None:
        return "Unknown"
    return "Free" if r.shipping_price == 0 else money(r.shipping_price, r.currency)


def show_table(results: list[PartResult]) -> None:
    if not results:
        st.info("No results.")
        return
    st.dataframe(
        to_table(results),
        hide_index=True,
        width="stretch",
        column_config={"Link": st.column_config.LinkColumn("Link", display_text="Open ↗", width="small")},
    )


def show_cards(results: list[PartResult], key: str, limit: int = 60) -> None:
    if not results:
        st.info("No results.")
        return
    for i, r in enumerate(results[:limit]):
        with st.container(border=True):
            img, body, side = st.columns([1, 4, 1.4])
            if r.image_url:
                img.image(r.image_url, width="stretch")
            body.markdown(f"**[{r.title}]({r.url})**")
            body.caption(" · ".join(x for x in (
                TIER_LABELS[r.match_tier], r.condition.value.capitalize(), r.seller, r.location, r.source,
            ) if x))
            if r.normalized_part_numbers:
                body.caption("Part numbers: " + ", ".join(r.normalized_part_numbers[:4]))
            side.markdown(f"### {total_label(r)}")
            side.caption(f"Item {('from ' if r.price_is_minimum else '')}{money(r.price, r.currency)}"
                         f" · Shipping {shipping_label(r)}")
            side.link_button("Open listing ↗", r.url, width="stretch", key=f"open_{key}_{i}")
    if len(results) > limit:
        st.caption(f"Showing the first {limit} of {len(results)}. Switch to Table to see all.")


def show_results(results: list[PartResult], view: str, key: str) -> None:
    if view == "Cards":
        show_cards(results, key)
    else:
        show_table(results)


def show_source_summary(statuses: list[SourceStatus]) -> None:
    """One chip per source so a failed integration is never mistaken for 'no parts exist'."""
    if not statuses:
        return
    cols = st.columns(min(len(statuses), 4))
    for i, s in enumerate(statuses):
        with cols[i % len(cols)]:
            label = state_label(s)
            caption = f"{s.result_count} found" if state_of(s).ran else (s.message or "")
            st.caption(f"**{s.name}**  \n{label}  \n{caption}")
    problems = [s for s in statuses if not state_of(s).ran and state_of(s) != SourceState.DISABLED]
    if problems:
        names = ", ".join(f"{p.name} ({state_of(p).value})" for p in problems)
        st.warning(f"Some sources did not run a normal search: {names}. "
                   f"A '0 results' from these is not evidence that the part is unavailable.")


OEM_STATUS_TEXT = {
    "user_provided": "Using the OEM number you entered.",
    "verified_mapping": "Matched a verified OEM mapping you saved earlier.",
    "catalog": "Resolved from a parts catalog.",
    "unresolved": "No OEM number - searching by vehicle and part name only.",
}


def show_oem_resolution(outcome: SearchOutcome) -> None:
    res = outcome.oem_resolution
    if res is None:
        return
    text = OEM_STATUS_TEXT.get(res.status.value, res.status.value)
    if res.resolved:
        number = res.primary
        alts = ", ".join(n for n in res.all_numbers()[1:])
        line = f"**OEM {number}** - {text}" + (f"  (alternatives: {alts})" if alts else "")
        (st.info if res.confident else st.warning)(line)
        for note in res.notes:
            st.caption("⚠️ " + note if not res.confident else "• " + note)
    else:
        st.info(text)
        for note in res.notes:
            st.caption("• " + note)
        if res.guidance_url:
            st.link_button("Open parts catalog to look it up ↗", res.guidance_url)


def show_save_mapping(outcome: SearchOutcome) -> None:
    """Let the user save an OEM they have verified, so future searches reuse it."""
    q = outcome.query
    res = outcome.oem_resolution
    already_saved = bool(res and res.status.value == "verified_mapping")
    with st.expander("Save a verified OEM mapping" + (" (already matched)" if already_saved else "")):
        st.caption("Save an OEM number you have confirmed fits this exact vehicle. It will be reused "
                   "automatically next time, and lets part-number-only sources work. Only save numbers "
                   "you have verified - a wrong mapping is worse than none.")
        with st.form("save_mapping"):
            c1, c2, c3 = st.columns(3)
            m_make = c1.text_input("Make", q.make, key="m_make")
            m_model = c2.text_input("Model / chassis", q.model, key="m_model")
            m_engine = c3.text_input("Engine (optional)", q.engine, key="m_engine")
            c4, c5, c6 = st.columns(3)
            m_part = c4.text_input("Part name", q.part_name, key="m_part")
            m_oem = c5.text_input("OEM number", outcome.normalized_oem or "", key="m_oem")
            m_year = c6.number_input("Verified for year", min_value=1950, max_value=2035,
                                     value=int(q.year) if q.year else 2021, step=1, key="m_year")
            c7, c8 = st.columns(2)
            m_alts = c7.text_input("Alternative / superseded numbers (comma separated)", key="m_alts")
            m_notes = c8.text_input("Notes (optional)", key="m_notes")
            if st.form_submit_button("Save mapping"):
                if not (m_make.strip() and m_part.strip() and m_oem.strip()):
                    st.error("Make, part name and OEM number are required.")
                else:
                    from carparts.oem import detect_sides
                    from carparts.vocabulary import chassis_codes
                    codes = chassis_codes(m_model)
                    storage.save_oem_mapping({
                        "make": m_make.strip(), "model": m_model.strip(),
                        "chassis": codes[0] if codes else "",
                        "year_from": int(m_year), "year_to": int(m_year),
                        "engine": m_engine.strip(), "body": "",
                        "part_name": m_part.strip(), "side": " ".join(detect_sides(m_part)),
                        "oem_number": m_oem.strip(), "alt_numbers": m_alts.strip(),
                        "source": "manual", "notes": m_notes.strip(),
                    })
                    st.success(f"Saved OEM {m_oem.strip()} for {m_make} {m_model}. Re-run the search to use it.")


def show_external_searches(outcome: SearchOutcome) -> None:
    if not outcome.external_searches:
        return
    with st.expander(f"Search these sites yourself ({len(outcome.external_searches)} links)"):
        st.caption("These sites can't be queried automatically (e.g. eBay without an API key). "
                   "Open the search in your browser. Nothing below was retrieved or checked by this app.")
        for link in outcome.external_searches:
            st.link_button(link.label + " ↗", link.url)
            if link.note:
                st.caption(link.note)


def show_outcome(outcome: SearchOutcome) -> None:
    results = outcome.results
    exact = sum(r.match_tier == 3 for r in results)
    st.subheader(f"{len(results)} results ({exact} exact part number matches)")
    show_part_resolution(outcome)
    show_oem_resolution(outcome)
    show_source_summary(outcome.statuses)
    show_external_searches(outcome)
    show_save_mapping(outcome)
    if results:
        best = results[0]
        st.success(f"Best: **[{best.title}]({best.url})** | {total_label(best)} | {best.source}")
    st.caption("Sorted by match quality first, then estimated total. Shipping is the seller's default "
               "(usually within Germany); check the listing for shipping to your country.")
    view = st.segmented_control("View", ["Cards", "Table"], default="Cards", key="view") or "Cards"
    show_results(results, view, "r")

    with st.expander(f"Hidden results ({len(outcome.hidden_results)}): wrong condition or likely unrelated"):
        show_results(outcome.hidden_results, view, "h")

    with st.expander("Debug"):
        st.write(f"Normalized OEM number: `{outcome.normalized_oem or '(none)'}`")
        st.write("Generated queries:")
        st.table(pd.DataFrame([g.model_dump() for g in outcome.generated_queries]))
        st.write("Sources:")
        st.table(pd.DataFrame([{
            "Source": s.name, "State": state_of(s).value, "Status": s.message,
            "Queries run": len(s.queries_run), "Results": s.result_count, "Errors": "; ".join(s.errors)[:300],
        } for s in outcome.statuses]))
        st.write("Relevance reasons (shown results):")
        for r in results[:50]:
            st.text(f"[{r.relevance_score:+d}] {r.title[:90]}\n    " + " | ".join(r.relevance_reasons)
                    + (f"\n    duplicates: {', '.join(r.duplicates)}" if r.duplicates else ""))


def show_part_resolution(outcome: SearchOutcome) -> None:
    pr = outcome.part_resolution
    if pr is None:
        return
    if pr.matched:
        bg = f" ({pr.display_bg})" if pr.display_bg else ""
        attrs = ", ".join(f"{k}: {v}" for k, v in pr.attributes.items())
        st.caption(f"🧩 Matched part: **{pr.canonical_en}**{bg} · {pr.category}"
                   + (f" · {attrs}" if attrs else "") + f" · via {pr.match_type}")
    elif pr.ambiguous:
        names = ", ".join(BY_ID[c].en for c in pr.candidate_ids if c in BY_ID)
        st.warning(f"“{pr.original_text}” could mean: {names}. Searched your exact text - "
                   f"pick a specific part (use Find a part) for sharper results.")
    elif pr.original_text:
        line = f"🧩 “{pr.original_text}” isn’t in the catalog - searching by your exact words."
        sugg = [BY_ID[s].en for s in pr.suggestion_ids if s in BY_ID]
        if sugg:
            line += "  Did you mean: " + ", ".join(sugg[:5]) + "?"
        st.caption(line)


def part_finder_ui() -> None:
    """Autocomplete above the search form. Fills the part field; never forces a choice."""
    st.session_state.setdefault("part_name_input", "Front bumper")
    st.session_state.setdefault("selected_part_id", "")
    st.session_state.setdefault("selected_part_text", "")
    finder = st.text_input("🔎 Find a part", key="part_finder",
                           placeholder="Type any language: броня, bumper, Stoßstange, фар, radiator…",
                           help="Optional. Click a suggestion to fill the part field below, "
                                "or just type freely into the part field.")
    if finder and len(finder.strip()) >= 2:
        suggestions = resolver.suggest(finder, limit=8)
        if suggestions:
            st.caption("Suggestions (click to use; you can still edit afterwards):")
            cols = st.columns(2)
            for i, p in enumerate(suggestions):
                bg = f" · {p.name_bg}" if p.name_bg else ""
                if cols[i % 2].button(f"{p.en}{bg}  —  {p.category_name}", key=f"sugg_{p.id}",
                                      width="stretch"):
                    st.session_state["part_name_input"] = p.en
                    st.session_state["selected_part_id"] = p.id
                    st.session_state["selected_part_text"] = p.en
                    st.rerun()
        else:
            st.caption("No catalog match - type it into the part field and search anyway.")


def vocabulary_maintenance_ui() -> None:
    labels = {f"{p.en} · {p.category_name}": p.id
              for p in sorted(CATALOG, key=lambda p: (p.category_name, p.en))}
    with st.sidebar.expander("Vocabulary maintenance"):
        st.caption("Unknown search terms - map one to a part to teach the catalog.")
        unknown = storage.top_unknown_terms(20)
        if not unknown:
            st.caption("No unknown terms logged yet.")
        for t in unknown:
            st.markdown(f"**{t['original']}** · seen {t['count']}×")
            choice = st.selectbox("Map to part", ["(choose)"] + list(labels),
                                  key=f"map_{t['normalized']}", label_visibility="collapsed")
            cc = st.columns(2)
            if cc[0].button("Map", key=f"mapbtn_{t['normalized']}"):
                if choice != "(choose)":
                    storage.add_user_alias(t["original"], t["normalized"], labels[choice])
                    storage.delete_unknown_term(t["normalized"])
                    st.rerun()
            if cc[1].button("Dismiss", key=f"dis_{t['normalized']}"):
                storage.delete_unknown_term(t["normalized"])
                st.rerun()
        st.divider()
        st.caption("Add an alias manually:")
        alias = st.text_input("Alias", key="newalias")
        part_label = st.selectbox("Part", list(labels), key="newaliaspart")
        if st.button("Add alias") and alias.strip():
            ok = storage.add_user_alias(alias.strip(), normalize(alias), labels[part_label])
            st.toast("Alias added" if ok else "That alias already exists")
            st.rerun()
        user_aliases = storage.all_user_aliases()
        if user_aliases:
            st.caption("Your aliases (click to remove):")
            for row in user_aliases[:30]:
                name = BY_ID[row["part_id"]].en if row["part_id"] in BY_ID else row["part_id"]
                if st.button(f"✖ {row['alias']} → {name}", key=f"ua_{row['id']}"):
                    storage.delete_user_alias(row["id"])
                    st.rerun()


storage, sources, rates, resolver = get_app()

st.title("Car Parts Hunter")

part_finder_ui()

with st.form("search"):
    c1, c2, c3, c4 = st.columns(4)
    make = c1.text_input("Make", "BMW")
    model = c2.text_input("Model", "3 Series G20")
    year = c3.number_input("Year", min_value=1950, max_value=2035, value=2021, step=1)
    engine = c4.text_input("Engine (optional)", "320d")
    c5, c6, c7, c8, c9 = st.columns([1.2, 1.2, 1, 0.8, 1])
    part_name = c5.text_input("Part name", key="part_name_input",
                              help="Any language and free text work. Include the side if it matters, "
                                   "e.g. 'Left headlight'. Use Find a part above for suggestions.")
    oem = c6.text_input("OEM / part number (optional)", "51118080658")
    country = c7.selectbox("Country preference", list(COUNTRIES), index=list(COUNTRIES).index("Europe"))
    condition = c8.selectbox("Condition", ["Any", "Used", "New", "Refurbished"], index=1)
    drive = c9.selectbox("Drive", list(DRIVES), index=0,
                         help="Headlights, dashboards, steering, wipers and heater parts often differ "
                              "between left- and right-hand drive cars.")
    submitted = st.form_submit_button("SEARCH PARTS", type="primary")

with st.sidebar:
    st.header("Sources")
    saved = load_toggles()
    enabled: dict[str, bool] = {}
    for s in sources:
        ok = getattr(s, "available", True)
        enabled[s.name] = st.toggle(s.name, value=ok and saved.get(s.name, True), disabled=not ok,
                                    key=f"src_{s.name}")
        if not ok:
            st.caption(getattr(s, "unavailable_reason", ""))
    current = {s.name: enabled[s.name] for s in sources if getattr(s, "available", True)}
    if any(saved.get(name, True) != on for name, on in current.items()):
        save_toggles(current)
    if not any(enabled.values()):
        st.warning("All sources are off.")
    st.header("History")
    for h in storage.recent_searches(15):
        if st.button(f"{h['created_at'][5:16]}  {h['label']}", key=f"h{h['id']}"):
            st.session_state["outcome"] = storage.load_search(h["id"])
    if st.button("Clear HTTP cache"):
        storage.clear_cache()
        st.toast("Cache cleared")

vocabulary_maintenance_ui()

if submitted:
    if not (part_name.strip() or oem.strip()):
        st.error("Enter a part name or a part number.")
    else:
        # Pass the chosen catalog id only if the field still holds the picked part text,
        # so editing the field afterwards falls back to resolving the typed text.
        picked_id = ""
        if st.session_state.get("selected_part_text", "").strip() == part_name.strip():
            picked_id = st.session_state.get("selected_part_id", "")
        query = PartsQuery(
            make=make, model=model, year=int(year) if year else None, engine=engine,
            part_name=part_name, part_id=picked_id, oem_number=oem, country=country,
            condition=Condition(condition.lower()), drive=DRIVES[drive],
        )
        with st.spinner("Searching (polite delays between requests, this can take a little while)..."):
            outcome = run_search(query, [s for s in sources if enabled[s.name]], rates, storage)
            outcome.statuses += [
                SourceStatus(
                    name=s.name, available=getattr(s, "available", True),
                    state=SourceState.DISABLED if getattr(s, "available", True)
                    else getattr(s, "unavailable_state", SourceState.UNAVAILABLE),
                    message="Turned off" if getattr(s, "available", True)
                    else getattr(s, "unavailable_reason", "") or "Unavailable",
                )
                for s in sources if not enabled[s.name]
            ]
            st.session_state["outcome"] = outcome

if st.session_state.get("outcome"):
    show_outcome(st.session_state["outcome"])
