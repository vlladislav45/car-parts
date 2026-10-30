"""Source registry: builds source objects from config.yaml."""

from __future__ import annotations

import os
from typing import Any

from ..http import PoliteClient
from .base import BaseSource, PartsSource, SourceUnavailable
from .ebay import EbayBrowseApiSource, EbayWebSource
from .generic_dealer import GenericDealerSource
from .web_search import WebSearchSource

__all__ = ["BaseSource", "PartsSource", "SourceUnavailable", "build_sources"]


def build_sources(config: dict[str, Any], client: PoliteClient) -> list[PartsSource]:
    sources: list[PartsSource] = []
    for entry in config.get("sources", []):
        if not entry.get("enabled", True):
            continue
        kind = entry.get("type", "generic_dealer")
        if kind == "generic_dealer":
            sources.append(GenericDealerSource(entry, client))
        elif kind == "ebay_web":
            sources.append(EbayWebSource(marketplace=entry.get("marketplace", "EBAY_DE")))
        elif kind == "ebay_api":
            sources.append(EbayBrowseApiSource(
                client_id=os.environ.get("EBAY_CLIENT_ID"),
                client_secret=os.environ.get("EBAY_CLIENT_SECRET"),
                marketplace=entry.get("marketplace", "EBAY_DE"),
            ))
        elif kind == "web_search":
            sources.append(WebSearchSource())
        else:
            raise ValueError(f"Unknown source type: {kind}")
    return sources
