"""A polite HTTP client.

- Sends an honest User-Agent.
- Checks robots.txt (with the * and $ wildcards that Python's robotparser lacks).
- Waits between requests to the same host.
- Caches responses in SQLite so repeated searches don't hit sites again.
- Stops on 403/429/CAPTCHA responses instead of retrying or working around them.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from .storage import Storage

DEFAULT_USER_AGENT = "CarPartsHunter/0.1 (personal local research tool)"
ROBOTS_AGENT_TOKEN = "carpartshunter"


class SourceBlocked(Exception):
    """The site refused the request (403/429/CAPTCHA). We do not retry or work around it."""


class RobotsDisallowed(Exception):
    """robots.txt disallows this URL for our user agent."""


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    from_cache: bool = False


class RobotsRules:
    """Minimal robots.txt evaluator (Google-style longest match, allow wins ties)."""

    def __init__(self, text: str, agent_token: str = ROBOTS_AGENT_TOKEN):
        groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        last_was_agent = False
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and (agents or rules):
                    groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(value.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if value:
                    rules.append((key == "allow", value))
            else:
                last_was_agent = False
        if agents or rules:
            groups.append((agents, rules))

        specific = [r for a, r in groups if any(x != "*" and x in agent_token for x in a)]
        generic = [r for a, r in groups if "*" in a]
        chosen = specific or generic
        self.rules = [rule for group in chosen for rule in group]

    @staticmethod
    def _pattern(path: str) -> re.Pattern:
        anchored = path.endswith("$")
        body = re.escape(path.rstrip("$")).replace(r"\*", ".*")
        return re.compile(body + ("$" if anchored else ""))

    def allowed(self, path_and_query: str) -> bool:
        best_len, best_allow = -1, True
        for allow, path in self.rules:
            if self._pattern(path).match(path_and_query):
                length = len(path)
                if length > best_len or (length == best_len and allow):
                    best_len, best_allow = length, allow
        return best_allow


class PoliteClient:
    def __init__(
        self,
        storage: Storage | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        default_delay: float = 2.0,
        timeout: float = 20.0,
        cache_ttl_seconds: float = 6 * 3600,
        transport: httpx.BaseTransport | None = None,
    ):
        self.storage = storage
        self.default_delay = default_delay
        self.cache_ttl = cache_ttl_seconds
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "de,en;q=0.8"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._robots: dict[str, RobotsRules | None] = {}
        self._last_request: dict[str, float] = {}
        self._host_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()

    def _host_lock(self, host: str) -> threading.Lock:
        with self._lock:
            return self._host_locks.setdefault(host, threading.Lock())

    def _wait(self, host: str, delay: float) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = delay - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request[host] = time.monotonic()

    def _robots_for(self, scheme: str, host: str, delay: float) -> RobotsRules | None:
        """None means "could not read robots.txt for a server-side reason": treat as disallowed."""
        if host in self._robots:
            return self._robots[host]
        url = f"{scheme}://{host}/robots.txt"
        cached = self.storage.cache_get(url, self.cache_ttl) if self.storage else None
        if cached:
            status, body = cached
        else:
            self._wait(host, delay)
            try:
                resp = self._client.get(url)
                status, body = resp.status_code, resp.text
            except httpx.HTTPError:
                status, body = 599, ""
            if self.storage and status < 500:
                self.storage.cache_put(url, status, body)
        if status >= 500:
            rules = None
        elif status >= 400:
            rules = RobotsRules("")  # no robots.txt: everything allowed
        else:
            rules = RobotsRules(body)
        self._robots[host] = rules
        return rules

    def get(self, url: str, delay: float | None = None, use_cache: bool = True,
            check_robots: bool = True) -> FetchResult:
        delay = self.default_delay if delay is None else delay
        parts = urlsplit(url)
        host = parts.netloc
        with self._host_lock(host):
            if use_cache and self.storage:
                cached = self.storage.cache_get(url, self.cache_ttl)
                if cached:
                    return FetchResult(url, cached[0], cached[1], from_cache=True)
            if check_robots:
                rules = self._robots_for(parts.scheme, host, delay)
                path = parts.path or "/"
                if parts.query:
                    path += "?" + parts.query
                if rules is None:
                    raise RobotsDisallowed(f"{host}: robots.txt unavailable (server error)")
                if not rules.allowed(path):
                    raise RobotsDisallowed(f"{host}: robots.txt disallows {path}")
            self._wait(host, delay)
            resp = self._client.get(url)
            text = resp.text
            if resp.status_code in (403, 429) or _looks_like_captcha(resp.status_code, text):
                raise SourceBlocked(f"{host} answered HTTP {resp.status_code} (blocked or rate limited)")
            if self.storage and use_cache and (resp.status_code == 200 or resp.status_code in (404, 410)):
                self.storage.cache_put(url, resp.status_code, text)
            return FetchResult(str(resp.url), resp.status_code, text)

    def close(self) -> None:
        self._client.close()


BLOCK_TITLE_WORDS = ("captcha", "are you a robot", "access denied", "just a moment", "attention required")


def _looks_like_captcha(status: int, text: str) -> bool:
    """Challenge pages usually say so in their <title>."""
    m = re.search(r"<title[^>]*>(.*?)</title>", text[:5000], re.I | re.S)
    title = m.group(1).lower() if m else ""
    return any(w in title for w in BLOCK_TITLE_WORDS)
