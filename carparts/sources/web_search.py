"""Search engine source (Google/Bing/DuckDuckGo results -> dealer pages).

Unavailable in v1. Google and Bing robots.txt disallow /search, DuckDuckGo
disallows /html and /lite, and the HTML endpoints answer 403 or a CAPTCHA to
scripted clients. Scraping them would mean working around those protections.

To enable it later, implement `search_text` with an official search API
(e.g. Brave Search API or Google Programmable Search JSON API), turn each hit
into a PartResult with price=None, and optionally follow allowed dealer pages
with GenericDealerSource's JSON-LD parser.
"""

from __future__ import annotations

from ..models import SourceState
from .base import BaseSource


class WebSearchSource(BaseSource):
    name = "Web search (Google/Bing)"
    available = False
    unavailable_state = SourceState.BLOCKED
    unavailable_reason = (
        "Unavailable: Google/Bing/DuckDuckGo disallow automated search result access (robots.txt) "
        "and block scripted clients. Plug in an official search API to enable."
    )
