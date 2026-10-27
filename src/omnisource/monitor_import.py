"""Explicitly import dated monitoring observations into pipeline state.

This is intentionally not part of an offline rebuild: ``data/status.json`` is
updated independently and automatically consuming it would make every
monitoring commit invalidate generated feeds. Operators may opt in when they
want to republish an existing observation, without pretending a new probe ran.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from omnisource.domain import Catalog
from omnisource.monitor import HISTORY_LIMIT


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


def import_snapshot(catalog: Catalog, state: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, int]:
    """Import exact app/URL matches, preserving the recorded check time.

    Unknown IDs, URL mismatches, invalid observations, and newer already-bound
    pipeline observations are left untouched. Mutates only ``state``.
    """
    observed_at = snapshot.get("generatedAt")
    observed = _timestamp(observed_at)
    downloads = snapshot.get("downloads")
    if observed is None or not isinstance(downloads, list):
        raise ValueError("monitoring snapshot requires a valid generatedAt and downloads array")
    rows = [row for row in downloads if isinstance(row, dict)]
    names: dict[str, int] = {}
    for app in catalog.apps:
        names[app.name] = names.get(app.name, 0) + 1
    counts = {"imported": 0, "skipped": 0}
    for app in catalog.apps:
        entry = state.get(app.slug)
        versions = entry.get("versions") if isinstance(entry, dict) else None
        if not isinstance(versions, list) or not versions or not isinstance(versions[0], dict):
            counts["skipped"] += 1
            continue
        url = versions[0].get("downloadURL")
        candidates = [row for row in rows if row.get("id") == app.slug]
        if not candidates and names[app.name] == 1:
            candidates = [row for row in rows if row.get("id") == app.name]
        matches = [row for row in candidates if url and row.get("url") == url and isinstance(row.get("ok"), bool)]
        if len(matches) != 1:
            counts["skipped"] += 1
            continue
        result = matches[0]
        health = entry.get("health") if isinstance(entry.get("health"), dict) else {}
        existing_raw = health.get("measuredAt")
        existing = _timestamp(existing_raw)
        # Compare precise timestamps exactly. When either side is date-only,
        # its time is unknown, so retain a bound result from the same day.
        date_only = len(str(existing_raw or "").strip()) == 10 or len(str(observed_at).strip()) == 10
        if health.get("checkedURL") == url and existing:
            newer_or_equal = existing.date() >= observed.date() if date_only else existing >= observed
            if newer_or_equal:
                counts["skipped"] += 1
                continue
        status = result.get("status")
        detail = str(result.get("error") or (f"HTTP {status}" if isinstance(status, int) else "probe completed"))
        latency = result.get("latency_ms")
        latency = int(latency) if isinstance(latency, (int, float)) and not isinstance(latency, bool) else 0
        reachable = result["ok"]
        entry["health"] = {
            **health,
            "reachable": reachable,
            "detail": detail,
            "latencyMs": latency,
            "measuredAt": observed_at,
            "checkedURL": url,
            "since": (health.get("since") or observed.date().isoformat())
            if health.get("checkedURL") == url and health.get("reachable") is reachable
            else observed.date().isoformat(),
        }
        history = entry.get("healthHistory") if isinstance(entry.get("healthHistory"), list) else []
        history = [item for item in history if isinstance(item, dict)]
        history.append({"at": observed_at, "reachable": reachable, "latencyMs": latency, "detail": detail[:120]})
        history.sort(key=lambda item: str(item.get("at") or item.get("date") or ""))
        entry["healthHistory"] = history[-HISTORY_LIMIT:]
        counts["imported"] += 1
    return counts
