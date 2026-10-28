"""Search index builder.

The website search runs entirely on the client; the only thing the build
pipeline needs to publish is a precomputed search index that the builtin
fuzzy-search engines (``js/core.js``, ``src/js/search-engine.js``,
``website/search/``) consume without any extra normalization.

The index carries the fields the user can search on:

* ``name``              — display name
* ``shortDescription``  — short blurb
* ``description``       — long description
* ``category``          — primary category
* ``tags``              — declared tags
* ``keywords``          — normalized keyword tokens (name + tags + category)
* ``developer``         — author name
* ``bundleId``          — bundle identifier
* ``verificationLevel`` — community / verified / manual / unverified
* ``clientCompatibility`` — per-app list of clients that can install the app
"""

from __future__ import annotations

import re
from typing import Any

from omnisource.discovery import newest_version
from omnisource.domain import App, Catalog, today

SEARCH_INDEX_VERSION = 2

_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _clients_for(app: App, catalog: Catalog) -> list[str]:
    """Clients that can install this app, from its compatibility block.

    Falls back to the feed-wide client list only when the app declares no
    compatibility block at all (legacy rows); an explicitly empty client
    list stays empty instead of silently claiming universal support.
    """
    compatibility = app.raw.get("compatibility")
    if isinstance(compatibility, dict) and isinstance(compatibility.get("clients"), list):
        return [str(cid) for cid in compatibility["clients"] if cid]
    return [str(client.get("id") or "") for client in catalog.clients if client.get("id")]


def _keywords_for(app: App) -> list[str]:
    """Normalized keyword tokens: name + tags + category + developer.

    Lowercased alphanumeric tokens, deduplicated, capped at 24 so the
    index stays small while fuzzy search still matches on partial words.
    """
    seen: dict[str, None] = {}
    for source in (app.name, app.developer, app.category, *app.tags, app.short_description):
        for token in _TOKEN_RE.split(str(source or "").casefold()):
            if len(token) >= 2 and token not in seen and len(seen) < 24:
                seen[token] = None
    return sorted(seen)


def build_search_index(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any] | None = None,
    verification_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    health_doc = health_doc or {}
    health_by_slug = {item.get("slug"): item for item in health_doc.get("apps", []) if isinstance(item, dict)}
    verification_by_slug = {
        item.get("app"): item for item in (verification_doc or {}).get("apps", []) if isinstance(item, dict)
    }
    docs: list[dict[str, Any]] = []
    for app in catalog.apps:
        newest = newest_version(state, app.slug)
        health = health_by_slug.get(app.slug) or {}
        verification = verification_by_slug.get(app.slug) or {}
        docs.append(
            {
                "id": app.slug,
                "slug": app.slug,
                "name": app.name,
                "subtitle": app.short_description,
                "shortDescription": app.short_description,
                "description": app.description,
                "category": app.category,
                "tags": list(app.tags),
                "keywords": _keywords_for(app),
                "developer": app.developer,
                "bundleId": app.bundle_id,
                "icon": f"assets/{app.icon}" if app.icon else "",
                "pageURL": f"apps/{app.slug}/",
                "version": str(newest.get("version") or ""),
                "verificationLevel": str(verification.get("status") or "UNVERIFIED"),
                "downloadReachable": health.get("downloadReachable")
                if isinstance(health.get("downloadReachable"), bool)
                else None,
                "clientCompatibility": _clients_for(app, catalog),
            }
        )
    return {
        "schemaVersion": SEARCH_INDEX_VERSION,
        "generatedAt": today(),
        "count": len(docs),
        "fuse": {
            "keys": [
                {"name": "name", "weight": 0.32},
                {"name": "shortDescription", "weight": 0.13},
                {"name": "description", "weight": 0.09},
                {"name": "category", "weight": 0.07},
                {"name": "tags", "weight": 0.09},
                {"name": "keywords", "weight": 0.10},
                {"name": "developer", "weight": 0.09},
                {"name": "bundleId", "weight": 0.11},
            ],
            "threshold": 0.38,
            "ignoreLocation": True,
            "minMatchCharLength": 2,
        },
        "documents": docs,
    }
