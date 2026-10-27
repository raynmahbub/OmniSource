"""OmniStore Pro API contract (``feeds/api/v2/`` -> ``api/v2/``).

Stable, versioned endpoints for OmniStore Pro clients and third-party
integrations. Every document carries ``schemaVersion`` + ``feedVersion``
so clients can sync incrementally:

* ``GET /api/v2/manifest.json`` — compare ``feedVersion`` with the cached
  one; when it matches, nothing changed and no further request is needed.
* ``documents[]`` carries a SHA-256 per endpoint for per-document
  conditional refresh (delta updates without HTTP etag support).
* ``updates.json`` carries monotonic ``sequence`` numbers: a client that
  remembers ``sequenceHigh`` only applies changes with a higher sequence.

Endpoints
---------
* ``apps.json``            full discovery catalog (existing alias, unchanged)
* ``apps/<id>.json``       one normalized app record + versions + health
* ``featured.json``        featured apps (slim records)
* ``categories.json``      categories with counts + member slugs
* ``trending.json``        trending / rising / recently updated (existing alias)
* ``updates.json``         sequenced release timeline for delta sync
* ``manifest.json``        feed version, checksums, compatibility floor

``api/v2/index.json`` stays hand-maintained (endpoint registry); everything
else is generated on every build and mirrored byte-identical to ``api/v2/``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from omnisource.app_schema import build_app_records
from omnisource.discovery import newest_version
from omnisource.domain import Catalog, today
from omnisource.io import dumps_pretty

API_V2_SCHEMA_VERSION = 2
MINIMUM_CLIENT_VERSION = "2.0.0"
FEED_VERSION_LENGTH = 12

CONTRACT_DOCUMENTS = ("manifest.json", "featured.json", "categories.json", "updates.json")


def sha256_text(payload: str) -> str:
    """Hex SHA-256 of a UTF-8 payload."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_feed_version(records: list[dict[str, Any]], state: dict[str, Any] | None = None) -> str:
    """Content hash identifying one feed generation (12 hex chars).

    Covers the fields a client installs from; display-only metadata
    (descriptions, icons) does not bump the version.
    """
    canonical = [
        {
            "id": record.get("id"),
            "version": record.get("version"),
            "versionDate": record.get("versionDate"),
            "downloadURL": record.get("downloadURL"),
            "checksum": record.get("checksum"),
            "bundleIdentifier": record.get("bundleIdentifier"),
        }
        for record in sorted(records, key=lambda item: str(item.get("id") or ""))
    ]
    if state is not None:
        for item in canonical:
            node = state.get(str(item["id"]))
            versions = node.get("versions", []) if isinstance(node, dict) else []
            item["versions"] = [
                {key: version.get(key) for key in ("version", "date", "downloadURL", "size", "sha256")}
                for version in versions
                if isinstance(version, dict)
            ]
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256_text(payload)[:FEED_VERSION_LENGTH]


def _slim(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "developer": record.get("developer"),
        "bundleIdentifier": record.get("bundleIdentifier"),
        "version": record.get("version"),
        "versionDate": record.get("versionDate"),
        "category": record.get("category"),
        "icon": record.get("icon"),
        "shortDescription": record.get("shortDescription") or record.get("subtitle") or "",
        "downloadURL": record.get("downloadURL"),
        "size": record.get("size") or 0,
        "featured": bool(record.get("featured")),
        "status": record.get("status"),
    }


def build_featured_doc(records: list[dict[str, Any]], *, feed_version: str, generated_at: str) -> dict[str, Any]:
    featured = [_slim(record) for record in records if record.get("featured")]
    featured.sort(key=lambda item: str(item.get("name") or "").casefold())
    return {
        "schemaVersion": API_V2_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "feedVersion": feed_version,
        "count": len(featured),
        "apps": featured,
    }


def build_categories_doc(
    catalog: Catalog,
    records: list[dict[str, Any]],
    *,
    feed_version: str,
    generated_at: str,
) -> dict[str, Any]:
    base = catalog.base_url.rstrip("/")
    members: dict[str, list[str]] = {}
    for record in records:
        category = str(record.get("category") or "other")
        members.setdefault(category, []).append(str(record.get("id")))
    categories = [
        {
            "id": name,
            "name": name.replace("-", " ").title() if name != "other" else "Other",
            "count": len(sorted(slugs)),
            "icon": f"{base}/assets/placeholders/category.svg",
            "apps": sorted(slugs),
        }
        for name, slugs in sorted(members.items())
    ]
    return {
        "schemaVersion": API_V2_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "feedVersion": feed_version,
        "count": len(categories),
        "categories": categories,
    }


