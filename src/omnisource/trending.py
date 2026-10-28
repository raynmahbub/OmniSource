"""Trending score engine for the OmniSource discovery layer.

The score combines four signals from already-generated artifacts (state, health,
verification, analytics). It is a deterministic, explainable 0..1 value that the
website and any future client can use to surface "what is hot" without
external services.

Score formula
-------------
::

    trending_score =
        recency_signal     * 0.40
      + availability_signal * 0.20
      + featured_bonus     * 0.20
      + verification_bonus * 0.20

* ``recency_signal`` decays linearly from 1.0 (released today) to 0.0 after
  ``RECENCY_FLOOR_DAYS`` days. New releases are the strongest discovery signal.
* ``availability_signal`` is 1.0 when the download is currently reachable,
  0.0 otherwise (degraded reduces it to 0.5).
* ``featured_bonus`` is 1.0 when the catalog marks the app as ``featured``.
* ``verification_bonus`` maps the verification level to a number — VERIFIED
  is 1.0, COMMUNITY is 0.7, MANUAL is 0.4, UNVERIFIED is 0.0.

The function returns the rounded score plus a per-signal breakdown so the
website can show the formula on hover / in tooltips.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from omnisource.discovery import newest_version
from omnisource.domain import Catalog, today

TRENDING_SCHEMA_VERSION = 1
RECENCY_FLOOR_DAYS = 60

# Verification levels used by the discovery engine. Values are intentionally
# ordered: an unverified app must never outrank a verified one on the
# "trending" board.
VERIFICATION_WEIGHT = {
    "VERIFIED": 1.0,
    "COMMUNITY": 0.7,
    "MANUAL": 0.4,
    "UNVERIFIED": 0.0,
}


def _days_since(iso: str, *, today_iso: str) -> int:
    try:
        parsed = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return RECENCY_FLOOR_DAYS
    try:
        end = date.fromisoformat(today_iso[:10])
    except ValueError:
        return RECENCY_FLOOR_DAYS
    return max(0, (end - parsed).days)


def _recency(release_date: str, *, today_iso: str) -> float:
    days = _days_since(release_date, today_iso=today_iso)
    if days >= RECENCY_FLOOR_DAYS:
        return 0.0
    return round(1.0 - (days / RECENCY_FLOOR_DAYS), 4)


def _availability(health: dict[str, Any]) -> float:
    if not isinstance(health, dict):
        return 0.0
    if health.get("downloadReachable") is True:
        # Slight latency penalty: a slow mirror is still available but
        # contributes a touch less than a snappy one.
        latency = health.get("latencyMs")
        if isinstance(latency, (int, float)) and latency > 4000:
            return 0.85
        return 1.0
    status = str(health.get("status") or "").lower()
    if status == "degraded":
        return 0.5
    return 0.0


def _featured(app: Any) -> float:
    return 1.0 if bool(getattr(app, "featured", False)) else 0.0


def _verification(level: str) -> float:
    return VERIFICATION_WEIGHT.get(str(level or "UNVERIFIED").upper(), 0.0)


def compute_trending(
    app: Any,
    state: dict[str, Any],
    health: dict[str, Any] | None,
    verification_level: str,
    *,
    today_iso: str | None = None,
) -> dict[str, Any]:
    """Return the trending score breakdown for a single app."""
    newest = newest_version(state, app.slug)
    today_iso = today_iso or today()
    release = str(newest.get("date") or "")
    recency = _recency(release, today_iso=today_iso)
    availability = _availability(health or {})
    featured = _featured(app)
    verification = _verification(verification_level)
    score = round(
        recency * 0.4 + availability * 0.2 + featured * 0.2 + verification * 0.2,
        4,
    )
    return {
        "slug": app.slug,
        "name": app.name,
        "category": app.category,
        "version": str(newest.get("version") or ""),
        "releaseDate": release,
        "score": score,
        "signals": {
            "recency": recency,
            "availability": availability,
            "featured": featured,
            "verification": verification,
        },
        "verificationLevel": verification_level,
        "featured": bool(featured),
        "downloadReachable": (health or {}).get("downloadReachable")
        if isinstance((health or {}).get("downloadReachable"), bool)
        else None,
    }


def build_trending_doc(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any] | None,
    verification_doc: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build ``feeds/trending.json``.

    Three derived lists are returned in addition to the raw scores:

    * ``trending`` — top apps overall (all categories), sorted by score.
    * ``rising`` — apps with the strongest recent-update signal regardless of
      their overall score. This is "what just shipped" filtering.
    * ``recentlyUpdated`` — newest by release date, score-tie-broken by the
      trending score so older but well-loved apps still appear.
    """
    health_doc = health_doc or {}
    health_by_slug = {item.get("slug"): item for item in health_doc.get("apps", []) if isinstance(item, dict)}
    verification_by_slug = {
        item.get("app"): item for item in (verification_doc or {}).get("apps", []) if isinstance(item, dict)
    }

    scored: list[dict[str, Any]] = []
    for app in catalog.apps:
        health = health_by_slug.get(app.slug) or {}
        verification = verification_by_slug.get(app.slug) or {}
        scored.append(
            compute_trending(
                app,
                state,
                health,
                str(verification.get("status") or "UNVERIFIED"),
            )
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    trending = scored[:10]

    # Rising: order by the recency signal only.
    rising_sorted = sorted(
        scored,
        key=lambda item: (item["signals"]["recency"], item["score"]),
        reverse=True,
    )
    rising = rising_sorted[:10]

    # Recently updated: by release date (newest first); ties broken by score.
    recently = sorted(
        (item for item in scored if item["releaseDate"]),
        key=lambda item: (item["releaseDate"], item["score"]),
        reverse=True,
    )[:10]

    return {
        "schemaVersion": TRENDING_SCHEMA_VERSION,
        "generatedAt": today(),
        "count": len(scored),
        "formula": {
            "weights": {
                "recency": 0.4,
                "availability": 0.2,
                "featured": 0.2,
                "verification": 0.2,
            },
            "recencyFloorDays": RECENCY_FLOOR_DAYS,
        },
        "trending": trending,
        "rising": rising,
        "recentlyUpdated": recently,
        "all": scored,
    }
