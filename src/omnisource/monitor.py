"""Source health monitoring.

Runs inside the feed build (no separate daemon): every sync probes each app's
primary download URL, records latency and reachability in pipeline state, and
this module renders ``feeds/status.json`` — the machine-readable health board
consumed by the website and monitoring dashboards.

Per-source history is stored in ``state.json`` (``healthHistory``, capped), so
the status document can carry a rolling window without an external database.
History is only appended when the pipeline actually probes (``--no-health``
builds keep the previous window untouched, which also keeps offline
reproducibility checks stable).
"""

from __future__ import annotations

from typing import Any

from omnisource.discovery import newest_version, source_label
from omnisource.domain import Catalog, today

STATUS_SCHEMA_VERSION = 1
HISTORY_LIMIT = 30
WINDOW = 14

# status values
HEALTHY = "healthy"
DEGRADED = "degraded"
UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"


def _status(reachable: bool | None, stale: bool) -> str:
    if reachable is None:
        return UNKNOWN
    if not reachable:
        return UNAVAILABLE
    return DEGRADED if stale else HEALTHY


def build_status_doc(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render ``status.json`` from the pipeline state and health document."""
    health_doc = health_doc or {}
    health_by_slug = {item.get("slug"): item for item in health_doc.get("apps", []) if isinstance(item, dict)}
    entries: list[dict[str, Any]] = []
    totals = {HEALTHY: 0, DEGRADED: 0, UNAVAILABLE: 0, UNKNOWN: 0}

    for app in catalog.apps:
        app_state = state.get(app.slug, {}) if isinstance(state.get(app.slug), dict) else {}
        health = app_state.get("health", {}) if isinstance(app_state.get("health"), dict) else {}
        health_item = health_by_slug.get(app.slug, {})
        reachable = health.get("reachable") if isinstance(health.get("reachable"), bool) else None
        newest = newest_version(state, app.slug)
        checked_url = str(health.get("checkedURL") or "")
        if not checked_url or checked_url != str(newest.get("downloadURL") or ""):
            reachable = None
        raw_latency = health.get("latencyMs")
        latency = None if raw_latency is None or reachable is None else int(raw_latency)
        status = _status(reachable, bool(health_item.get("stale", False)))
        totals[status] += 1

        history = [item for item in app_state.get("healthHistory", []) if isinstance(item, dict)][-WINDOW:]
        last_check = str(
            health.get("measuredAt") or (history[-1].get("at") or history[-1].get("date") if history else "") or ""
        )
        entries.append(
            {
                "id": app.slug,
                "app": app.slug,
                "name": app.name,
                "source": source_label(app),
                "sourceURL": app.source_url,
                "type": app.source_type.value,
                "status": status,
                "reachable": reachable,
                "latency": latency,
                "latencyMs": latency,
                "checkedAt": last_check if reachable is not None else "",
                "checkedURL": checked_url if reachable is not None else "",
                "lastUpdate": str(newest.get("date") or ""),
                "valid": True,  # the feed JSON was parsed and rebuilt on this run
                "detail": health.get("detail", ""),
                "history": history,
            }
        )

    entries.sort(key=lambda item: (item["status"] != HEALTHY, str(item["name"]).casefold()))
    return {
        "schemaVersion": STATUS_SCHEMA_VERSION,
        "generatedAt": today(),
        "totals": {"sources": len(entries), **totals},
        "pipeline": _pipeline_section(state, len(entries), totals),
        "providers": _provider_section(entries, state),
        "deployment": _deployment_section(totals, len(entries)),
        "sources": entries,
    }


def _pipeline_section(state: dict[str, Any], apps_total: int, totals: dict[str, int]) -> dict[str, Any]:
    """Feed-generation health from pipeline state (Phase 15)."""
    last_build = ""
    failing = 0
    for slug, value in state.items():
        if not isinstance(value, dict) or slug in {"updateHistory", "schemaVersion"}:
            continue
        synced_at = str(value.get("syncedAt") or "")
        if synced_at > last_build:
            last_build = synced_at
        if value.get("lastError"):
            failing += 1
    return {
        "status": "ok" if failing == 0 else "degraded",
        "lastBuild": last_build,
        "appsTotal": apps_total,
        "appsHealthy": totals.get(HEALTHY, 0),
        "appsFailing": failing,
    }


def _provider_section(entries: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-provider-kind availability + the failover leg that supplied each app (Phase 2/15)."""
    by_provider: dict[str, dict[str, Any]] = {}
    for entry in entries:
        provider = str(entry.get("type") or "unknown")
        info = by_provider.setdefault(
            provider,
            {"provider": provider, "apps": 0, "healthy": 0, "unavailable": 0, "lastResolvedFrom": {}},
        )
        info["apps"] += 1
        if entry.get("status") == HEALTHY:
            info["healthy"] += 1
        if entry.get("status") == UNAVAILABLE:
            info["unavailable"] += 1
        app_state = state.get(str(entry.get("app")))
        resolved = app_state.get("lastResolvedSource") if isinstance(app_state, dict) else None
        if resolved:
            info["lastResolvedFrom"][str(entry.get("app"))] = str(resolved)
    providers = sorted(by_provider.values(), key=lambda item: item["provider"])
    for info in providers:
        if not info["lastResolvedFrom"]:
            del info["lastResolvedFrom"]
    return providers


def _deployment_section(totals: dict[str, int], apps_total: int) -> dict[str, Any]:
    """Deployment status for the static GitHub Pages target (Phase 15).

    Pages has no server to report from, so the observable signal is the build
    itself: the sync workflow assembles and publishes the site in the same run,
    a fully reachable catalog means the deployed feeds are installable.
    """
    unavailable = totals.get(UNAVAILABLE, 0)
    status = "ok"
    if unavailable == apps_total and apps_total > 0:
        status = "unavailable"
    elif unavailable > 0:
        status = "degraded"
    return {
        "platform": "GitHub Pages (static)",
        "status": status,
        "reachable": apps_total - unavailable,
        "total": apps_total,
    }


def remember_probe(state: dict[str, Any], slug: str, *, reachable: bool, detail: str, latency_ms: float) -> None:
    """Record one probe in memory; the pipeline persists ``state`` afterwards."""
    entry = state.setdefault(slug, {})
    if not isinstance(entry, dict):
        entry = {}
        state[slug] = entry
    health = entry.setdefault("health", {})
    if not isinstance(health, dict):
        health = {}
        entry["health"] = health
    health["reachable"] = bool(reachable)
    health["detail"] = str(detail)
    health["latencyMs"] = int(latency_ms)
    health["measuredAt"] = today()

    history = entry.setdefault("healthHistory", [])
    if not isinstance(history, list):
        history = []
        entry["healthHistory"] = history
    history.append(
        {
            "at": today(),
            "reachable": bool(reachable),
            "latencyMs": int(latency_ms),
            "detail": str(detail)[:120],
        }
    )
    del history[:-HISTORY_LIMIT]
