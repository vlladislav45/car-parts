"""The source interface.

Any object with a `name` and a `search(query) -> list[PartResult]` method is a
source. `BaseSource` adds the common loop (generate queries, run each, record
status) so a concrete source only has to implement `search_text`.

A source can be backed by scraping today and by an official API tomorrow;
nothing outside the source cares how it gets its data.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..http import RobotsDisallowed, SourceBlocked
from ..models import ExternalSearch, GeneratedQuery, PartResult, PartsQuery, SourceState, SourceStatus
from ..queries import generate_queries


@runtime_checkable
class PartsSource(Protocol):
    name: str

    def search(self, query: PartsQuery) -> list[PartResult]: ...


class SourceUnavailable(Exception):
    """Raised by a source that cannot be used (blocked, disallowed, not configured).

    Carries the SourceState it should surface as, so the UI can tell apart a
    missing credential (AUTH_REQUIRED) from a rate limit (RATE_LIMITED) etc.
    """

    def __init__(self, message: str, state: SourceState = SourceState.UNAVAILABLE):
        super().__init__(message)
        self.state = state


class BaseSource:
    name: str = "base"
    countries: list[str] = ["EU"]  # ISO codes, or "EU" for Europe-wide
    languages: list[str] = ["any", "en", "de"]
    max_queries: int = 6
    available: bool = True
    unavailable_reason: str = ""
    # State to report when `available` is False (overridden by e.g. the eBay API source).
    unavailable_state: SourceState = SourceState.UNAVAILABLE
    # Message shown when the source is usable but no query applies to this search.
    not_supported_reason: str = "No query applies to this source for this search."

    def __init__(self) -> None:
        self.last_status = SourceStatus(
            name=self.name, available=self.available, message=self.unavailable_reason,
            state=None if self.available else self.unavailable_state,
        )

    def select_queries(self, query: PartsQuery) -> list[GeneratedQuery]:
        return [g for g in generate_queries(query) if g.language in self.languages][: self.max_queries]

    def search_text(self, generated: GeneratedQuery, query: PartsQuery) -> list[PartResult]:
        raise NotImplementedError

    def browser_searches(self, query: PartsQuery) -> list[ExternalSearch]:
        """Links to this source's own search page for the user to open by hand.

        Default: none. A source that cannot be queried programmatically overrides
        this to offer a fallback without scraping anything.
        """
        return []

    def search(self, query: PartsQuery) -> list[PartResult]:
        status = SourceStatus(name=self.name, available=self.available, message=self.unavailable_reason)
        self.last_status = status
        if not self.available:
            status.state = self.unavailable_state
            return []

        queries = self.select_queries(query)
        if not queries:
            # The source works, but nothing we could ask it makes sense for this search
            # (e.g. a part-number-only site with no OEM, or no query in a supported language).
            status.state = SourceState.NOT_SUPPORTED
            status.message = self.not_supported_reason
            return []

        results: list[PartResult] = []
        for g in queries:
            status.queries_run.append(g.text)
            try:
                found = self.search_text(g, query)
            except (SourceBlocked, RobotsDisallowed) as e:
                # Stop this source entirely. No retries, no workarounds.
                status.errors.append(str(e))
                status.message = f"Stopped: {e}"
                status.state = SourceState.BLOCKED
                status.result_count = len(results)
                return results
            except SourceUnavailable as e:
                status.errors.append(str(e))
                status.message = f"Stopped: {e}"
                status.state = e.state
                status.result_count = len(results)
                return results
            except Exception as e:  # one bad query should not kill the source
                status.errors.append(f"{g.text}: {type(e).__name__}: {e}")
                continue
            for r in found:
                r.query_used = g.text
            results.extend(found)

        status.result_count = len(results)
        if results:
            status.state = SourceState.SUCCESS
            status.message = "OK" if not status.errors else "Finished with errors"
        elif status.errors:
            # Ran every query, parsed nothing, and hit errors: treat as a broken parser
            # rather than a genuine empty result.
            status.state = SourceState.PARSING_ERROR
            status.message = "Finished with errors"
        else:
            status.state = SourceState.NO_RESULTS
            status.message = "No matching listings"
        return results
