"""Normalized app records (``schemas/app.schema.json``).

The AltStore distribution feeds are shaped for sideloading clients; the
website and OmniStore Pro clients need a smaller, stable contract. This
module builds that contract — one normalized record per app — from the
same catalog + pipeline state the feeds are rendered from, and validates
it:

* no duplicate ids
* no duplicate bundle identifiers (unless the catalog declares the
  ``alternativeTo`` group, e.g. the YouTube tweaks)
* no empty icons (missing icons resolve to the placeholder asset)
* no broken URLs (every URL must be absolute HTTP(S))
* no invalid versions (non-empty, contains a digit, no whitespace)
* no missing metadata (name / developer / description / downloadURL)

The pipeline calls :func:`validate_app_records` on every build and fails
when a record violates the schema, so a bad upstream can never publish a
half-empty app to clients.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from omnisource.constants import INSTALLABLE_SUFFIXES
from omnisource.discovery import newest_version, source_label
from omnisource.domain import App, Catalog
from omnisource.http import is_http_url
from omnisource.validation import DATE_RE, Report

APP_SCHEMA_VERSION = 1

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
BUNDLE_RE = re.compile(r"^[A-Za-z0-9.-]+$")
VERSION_RE = re.compile(r"^(?=.*\d)\S+$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")

REQUIRED_RECORD_FIELDS = (
    "id",
    "name",
    "bundleIdentifier",
    "version",
    "versionDate",
    "description",
    "category",
    "icon",
    "screenshots",
    "downloadURL",
    "source",
    "checksum",
)


def schema_path() -> Path:
    """Filesystem location of the JSON Schema document for app records."""
    return Path(__file__).resolve().parents[2] / "schemas" / "app.schema.json"


def load_schema() -> dict[str, Any]:
    """Parse ``schemas/app.schema.json`` (raises when it is unreadable)."""
    raw = json.loads(schema_path().read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("schemas/app.schema.json must be a JSON object")
    return raw


def placeholder_icon_url(base_url: str) -> str:
    """Absolute URL of the fallback app icon served from this repository."""
    return f"{base_url.rstrip('/')}/assets/placeholders/app.svg"


def _icon_url(catalog: Catalog, app: App) -> str:
    base = catalog.base_url.rstrip("/")
    if app.icon:
        return f"{base}/assets/{app.icon}"
    return placeholder_icon_url(base)


def _screenshots(app: App, base_url: str) -> list[str]:
    out: list[str] = []
    for shot in app.raw.get("screenshots") or []:
        if isinstance(shot, str) and shot.strip():
            url = shot.strip()
            out.append(url if is_http_url(url) else f"{base_url.rstrip('/')}/{url.lstrip('/')}")
    return out


def build_record(
    catalog: Catalog,
    app: App,
    state: dict[str, Any],
    health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the normalized record for one catalog app.

    ``state`` is the pipeline state (``state[slug][\"versions\"]`` carries the
    synced releases). Apps without a synced version still produce a record so
    validation can report them instead of silently dropping them; their
    version fields stay empty and fail the metadata rules.
    """
    base = catalog.base_url.rstrip("/")
    newest = newest_version(state, app.slug)
    description = str(app.description or app.short_description or app.name or "").strip()
    sha = newest.get("sha256")
    sha_value = str(sha).strip() if isinstance(sha, str) and sha.strip() else None
    verification = app.raw.get("verification")
    checksum_published = bool(isinstance(verification, dict) and verification.get("checksumPublished"))
    record: dict[str, Any] = {
        "id": app.slug,
        "name": app.name,
        "developer": app.developer,
        "subtitle": app.short_description,
        "bundleIdentifier": app.bundle_id,
        "version": str(newest.get("version") or ""),
        "versionDate": str(newest.get("date") or ""),
        "description": description,
        "shortDescription": app.short_description,
        "category": app.category or "other",
        "tags": list(app.tags),
        "icon": _icon_url(catalog, app),
        "screenshots": _screenshots(app, base),
        "downloadURL": str(newest.get("downloadURL") or ""),
        "size": int(newest.get("size") or 0),
        "source": source_label(app),
        "sourceURL": str(app.raw.get("upstreamURL") or ""),
        "checksum": sha_value,
        "checksumPublished": checksum_published,
        "minOSVersion": str(app.raw.get("compatibility", {}).get("minOSVersion") or "16.0")
        if isinstance(app.raw.get("compatibility"), dict)
        else "16.0",
        "status": str(app.raw.get("status") or "stable"),
        "featured": bool(app.raw.get("featured")),
        "pageURL": f"{base}/apps/{app.slug}/",
        "feedURL": f"{base}/feeds/{app.slug}.json",
    }
    if health:
        record["health"] = {
            "reachable": health.get("downloadReachable") if isinstance(health.get("downloadReachable"), bool) else None,
            "detail": str(health.get("detail") or ""),
            "updatedAt": str(health.get("updatedAt") or ""),
        }
    return record