def build_updates_doc(
    updates_doc: dict[str, Any],
    *,
    feed_version: str,
    generated_at: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Sequenced release timeline for delta sync.

    The source timeline is newest-first; sequences run oldest -> newest so a
    client can persist ``sequenceHigh`` and apply only newer changes.
    """
    raw = [item for item in updates_doc.get("updates", []) if isinstance(item, dict)][:limit]
    chronological = sorted(
        raw,
        key=lambda item: (str(item.get("date") or ""), str(item.get("slug") or "")),
    )
    sequence_of: dict[int, int] = {id(item): number for number, item in enumerate(chronological, start=1)}
    changes = [
        {
            "sequence": sequence_of[id(item)],
            "slug": item.get("slug"),
            "name": item.get("name"),
            "version": item.get("version"),
            "previousVersion": item.get("previousVersion"),
            "date": item.get("date"),
            "kind": item.get("kind"),
            "downloadURL": item.get("downloadURL"),
            "feedURL": item.get("feedURL"),
        }
        for item in raw
    ]
    return {
        "schemaVersion": API_V2_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "feedVersion": feed_version,
        "count": len(changes),
        "sequenceHigh": len(chronological),
        "sequenceLow": 1 if chronological else 0,
        "changes": changes,
    }


def build_per_app_doc(
    record: dict[str, Any],
    state: dict[str, Any],
    *,
    feed_version: str,
    generated_at: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slug = str(record.get("id") or "")
    entry = state.get(slug) if isinstance(state.get(slug), dict) else {}
    versions = [v for v in (entry.get("versions") or []) if isinstance(v, dict)]
    newest = newest_version(state, slug)
    doc: dict[str, Any] = {
        "schemaVersion": API_V2_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "feedVersion": feed_version,
        "app": record,
        "newest": {
            "version": str(newest.get("version") or ""),
            "date": str(newest.get("date") or ""),
            "downloadURL": str(newest.get("downloadURL") or ""),
            "size": int(newest.get("size") or 0),
            "sha256": newest.get("sha256"),
        },
        "versions": [
            {
                "version": str(item.get("version") or ""),
                "date": str(item.get("date") or ""),
                "downloadURL": str(item.get("downloadURL") or ""),
                "size": int(item.get("size") or 0),
                "sha256": item.get("sha256"),
            }
            for item in versions
        ],
    }
    if verification:
        doc["verification"] = {
            "status": verification.get("status"),
            "level": verification.get("level") or verification.get("status"),
            "method": verification.get("method"),
        }
    return doc


def build_manifest_doc(
    document_payloads: dict[str, str],
    *,
    feed_version: str,
    generated_at: str,
    app_count: int,
) -> dict[str, Any]:
    """Feed manifest with per-document checksums for delta sync."""
    documents = []
    for name, payload in sorted(document_payloads.items()):
        rest = name[len("api/v2/") :] if name.startswith("api/v2/") else name
        if rest == "manifest.json":
            continue
        documents.append(
            {
                "path": f"/api/v2/{rest}",
                "sha256": sha256_text(payload),
                "bytes": len(payload.encode("utf-8")),
            }
        )
    return {
        "schemaVersion": API_V2_SCHEMA_VERSION,
        "generatedAt": generated_at,
        "minimumClientVersion": MINIMUM_CLIENT_VERSION,
        "feedVersion": feed_version,
        "appCount": app_count,
        "documents": documents,
        "endpoints": [
            "/api/v2/apps.json",
            "/api/v2/apps/{id}.json",
            "/api/v2/apps/{id}/versions.json",
            "/api/v2/featured.json",
            "/api/v2/categories.json",
            "/api/v2/trending.json",
            "/api/v2/updates.json",
            "/api/v2/manifest.json",
        ],
        "compatibility": {
            "altstore": True,
            "sidestore": True,
            "feather": True,
            "esign": True,
            "livecontainer": True,
        },
    }


def build_api_v2_documents(
    catalog: Catalog,
    state: dict[str, Any],
    *,
    health_doc: dict[str, Any] | None = None,
    verification_doc: dict[str, Any] | None = None,
    updates_doc: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build every generated v2 contract document, keyed by relative path.

    Keys are relative to ``feeds/`` (``api/v2/<name>``). The manifest is
    computed over the exact bytes the publisher writes, so clients can
    verify each endpoint with the advertised SHA-256.
    """
    generated_at = today()
    records = build_app_records(catalog, state, health_doc)
    feed_version = compute_feed_version(records, state)
    verification_by_slug = {
        item.get("app"): item for item in (verification_doc or {}).get("apps", []) if isinstance(item, dict)
    }

    documents: dict[str, dict[str, Any]] = {
        "api/v2/featured.json": build_featured_doc(records, feed_version=feed_version, generated_at=generated_at),
        "api/v2/categories.json": build_categories_doc(
            catalog, records, feed_version=feed_version, generated_at=generated_at
        ),
        "api/v2/updates.json": build_updates_doc(
            updates_doc or {}, feed_version=feed_version, generated_at=generated_at
        ),
    }
    for record in records:
        slug = str(record.get("id") or "")
        per_app = build_per_app_doc(
            record,
            state,
            feed_version=feed_version,
            generated_at=generated_at,
            verification=verification_by_slug.get(slug),
        )
        documents[f"api/v2/apps/{slug}.json"] = per_app
        documents[f"api/v2/apps/{slug}/versions.json"] = {
            "schemaVersion": API_V2_SCHEMA_VERSION,
            "generatedAt": generated_at,
            "feedVersion": feed_version,
            "id": slug,
            "versions": per_app["versions"],
        }
    payloads = {name: dumps_pretty(doc) for name, doc in documents.items()}
    documents["api/v2/manifest.json"] = build_manifest_doc(
        payloads,
        feed_version=feed_version,
        generated_at=generated_at,
        app_count=len(records),
    )
    return documents
