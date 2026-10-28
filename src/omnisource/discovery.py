"""Discovery catalog generator.

The hand-edited ``catalog.json`` remains the source of truth. This module turns
it — together with the pipeline state and health document — into the
*discovery catalog* that the website and future mobile clients consume:

* ``feeds/discovery.json`` — searchable app index (published as
  ``discovery.json`` and ``api/catalog.json`` by the Pages builder).

The discovery catalog is generated on every feed build and is never edited by
hand. Added fields are additive to the AltStore feeds and carry no assumptions
about the upstream schema, so the two catalogs can diverge over time without
breaking existing clients.
"""

from __future__ import annotations

from typing import Any

from omnisource.domain import App, Catalog, today

# Canonical categories used by the website filter row. Values are the raw
# catalog ``category`` values so new categories pass through automatically.
DISCOVERY_SCHEMA_VERSION = 1


def newest_version(state: dict[str, Any], slug: str) -> dict[str, Any]:
    """Return the newest version entry for ``slug`` (empty dict when absent)."""
    versions = state.get(slug, {}).get("versions") if isinstance(state.get(slug), dict) else None
    if isinstance(versions, list) and versions and isinstance(versions[0], dict):
        return versions[0]
    return {}


def source_label(app: App) -> str:
    """Human-readable name of the upstream that published this app."""
    verification = app.raw.get("verification")
    if isinstance(verification, dict) and verification.get("publisher"):
        return str(verification["publisher"])
    upstream = app.upstream
    if upstream is not None and upstream.identity:
        return upstream.identity
    developer = app.developer
    return developer if developer else app.name


def _entry(catalog: Catalog, app: App, state: dict[str, Any], health: dict[str, Any] | None) -> dict[str, Any]:
    base = catalog.base_url.rstrip("/")
    newest = newest_version(state, app.slug)
    verification = app.raw.get("verification", {})
    if not isinstance(verification, dict):
        verification = {}
    health = health or {}

    downloads = 0
    for version in state.get(app.slug, {}).get("versions", []) if isinstance(state.get(app.slug), dict) else []:
        if isinstance(version, dict):
            downloads += int(version.get("downloads") or 0)

    return {
        # Canonical discovery keys (see docs/API.md).
        "id": app.slug,
        "slug": app.slug,
        "name": app.name,
        "developer": app.developer,
        "version": str(newest.get("version") or ""),
        "releaseDate": str(newest.get("date") or ""),
        "category": app.category,
        "categories": list(app.categories),
        "tags": list(app.tags),
        "source": source_label(app),
        # Extended metadata for the website and future clients.
        "sourceURL": app.source_url,
        "bundleId": app.bundle_id,
        "bundleIdentifier": app.bundle_id,
        "description": app.description,
        "shortDescription": app.short_description,
        "icon": app.icon,
        "iconURL": f"{base}/assets/{app.icon}",
        "pageURL": f"{base}/apps/{app.slug}/",
        "feedURL": f"{base}/feeds/{app.slug}.json",
        "homepage": app.homepage,
        "status": app.status,
        "featured": app.featured,
        "size": int(newest.get("size") or 0),
        "downloads": downloads,
        "downloadURL": str(newest.get("downloadURL") or ""),
        "sha256": newest.get("sha256"),
        "minOSVersion": app.minimum_ios_version,
        "verificationMethod": verification.get("method", ""),
        "publisher": verification.get("publisher", ""),
        "checksumPublished": bool(verification.get("checksumPublished", False)),
        "health": {
            "reachable": health.get("downloadReachable") if isinstance(health.get("downloadReachable"), bool) else None,
            "detail": health.get("detail", ""),
            "updatedAt": health.get("updatedAt", newest.get("date", "")),
        },
    }


def build_discovery_doc(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the searchable app index (``discovery.json``)."""
    health_doc = health_doc or {}
    health_by_slug = {item.get("slug"): item for item in health_doc.get("apps", []) if isinstance(item, dict)}
    apps = [_entry(catalog, app, state, health_by_slug.get(app.slug)) for app in catalog.apps]
    return {
        "schemaVersion": DISCOVERY_SCHEMA_VERSION,
        "generatedAt": today(),
        "count": len(apps),
        "baseURL": catalog.base_url.rstrip("/"),
        "apps": apps,
    }


def build_sources_doc(catalog: Catalog, state: dict[str, Any]) -> dict[str, Any]:
    """Build the source index (``sources.json``).

    Each catalog app may resolve from its own upstream, so a "source" is the
    unique upstream identity plus the apps it contributes. The document also
    carries the OmniSource feed itself and the supported clients, which is what
    an API consumer needs before installing anything.
    """
    base = catalog.base_url.rstrip("/")
    grouped: dict[str, dict[str, Any]] = {}

    for app in catalog.apps:
        verification = app.raw.get("verification", {})
        if not isinstance(verification, dict):
            verification = {}
        upstream = app.upstream
        identity = (upstream.identity if upstream is not None else None) or f"manual:{app.slug}"
        kind = upstream.provider.value if upstream is not None else "manual"
        display = source_label(app)
        entry = grouped.setdefault(
            identity,
            {
                "id": identity,
                "source": display,
                "type": kind,
                # Link of the source itself (the repo/feed that publishes the
                # sideload IPAs) - not the official page of one of its apps.
                "homepage": app.source_url or app.repository_url or app.homepage,
                "sourceURL": app.source_url or app.repository_url or app.homepage,
                "publisher": verification.get("publisher", ""),
                "apps": [],
            },
        )
        entry["apps"].append(
            {
                "slug": app.slug,
                "name": app.name,
                "version": str(newest_version(state, app.slug).get("version") or ""),
            }
        )

    sources = sorted(grouped.values(), key=lambda item: (str(item["source"]).casefold(), str(item["id"])))
    return {
        "schemaVersion": DISCOVERY_SCHEMA_VERSION,
        "generatedAt": today(),
        "count": len(sources),
        "feed": {
            "name": catalog.source.get("name", "OmniSource"),
            "identifier": catalog.source.get("identifier", "com.omnisource"),
            "baseURL": base,
            "appsURL": f"{base}/apps.json",
            "website": f"{base}/",
        },
        "clients": catalog.clients,
        "sources": sources,
    }