def build_app_records(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build normalized records for every catalog app, sorted by id."""
    health_by_slug = {item.get("slug"): item for item in (health_doc or {}).get("apps", []) if isinstance(item, dict)}
    records = [build_record(catalog, app, state, health_by_slug.get(app.slug)) for app in catalog.apps]
    records.sort(key=lambda item: str(item.get("id") or ""))
    return records


def record_from_feed_entry(entry: dict[str, Any], *, slug: str = "") -> dict[str, Any]:
    """Map one AltStore feed app entry onto the normalized record shape.

    Used by the validator so the *published* feeds — not just the in-memory
    pipeline state — are checked against the client contract.
    """
    extension = entry.get("omnisource") if isinstance(entry.get("omnisource"), dict) else {}
    verification = extension.get("verification") if isinstance(extension, dict) else {}
    versions = entry.get("versions") if isinstance(entry.get("versions"), list) else []
    newest = versions[0] if versions and isinstance(versions[0], dict) else {}
    return {
        "id": slug or str(extension.get("slug") or ""),
        "name": str(entry.get("name") or ""),
        "developer": str(entry.get("developerName") or ""),
        "subtitle": str(entry.get("subtitle") or ""),
        "bundleIdentifier": str(entry.get("bundleIdentifier") or ""),
        "version": str(entry.get("version") or ""),
        "versionDate": str(entry.get("versionDate") or ""),
        "description": str(entry.get("localizedDescription") or entry.get("versionDescription") or ""),
        "shortDescription": str(entry.get("subtitle") or ""),
        "category": str(entry.get("category") or "other"),
        "tags": [],
        "icon": str(entry.get("iconURL") or ""),
        "screenshots": list(entry.get("screenshotURLs") or []),
        "downloadURL": str(entry.get("downloadURL") or ""),
        "size": entry.get("size") or 0,
        "source": str(extension.get("upstreamURL") or verification.get("publisher") or ""),
        "sourceURL": str(extension.get("upstreamURL") or ""),
        "checksum": newest.get("sha256"),
        "checksumPublished": bool(verification.get("checksumPublished")) if isinstance(verification, dict) else False,
        "minOSVersion": str((extension.get("compatibility") or {}).get("minOSVersion") or "16.0")
        if isinstance(extension.get("compatibility"), dict)
        else "16.0",
        "status": str(extension.get("status") or "stable"),
        "featured": False,
        "pageURL": "",
        "feedURL": "",
    }


def declared_bundle_groups(catalog: Catalog | dict[str, Any] | None) -> dict[str, set[str]]:
    """Bundle id -> catalog slugs that declared themselves alternatives.

    Mirrors the ``alternativeTo`` rule in :mod:`omnisource.validation`: every
    member of a shared-bundle group must point at another member.
    """
    apps: list[Any] = []
    if isinstance(catalog, Catalog):
        apps = list(catalog.apps)
    elif isinstance(catalog, dict):
        apps = [item for item in catalog.get("apps", []) if isinstance(item, dict)]
    by_bundle: dict[str, list[tuple[str, str]]] = {}
    for app in apps:
        if isinstance(app, App):
            slug, bundle, alt = app.slug, app.bundle_id, str(app.raw.get("alternativeTo") or "")
        else:
            slug = str(app.get("slug") or "")
            bundle = str(app.get("bundleIdentifier") or "")
            alt = str(app.get("alternativeTo") or "")
        if slug and bundle:
            by_bundle.setdefault(bundle, []).append((slug, alt))
    groups: dict[str, set[str]] = {}
    for bundle, members in by_bundle.items():
        if len(members) < 2:
            continue
        slugs = {slug for slug, _ in members}
        if all(alt in slugs - {slug} for slug, alt in members if slug):
            groups[bundle] = slugs
    return groups


def validate_app_records(
    records: list[dict[str, Any]],
    catalog: Catalog | dict[str, Any] | None = None,
    *,
    prefix: str = "app",
) -> Report:
    """Validate normalized records against the client contract."""
    report = Report()
    if not isinstance(records, list):
        report.error(f"{prefix}: records must be a list")
        return report
    groups = declared_bundle_groups(catalog)
    seen_ids: set[str] = set()
    bundle_users: dict[str, list[str]] = {}
    for record in records:
        if isinstance(record, dict):
            bundle = str(record.get("bundleIdentifier") or "")
            app_id = str(record.get("id") or "")
            if bundle and BUNDLE_RE.match(bundle) and app_id:
                bundle_users.setdefault(bundle, []).append(app_id)
    for bundle, users in sorted(bundle_users.items()):
        if len(users) < 2:
            continue
        members = groups.get(bundle, set())
        for app_id in users:
            if app_id not in members:
                others = ", ".join(sorted(set(users) - {app_id}))
                report.error(
                    f"{prefix}:{app_id}: duplicate bundleIdentifier '{bundle}' "
                    f"(also used by {others}; declare 'alternativeTo' to share one)"
                )
    for index, record in enumerate(records):
        label = f"{prefix}[{index}]"
        if not isinstance(record, dict):
            report.error(f"{label} must be an object")
            continue
        label = f"{prefix}:{record.get('id', index)}"
        for field in REQUIRED_RECORD_FIELDS:
            if field not in record:
                report.error(f"{label} is missing required field '{field}'")

        app_id = str(record.get("id") or "")
        if not app_id:
            report.error(f"{label} has an empty id")
        elif not ID_RE.match(app_id):
            report.error(f"{label}: id must be lowercase kebab-case (2-32 chars)")
        elif app_id in seen_ids:
            report.error(f"{label}: duplicate id '{app_id}'")
        seen_ids.add(app_id)

        bundle = str(record.get("bundleIdentifier") or "")
        if not bundle:
            report.error(f"{label} has an empty bundleIdentifier")
        elif not BUNDLE_RE.match(bundle):
            report.error(f"{label}: bundleIdentifier contains invalid characters")

        if not str(record.get("name") or "").strip():
            report.error(f"{label} has an empty name")
        if not str(record.get("developer") or "").strip():
            report.error(f"{label} has an empty developer")
        if not str(record.get("description") or "").strip():
            report.warn(f"{label} has an empty description - clients will show a blank app page")

        version = str(record.get("version") or "")
        if not version:
            report.error(f"{label} has an empty version")
        elif not VERSION_RE.match(version):
            report.error(f"{label}: invalid version '{version}' (must contain a digit, no whitespace)")

        version_date = str(record.get("versionDate") or "")
        if not version_date:
            report.error(f"{label} has an empty versionDate")
        elif not DATE_RE.match(version_date):
            report.error(f"{label}: versionDate must be an ISO date (YYYY-MM-DD)")

        if not str(record.get("category") or "").strip():
            report.error(f"{label} has an empty category")

        icon = str(record.get("icon") or "")
        if not icon:
            report.error(f"{label} has an empty icon")
        elif not is_http_url(icon):
            report.error(f"{label}: icon must be an absolute HTTP(S) URL")

        screenshots = record.get("screenshots")
        if not isinstance(screenshots, list):
            report.error(f"{label}: screenshots must be an array")
        else:
            for shot in screenshots:
                if not isinstance(shot, str) or not is_http_url(shot):
                    report.error(f"{label}: screenshot URL must be an absolute HTTP(S) URL")
                    break

        download_url = str(record.get("downloadURL") or "")
        if not download_url:
            report.error(f"{label} has an empty downloadURL")
        elif not is_http_url(download_url):
            report.error(f"{label}: downloadURL must be an absolute HTTP(S) URL")
        elif not download_url.split("?", 1)[0].lower().endswith(INSTALLABLE_SUFFIXES):
            report.warn(f"{label}: downloadURL does not end in an installable suffix {INSTALLABLE_SUFFIXES}")

        if not str(record.get("source") or "").strip():
            report.error(f"{label} has an empty source")
        source_url = str(record.get("sourceURL") or "")
        if source_url and not is_http_url(source_url):
            report.error(f"{label}: sourceURL must be an absolute HTTP(S) URL")

        checksum = record.get("checksum")
        if checksum is not None and (not isinstance(checksum, str) or not SHA_RE.match(checksum)):
            report.error(f"{label}: checksum must be null or a 64-char hex digest")
    return report
