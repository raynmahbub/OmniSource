"""Privacy-preserving source and package intelligence.

Insights are derived from catalog snapshots, release history, validation, and
health probes.  No user accounts, clicks, ratings, comments, or behavioral
profiles are read.  "Popularity" in this system means observable catalog
coverage and release availability, not user activity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from omnisource.release_history import QUARANTINED

SCHEMA_VERSION = 1


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _apps(source: dict[str, Any]) -> set[str]:
    values = source.get("app_ids", source.get("apps", []))
    if not isinstance(values, list):
        return set()
    app_ids: set[str] = set()
    for item in values:
        value = (item.get("id") or item.get("slug")) if isinstance(item, dict) else item
        if isinstance(value, str) and value:
            app_ids.add(value)
    return app_ids


def build_source_insights(
    registry: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
    release_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute source growth/decline, churn, cadence, and health trends."""
    old_by_id = {
        str(item.get("source_id") or item.get("id")): item
        for item in (previous or {}).get("sources", [])
        if isinstance(item, dict) and (item.get("source_id") or item.get("id"))
    }
    insights: list[dict[str, Any]] = []
    for source in registry.get("sources", []) if isinstance(registry, dict) else []:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or source.get("id") or "")
        current_apps = _apps(source)
        prior = old_by_id.get(source_id)
        if isinstance(prior, dict) and (isinstance(prior.get("app_ids"), list) or isinstance(prior.get("apps"), list)):
            previous_apps = _apps(prior)
        elif prior is None and isinstance(previous, dict) and isinstance(previous.get("sources"), list):
            previous_apps = set()  # A new source since an existing baseline.
        else:
            # Old insight documents did not store membership. An absent
            # baseline is unknown, not evidence that every app was just added.
            previous_apps = current_apps
        added = sorted(current_apps - previous_apps)
        removed = sorted(previous_apps - current_apps)
        history = source.get("history", [])
        # Older registry rows were build snapshots, not necessarily probes.
        # Count only dated URL-bound observations, deduplicated by timestamp;
        # keep different endpoints out of the same uptime calculation.
        samples: dict[tuple[str, str], str] = {}
        for item in history if isinstance(history, list) else []:
            if not isinstance(item, dict):
                continue
            health = str(item.get("health") or "").casefold()
            at, url = str(item.get("observedAt") or ""), str(item.get("observationURL") or "")
            try:
                parsed = datetime.fromisoformat(at.replace("Z", "+00:00"))
                if parsed.tzinfo is None or not url.startswith("https://") or health not in {"online", "offline"}:
                    continue
            except ValueError:
                continue
            samples[(at, url)] = health
        latest_url = (
            max(samples, key=lambda key: datetime.fromisoformat(key[0].replace("Z", "+00:00")))[1] if samples else ""
        )
        health_values = [health for (_, url), health in samples.items() if url == latest_url]
        online_samples = sum(value == "online" for value in health_values)
        uptime = round(online_samples / len(health_values) * 100, 2) if health_values else None
        last_sync = str(source.get("last_sync") or "")
        cadence_days = _cadence_days(source, release_history)
        if added and not removed:
            trend = "growing"
        elif removed and not added:
            trend = "declining"
        elif added or removed:
            trend = "changing"
        else:
            trend = "stable"
        insights.append(
            {
                "source_id": source_id,
                "source_name": source.get("source_name", source_id),
                "trend": trend,
                "app_ids": sorted(current_apps),
                "apps_added": added,
                "apps_removed": removed,
                "app_delta": len(current_apps) - len(previous_apps),
                "update_frequency_days": cadence_days,
                "health_samples": len(health_values),
                "observed_uptime_percent": uptime,
                "last_sync": last_sync,
            }
        )
    insights.sort(key=lambda item: (item["trend"] != "declining", str(item["source_name"]).casefold()))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utcnow(),
        "method": "catalog-and-health-observations",
        "privacy": {"usesUserActivity": False, "usesAccounts": False},
        "count": len(insights),
        "summary": {
            "growing": sum(item["trend"] == "growing" for item in insights),
            "declining": sum(item["trend"] == "declining" for item in insights),
            "stable": sum(item["trend"] == "stable" for item in insights),
            "changing": sum(item["trend"] == "changing" for item in insights),
        },
        "sources": insights,
    }


