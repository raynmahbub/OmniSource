"""Global source registry and source lifecycle history.

The registry is deliberately source-centric: it records where a feed comes
from, how it was verified, its observed health, and the applications/releases
it currently contributes.  It does not contain users, reviews, ratings, or
personalization signals.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

REGISTRY_SCHEMA_VERSION = 1
CLASSIFICATIONS = ("Official", "Verified", "Community", "Experimental", "Archived")


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def stable_id(value: Any) -> str:
    raw = str(value or "").strip()
    if raw:
        slug = re.sub(r"[^a-z0-9]+", "-", raw.casefold()).strip("-")
        if slug:
            return slug[:64]
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _score(source: dict[str, Any], reputation: dict[str, Any] | None) -> float:
    value = source.get("score", source.get("reputation", source.get("reputation_score", 0)))
    if isinstance(reputation, dict):
        source_id = str(source.get("id") or source.get("source_id") or source.get("source") or "")
        for item in reputation.get("sources", []):
            if isinstance(item, dict) and str(item.get("id") or item.get("source") or "") in {
                source_id,
                str(source.get("source")),
            }:
                value = item.get("score", value)
                break
    try:
        return round(max(0.0, min(100.0, float(value or 0))), 2)
    except (TypeError, ValueError):
        return 0.0


def classify_source(
    source: dict[str, Any],
    *,
    score: float = 0.0,
    archived: bool = False,
) -> str:
    """Classify a source from explicit provenance and observed evidence."""
    if (
        archived
        or bool(source.get("archived"))
        or str(source.get("status", "")).casefold()
        in {
            "archived",
            "deprecated",
        }
    ):
        return "Archived"
    verification = str(source.get("verification_status") or source.get("verification") or "").casefold()
    source_type = str(source.get("type") or source.get("source_type") or "").casefold()
    publisher = str(source.get("publisher") or source.get("owner") or "").casefold()
    if source.get("official") is True or verification in {"official", "verified official"}:
        return "Official"
    if "community" in verification or "community" in publisher or source_type in {"community", "mirror"}:
        return "Community"
    if score >= 85 or verification in {"verified", "trusted"}:
        return "Verified"
    if score >= 25 or source.get("apps"):
        return "Experimental"
    return "Experimental"


def _source_url(source: dict[str, Any]) -> str:
    return str(
        source.get("sourceURL")
        or source.get("source_url")
        or source.get("url")
        or source.get("homepage")
        or source.get("feedURL")
        or ""
    )


def _instant(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _source_observation(source: dict[str, Any], status: dict[str, Any] | None) -> dict[str, str] | None:
    """Use a dated monitor result only when it checked this exact source URL.

    Some monitoring snapshots check a host's root rather than the feed or
    project URL. Such a probe says nothing about the source itself.
    """
    if not isinstance(status, dict):
        return None
    at = str(status.get("generatedAt") or "")
    if _instant(at) is None:
        return None
    source_id = str(source.get("id") or source.get("source_id") or source.get("source") or "")
    expected = {_source_url(source), source_id}
    nodes = status.get("sources", [])
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict) or str(node.get("id") or node.get("source_id") or "") != source_id:
            continue
        url = str(node.get("url") or "")
        if not url.startswith("https://") or url not in expected or not isinstance(node.get("ok"), bool):
            return None
        return {"at": at, "url": url, "health": "online" if node["ok"] else "offline"}
    return None


def build_registry(
    sources: list[dict[str, Any]],
    *,
    discovered: list[dict[str, Any]] | None = None,
    status: dict[str, Any] | None = None,
    reputation: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a registry while preserving per-source history."""
    previous_sources = previous.get("sources", []) if isinstance(previous, dict) else []
    previous_by_id = {
        str(item.get("source_id") or item.get("id")): item
        for item in previous_sources
        if isinstance(item, dict) and (item.get("source_id") or item.get("id"))
    }
    current: dict[str, dict[str, Any]] = {}
    # Hand-maintained/catalog sources are already publication inputs. A
    # discovered record is an untrusted candidate until the explicit verifier
    # marks it verified or published; quarantined/validating candidates never
    # enter the public registry projection.
    discovered_public = [
        raw
        for raw in (discovered or [])
        if isinstance(raw, dict)
        and str(raw.get("status", "")).casefold() in {"verified", "published"}
        and str(raw.get("verification_status", "")).casefold() in {"verified", "trusted", "official"}
        and not raw.get("errors")
    ]
    for raw in [*sources, *discovered_public]:
        if not isinstance(raw, dict):
            continue
        url = _source_url(raw)
        key = str(raw.get("id") or raw.get("source_id") or raw.get("source") or url)
        source_id = stable_id(key)
        score = _score(raw, reputation)
        old = previous_by_id.get(source_id, {})
        observation = _source_observation(raw, status)
        previous_observation = old.get("last_health_observation")
        if not isinstance(previous_observation, dict) or (
            previous_observation.get("url") not in {key, url}
            or _instant(previous_observation.get("at")) is None
            or previous_observation.get("health") not in {"online", "offline"}
        ):
            previous_observation = None
        incoming_at = _instant(observation.get("at")) if observation else None
        previous_at = _instant(previous_observation.get("at")) if previous_observation else None
        new_observation = incoming_at is not None and (previous_at is None or incoming_at > previous_at)
        current_observation = observation if new_observation else previous_observation
        health = current_observation["health"] if current_observation else "unknown"
        apps = raw.get("apps", [])
        app_count = len(apps) if isinstance(apps, list) else int(raw.get("appCount", 0) or 0)
        first_seen = str(
            old.get("first_seen")
            or old.get("firstSeen")
            or raw.get("first_seen")
            or raw.get("discovered_at")
            or utcnow()
        )
        record = {
            "source_id": source_id,
            "source_name": str(raw.get("source_name") or raw.get("name") or raw.get("source") or url or source_id),
            "source_type": str(raw.get("source_type") or raw.get("type") or "unknown"),
            "source_url": url,
            "classification": classify_source(raw, score=score),
            "verification_status": str(raw.get("verification_status") or raw.get("verification") or "unverified"),
            "reputation_score": score,
            "health_status": health,
            "last_health_observation": current_observation,
            "uptime": None,
            "first_seen": first_seen,
            "last_seen": str(raw.get("last_seen") or raw.get("last_checked") or old.get("last_seen") or first_seen),
            "last_sync": str(raw.get("last_sync") or raw.get("lastUpdate") or raw.get("last_checked") or ""),
            "app_count": app_count,
            "release_count": int(raw.get("releaseCount", 0) or 0),
            "apps": [
                {
                    "id": str(item.get("slug") or item.get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "version": str(item.get("version") or ""),
                }
                for item in apps
                if isinstance(item, dict)
            ],
            "history": list(old.get("history", [])) if isinstance(old.get("history"), list) else [],
        }
        observed_at = _instant(current_observation.get("at")) if current_observation else None
        last_seen_at = _instant(record["last_seen"])
        if observed_at and (last_seen_at is None or observed_at > last_seen_at):
            record["last_seen"] = current_observation["at"]
        history = record["history"]
        material = {"reputation": score, "appCount": app_count, "verification": record["verification_status"]}
        last = history[-1] if history and isinstance(history[-1], dict) else {}
        material_changed = not last or any(last.get(key) != value for key, value in material.items())
        # A rebuild is not a new probe. Record a monitor observation at its
        # original time only once; metadata-only snapshots have unknown health.
        seen_observation = bool(
            observation
            and any(
                isinstance(item, dict)
                and item.get("observedAt") == observation["at"]
                and item.get("observationURL") == observation["url"]
                for item in history
            )
        )
        new_observation = new_observation and not seen_observation
        if material_changed or new_observation:
            snapshot = {"at": observation["at"] if new_observation else utcnow(), "health": "unknown", **material}
            if new_observation and observation:
                snapshot.update(
                    health=observation["health"], observedAt=observation["at"], observationURL=observation["url"]
                )
            history.append(snapshot)
        record["history"] = history[-90:]
        current[source_id] = record
    # Keep historical records that disappeared from the feed as Archived rather
    # than deleting them; this supports timeline and rollback audits.
    for source_id, old in previous_by_id.items():
        if source_id in current or not isinstance(old, dict):
            continue
        archived = dict(old)
        archived["classification"] = "Archived"
        # Disappearance from the catalog is not a failed network observation.
        archived["health_status"] = "unknown"
        archived["history"] = list(old.get("history", [])) if isinstance(old.get("history"), list) else []
        current[source_id] = archived
    records = sorted(current.values(), key=lambda item: str(item.get("source_name", "")).casefold())
    unchanged = isinstance(previous, dict) and previous.get("sources") == records
    return {
        "schemaVersion": REGISTRY_SCHEMA_VERSION,
        "generatedAt": str(previous.get("generatedAt") or utcnow()) if unchanged else utcnow(),
        "count": len(records),
        "classifications": {
            name: sum(1 for item in records if item.get("classification") == name) for name in CLASSIFICATIONS
        },
        "sources": records,
    }


def source_by_id(registry: dict[str, Any], source_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in registry.get("sources", []) if isinstance(item, dict) and item.get("source_id") == source_id),
        None,
    )


__all__ = ["CLASSIFICATIONS", "build_registry", "classify_source", "source_by_id", "stable_id"]
