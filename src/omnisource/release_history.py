"""Release tracking: append-only version history with rollback support.

The pipeline ``state.json`` keeps only the newest versions per app. This
module compiles those snapshots into ``data/release_history.json`` — an
append-only ledger that never deletes old releases, so clients can:

* compare versions (``is_newer`` / :func:`compare_entries`),
* roll back to any previously seen release (:func:`rollback_plan`),
* audit yanked or re-published binaries (:func:`detect_removed`).

History entries carry a lifecycle ``status``: ``current`` (newest known),
``superseded`` (replaced by a newer release), ``removed`` (the upstream
no longer lists it), or ``quarantined`` (retained evidence of a known identity
mismatch; never offered as a rollback).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from omnisource.utils.versioning import compare_versions

HISTORY_SCHEMA_VERSION = 1

CURRENT = "current"
SUPERSEDED = "superseded"
REMOVED = "removed"
QUARANTINED = "quarantined"


def utcnow() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def entry_key(entry: dict[str, Any]) -> str:
    """Identity of one release entry (version + date + download URL)."""
    return "|".join(str(entry.get(field, "")) for field in ("version", "date", "downloadURL"))


def normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
    """Project a state.json version entry onto the ledger schema."""
    return {
        "version": str(raw.get("version", "")),
        "date": str(raw.get("date", "")),
        "downloadURL": str(raw.get("downloadURL", "")),
        "size": raw.get("size", 0) if isinstance(raw.get("size"), int) else 0,
        "sha256": (raw.get("sha256") or raw.get("digest") or "") or "",
        "localizedDescription": str(raw.get("localizedDescription", ""))[:2000],
        "status": CURRENT,
        "firstSeen": raw.get("firstSeen") or utcnow(),
    }


def merge_app_history(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge a fresh version list into the stored ledger (never deletes)."""
    known = {entry_key(entry): dict(entry) for entry in previous if isinstance(entry, dict)}
    fresh_keys: set[str] = set()
    for raw in current:
        if not isinstance(raw, dict) or not raw.get("version"):
            continue
        entry = normalize_entry(raw)
        key = entry_key(entry)
        # A previously identified identity mismatch requires explicit review,
        # not silent reactivation merely because a source repeats the URL.
        if key in known and known[key].get("status") == QUARANTINED:
            continue
        fresh_keys.add(key)
        if key in known:
            known[key]["status"] = CURRENT
            for field in ("size", "sha256", "localizedDescription"):
                if entry[field]:
                    known[key][field] = entry[field]
        else:
            known[key] = entry
    newest_key = entry_key(normalize_entry(current[0])) if current else ""
    newest_version = str(current[0].get("version", "")) if current else ""
    for key, entry in known.items():
        if entry.get("status") == QUARANTINED:
            continue
        if key == newest_key:
            entry["status"] = CURRENT
        elif key in fresh_keys:
            entry["status"] = SUPERSEDED
        elif compare_versions(str(entry.get("version", "")), newest_version) < 0:
            # Replaced by a newer release but still addressable: superseded.
            entry["status"] = SUPERSEDED
        elif entry.get("status") == CURRENT:
            # Newer than anything the upstream still lists: yanked/removed.
            entry["status"] = REMOVED
    ordered = sorted(
        known.values(),
        key=lambda item: (item.get("date", ""), str(item.get("version", ""))),
        reverse=True,
    )
    return ordered


def build_history(
    state: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the full ledger document from pipeline state + prior ledger."""
    prior = previous.get("apps", {}) if isinstance(previous, dict) else {}
    if not isinstance(prior, dict):
        prior = {}
    apps: dict[str, list[dict[str, Any]]] = {}
    for slug, node in sorted(state.items()):
        if not isinstance(node, dict) or not isinstance(node.get("versions"), list):
            continue
        old = prior.get(slug, [])
        apps[slug] = merge_app_history(
            [entry for entry in old if isinstance(entry, dict)],
            [entry for entry in node["versions"] if isinstance(entry, dict)],
        )
    releases = sum(len(entries) for entries in apps.values())
    return {
        "schemaVersion": HISTORY_SCHEMA_VERSION,
        "generatedAt": utcnow(),
        "appCount": len(apps),
        "releases": releases,
        "apps": apps,
    }


def compare_entries(left: dict[str, Any], right: dict[str, Any]) -> int:
    """Compare two ledger entries by version, then date (-1/0/1)."""
    verdict = compare_versions(str(left.get("version", "")), str(right.get("version", "")))
    if verdict:
        return verdict
    left_date, right_date = str(left.get("date", "")), str(right.get("date", ""))
    return (left_date > right_date) - (left_date < right_date)


def rollback_plan(
    history: list[dict[str, Any]],
    target_version: str,
) -> dict[str, Any]:
    """Plan a downgrade to ``target_version`` (empty plan when impossible)."""
    entries = [entry for entry in history if isinstance(entry, dict) and entry.get("status") != QUARANTINED]
    current = next((entry for entry in entries if entry.get("status") == CURRENT), entries[0] if entries else None)
    target = next((entry for entry in entries if str(entry.get("version")) == target_version), None)
    if current is None or target is None:
        return {"ok": False, "reason": "unknown version", "target": target_version}
    if entry_key(current) == entry_key(target):
        return {"ok": True, "noop": True, "target": target_version}
    return {
        "ok": True,
        "noop": False,
        "from": current.get("version"),
        "target": target_version,
        "downloadURL": target.get("downloadURL", ""),
        "size": target.get("size", 0),
        "sha256": target.get("sha256", ""),
        "downgrade": compare_entries(target, current) < 0,
    }


def detect_removed(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entries present in ``previous`` but absent from ``current``."""
    fresh = {entry_key(entry) for entry in current if isinstance(entry, dict)}
    return [
        entry
        for entry in previous
        if isinstance(entry, dict) and entry.get("status") != QUARANTINED and entry_key(entry) not in fresh
    ]
