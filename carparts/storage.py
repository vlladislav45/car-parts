"""SQLite storage: search history, result rows and a small HTTP cache.

One short-lived connection per call keeps this safe to use from worker threads.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .models import SearchOutcome

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    label TEXT NOT NULL,
    query_json TEXT NOT NULL,
    outcome_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    source TEXT, title TEXT, url TEXT,
    price REAL, currency TEXT, shipping_price REAL, total_eur REAL, sort_price_eur REAL,
    condition TEXT, part_numbers TEXT, relevance_score INTEGER, match_tier INTEGER,
    scraped_at TEXT
);
CREATE TABLE IF NOT EXISTS http_cache (
    url TEXT PRIMARY KEY,
    status INTEGER NOT NULL,
    body TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS oem_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    make TEXT NOT NULL,
    model TEXT,
    chassis TEXT,
    year_from INTEGER,
    year_to INTEGER,
    engine TEXT,
    body TEXT,
    part_name TEXT NOT NULL,
    side TEXT,
    oem_number TEXT NOT NULL,
    alt_numbers TEXT,
    source TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_oem_lookup ON oem_mappings (make, part_name);
CREATE TABLE IF NOT EXISTS unknown_search_terms (
    normalized TEXT PRIMARY KEY,
    original TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    last_seen TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS user_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    normalized TEXT NOT NULL,
    part_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (normalized, part_id)
);
"""


class Storage:
    def __init__(self, path: str | Path = "data/carparts.db"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    # HTTP cache
    def cache_get(self, url: str, max_age_seconds: float) -> tuple[int, str] | None:
        with self._connect() as con:
            row = con.execute("SELECT status, body, fetched_at FROM http_cache WHERE url = ?", (url,)).fetchone()
        if row and time.time() - row["fetched_at"] <= max_age_seconds:
            return row["status"], row["body"]
        return None

    def cache_put(self, url: str, status: int, body: str) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO http_cache (url, status, body, fetched_at) VALUES (?, ?, ?, ?)",
                (url, status, body, time.time()),
            )

    def clear_cache(self) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM http_cache")

    # Searches
    def save_search(self, outcome: SearchOutcome) -> int:
        q = outcome.query
        label = " ".join(x for x in (q.vehicle_label(), q.part_name, q.oem_number) if x)
        with self._connect() as con:
            cur = con.execute(
                "INSERT INTO searches (label, query_json, outcome_json) VALUES (?, ?, ?)",
                (label, q.model_dump_json(), outcome.model_dump_json()),
            )
            search_id = cur.lastrowid
            con.executemany(
                """INSERT INTO results (search_id, source, title, url, price, currency, shipping_price,
                   total_eur, sort_price_eur, condition, part_numbers, relevance_score, match_tier, scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (search_id, r.source, r.title, r.url, r.price, r.currency, r.shipping_price, r.total_eur,
                     r.sort_price_eur, r.condition.value, json.dumps(r.normalized_part_numbers),
                     r.relevance_score, r.match_tier, r.scraped_at.isoformat())
                    for r in outcome.results
                ],
            )
        return int(search_id)

    def recent_searches(self, limit: int = 20) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, created_at, label FROM searches ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # Verified OEM mappings
    def save_oem_mapping(self, row: dict) -> int:
        with self._connect() as con:
            cur = con.execute(
                """INSERT INTO oem_mappings
                   (make, model, chassis, year_from, year_to, engine, body, part_name, side,
                    oem_number, alt_numbers, source, notes)
                   VALUES (:make, :model, :chassis, :year_from, :year_to, :engine, :body, :part_name, :side,
                           :oem_number, :alt_numbers, :source, :notes)""",
                {k: row.get(k) for k in ("make", "model", "chassis", "year_from", "year_to", "engine",
                                         "body", "part_name", "side", "oem_number", "alt_numbers",
                                         "source", "notes")},
            )
        return int(cur.lastrowid)

    def find_oem_mappings(self, make: str, part_name: str) -> list[dict]:
        """Candidate mappings for a make + part name. Compatibility is judged by the caller."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM oem_mappings WHERE lower(make) = lower(?) AND lower(part_name) = lower(?) "
                "ORDER BY id DESC",
                (make.strip(), part_name.strip()),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_oem_mappings(self, limit: int = 200) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM oem_mappings ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def delete_oem_mapping(self, mapping_id: int) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM oem_mappings WHERE id = ?", (mapping_id,))

    # Unknown search terms (for vocabulary maintenance)
    def log_unknown_term(self, original: str, normalized: str) -> None:
        if not normalized:
            return
        with self._connect() as con:
            con.execute(
                """INSERT INTO unknown_search_terms (normalized, original, count, last_seen)
                   VALUES (?, ?, 1, datetime('now'))
                   ON CONFLICT(normalized) DO UPDATE SET
                       count = count + 1, original = excluded.original, last_seen = datetime('now')""",
                (normalized, original),
            )

    def top_unknown_terms(self, limit: int = 50) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM unknown_search_terms ORDER BY count DESC, last_seen DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_unknown_term(self, normalized: str) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM unknown_search_terms WHERE normalized = ?", (normalized,))

    # User-maintained aliases (extend the catalog without code changes)
    def add_user_alias(self, alias: str, normalized: str, part_id: str) -> bool:
        """Returns False if this (alias, part) already exists."""
        with self._connect() as con:
            cur = con.execute(
                "INSERT OR IGNORE INTO user_aliases (alias, normalized, part_id) VALUES (?, ?, ?)",
                (alias, normalized, part_id),
            )
            return cur.rowcount > 0

    def all_user_aliases(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM user_aliases ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def delete_user_alias(self, alias_id: int) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM user_aliases WHERE id = ?", (alias_id,))

    def load_search(self, search_id: int) -> SearchOutcome | None:
        with self._connect() as con:
            row = con.execute("SELECT outcome_json FROM searches WHERE id = ?", (search_id,)).fetchone()
        if not row:
            return None
        outcome = SearchOutcome.model_validate_json(row["outcome_json"])
        outcome.search_id = search_id
        return outcome