def _cadence_days(source: dict[str, Any], release_history: dict[str, Any] | None) -> float | None:
    history = (release_history or {}).get("apps", {}) if isinstance(release_history, dict) else {}
    dates: list[datetime] = []
    for app in source.get("apps", []) if isinstance(source.get("apps"), list) else []:
        app_id = str(app.get("id") or app.get("slug") or "") if isinstance(app, dict) else ""
        records = history.get(app_id, []) if isinstance(history, dict) else []
        for release in records:
            if not isinstance(release, dict) or release.get("status") == QUARANTINED:
                continue
            value = str(release.get("date") or "")[:10]
            try:
                dates.append(datetime.fromisoformat(value).replace(tzinfo=UTC))
            except ValueError:
                continue
    dates.sort()
    if len(dates) < 2:
        return None
    gaps = [(right - left).days for left, right in pairwise(dates) if (right - left).days >= 0]
    return round(sum(gaps) / len(gaps), 2) if gaps else None


def build_package_intelligence(
    apps: list[dict[str, Any]],
    *,
    release_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render first/last seen, cadence, release count, and source count."""
    release_apps = (release_history or {}).get("apps", {}) if isinstance(release_history, dict) else {}
    records: list[dict[str, Any]] = []
    for app in apps:
        if not isinstance(app, dict):
            continue
        # Published AltStore entries carry their stable catalog slug inside
        # the extension block rather than at the top level. Without it every
        # entry is assigned an empty ID and misses its release history.
        omni = app.get("omnisource") if isinstance(app.get("omnisource"), dict) else {}
        app_id = str(app.get("id") or app.get("slug") or omni.get("slug") or "")
        releases = release_apps.get(app_id, []) if isinstance(release_apps, dict) else []
        releases = [item for item in releases if isinstance(item, dict) and item.get("status") != QUARANTINED]
        dates = sorted(str(item.get("date") or "")[:10] for item in releases if item.get("date"))
        sources = app.get("sources", app.get("sourceCount", []))
        source_count = len(sources) if isinstance(sources, list) else int(sources or 0)
        records.append(
            {
                "app_id": app_id,
                "name": str(app.get("name") or app_id),
                "first_seen": dates[0] if dates else str(app.get("firstSeen") or app.get("versionDate") or ""),
                "last_updated": dates[-1] if dates else str(app.get("versionDate") or ""),
                "update_frequency_days": _date_gap(dates),
                "release_count": len(releases) or len(app.get("versions", []))
                if isinstance(app.get("versions"), list)
                else len(releases),
                "source_count": source_count,
                "bundle_identifier": str(app.get("bundleIdentifier") or ""),
            }
        )
    records.sort(key=lambda item: str(item["app_id"]))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": utcnow(),
        "count": len(records),
        "apps": records,
    }


def _date_gap(dates: list[str]) -> float | None:
    values: list[datetime] = []
    for value in dates:
        try:
            values.append(datetime.fromisoformat(value).replace(tzinfo=UTC))
        except ValueError:
            continue
    if len(values) < 2:
        return None
    gaps = [(right - left).days for left, right in pairwise(values)]
    return round(sum(gaps) / len(gaps), 2)


def build_timeline(registry: dict[str, Any]) -> dict[str, Any]:
    """Flatten source history into a UI-friendly source timeline."""
    events: list[dict[str, Any]] = []
    for source in registry.get("sources", []) if isinstance(registry, dict) else []:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "")
        events.append({"at": source.get("first_seen", ""), "type": "source_created", "source_id": source_id})
        for snapshot in source.get("history", []) if isinstance(source.get("history"), list) else []:
            if not isinstance(snapshot, dict):
                continue
            at = str(snapshot.get("at") or "")
            events.append(
                {"at": at, "type": "health_changed", "source_id": source_id, "health": snapshot.get("health")}
            )
            events.append(
                {
                    "at": at,
                    "type": "verification_changed",
                    "source_id": source_id,
                    "verification": snapshot.get("verification", ""),
                }
            )
    events = [item for item in events if item.get("at")]
    events.sort(key=lambda item: (str(item["at"]), str(item["source_id"])))
    return {"schemaVersion": SCHEMA_VERSION, "generatedAt": utcnow(), "count": len(events), "events": events}


__all__ = ["build_package_intelligence", "build_source_insights", "build_timeline"]
