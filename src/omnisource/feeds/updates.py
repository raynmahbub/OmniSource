"""Website updates timeline document (``feeds/updates.json``).

A sanitized, publishable view of ``state.json`` update history plus each app's
newest known version. The static website reads it to render the "Latest
updates" timeline without ever exposing pipeline state.

The document is deterministic (``generatedAt`` mirrors the newest entry date,
matching ``health.json`` semantics) so a rebuild from committed state is a
byte-for-byte no-op.
"""

from __future__ import annotations

from typing import Any

from omnisource.domain import Catalog


def _event_dict(
    *,
    app: Any,
    base: str,
    version: str,
    date_str: str,
    kind: str,
    changelog: str,
    download_url: str,
    previous_version: str = "",
) -> dict[str, Any]:
    """Render one timeline entry with everything the website needs."""
    return {
        "slug": app.slug,
        "name": app.name,
        "version": version,
        "previousVersion": previous_version,
        "date": date_str[:10],
        "kind": kind,
        "changelog": changelog,
        "downloadURL": download_url,
        "iconURL": f"{base}/assets/{app.icon}",
        "feedURL": f"{base}/feeds/{app.slug}.json",
        "rssURL": f"{base}/feeds/{app.slug}.xml",
        "status": app.status,
        "shortDescription": app.short_description,
    }


def render_updates_doc(catalog: Catalog, state: dict[str, Any], limit: int = 40) -> dict[str, Any]:
    """Build the updates timeline from recorded history, seeded by current versions."""
    base = catalog.base_url.rstrip("/")
    app_by_slug = {app.slug: app for app in catalog.apps}
    app_by_bundle = {app.bundle_id: app for app in catalog.apps}
    updates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    # 1. Recorded update events (new versions, hotfixes, unmaintained flags).
    history = state.get("updateHistory", [])
    if isinstance(history, list):
        for event in history:
            if not isinstance(event, dict):
                continue
            app_id = str(event.get("appId") or "")
            app = app_by_slug.get(app_id) or app_by_bundle.get(app_id)
            if not app:
                continue
            version = str(event.get("version") or "")
            key = (app.slug, version)
            if not version or key in seen:
                continue
            seen.add(key)
            updates.append(
                _event_dict(
                    app=app,
                    base=base,
                    version=version,
                    date_str=str(event.get("releaseDate") or event.get("date") or ""),
                    kind=str(event.get("kind") or "updated"),
                    changelog=str(event.get("changelog") or ""),
                    download_url=str(event.get("downloadUrl") or ""),
                    previous_version=str(event.get("previousVersion") or ""),
                )
            )
            if len(updates) >= limit:
                break

    # 2. Seed with the newest known version per app so the timeline is always
    #    populated, even right after a fresh catalog bootstrap.
    if len(updates) < limit:
        for app in catalog.apps:
            versions = state.get(app.slug, {}).get("versions")
            if not isinstance(versions, list) or not versions:
                continue
            newest = versions[0]
            version = str(newest.get("version") or "")
            key = (app.slug, version)
            if not version or key in seen:
                continue
            seen.add(key)
            updates.append(
                _event_dict(
                    app=app,
                    base=base,
                    version=version,
                    date_str=str(newest.get("date") or ""),
                    kind="available",
                    changelog=str(newest.get("localizedDescription") or ""),
                    download_url=str(newest.get("downloadURL") or ""),
                )
            )
            if len(updates) >= limit:
                break

    updates.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    generated_at = max((str(item.get("date") or "") for item in updates), default="")
    return {
        "generatedAt": generated_at,
        "sourceURL": f"{base}/apps.json",
        "count": len(updates),
        "updates": updates[:limit],
    }
