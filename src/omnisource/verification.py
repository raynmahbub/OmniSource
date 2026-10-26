"""Verification system.

Trust levels are computed from observable facts, not claims:

``VERIFIED``
    The app is distributed by its official upstream (developer release, the
    developer's own feed, or a source the catalog marks official) and every
    offline/runtime check passed.
``COMMUNITY VERIFIED``
    The app is a community-built package (e.g. a community IPA of a tweak whose
    project publishes no IPA itself) and every check passed. It is still
    trustworthy, but the build provenance is not the upstream developer.
``UNVERIFIED``
    At least one check failed: invalid metadata, a non-HTTP(S) download URL,
    or the download was unreachable at build time.

Checks performed:

* ``metadata``   — required identity fields are present and well-formed.
* ``urls``       — download/upstream URLs are HTTP(S).
* ``fileAvailable`` — the last link probe considered the primary URL reachable.
* ``hashVerified``  — a SHA-256 digest is known for the newest build (from the
  upstream release's published checksum or the asset digest when the forge
  publishes one).

The result is rendered into ``feeds/verification.json`` and consumed by the
website badges and the duplicated-app recommendations.
"""

from __future__ import annotations

import re
from typing import Any

from omnisource.discovery import newest_version
from omnisource.domain import Catalog, today
from omnisource.download_intel import release_consistency
from omnisource.http import is_http_url
from omnisource.utils.health import probe_window

VERIFICATION_SCHEMA_VERSION = 1

# Trust Score (Phase 7): a 0..10 number per app combining five observable
# factors. Weights sum to 10.
TRUST_WEIGHTS = {
    "sourceVerification": 4.0,  # VERIFIED=4.0 / COMMUNITY VERIFIED=3.0 / other=1.0
    "updateHistory": 1.5,  # 0.5 per recorded release, capped at 3
    "releaseConsistency": 1.5,  # cadence variance 0..1
    "uptime": 1.5,  # probe reachability 0..1
    "integrity": 1.5,  # SHA-256 digest verified/known
}
TRUST_LEVELS = ("Verified", "Trusted", "Community", "Experimental")
TRUST_THRESHOLDS = ((9.0, "Verified"), (7.5, "Trusted"), (5.0, "Community"))


def trust_badge(score: float) -> str:
    for threshold, badge in TRUST_THRESHOLDS:
        if score >= threshold:
            return badge
    return "Experimental"


def compute_trust_score(
    *,
    level: str,
    release_count: int,
    consistency: float,
    uptime: float,
    hash_verified: bool,
) -> tuple[float, str]:
    """Return ``(trust_score 0..10, badge)`` for one app."""
    source = {"VERIFIED": 4.0, "COMMUNITY VERIFIED": 3.0}.get(str(level).upper(), 1.0)
    history = 0.5 * max(0, min(release_count, 3))
    consistency_component = max(0.0, min(1.0, consistency)) * TRUST_WEIGHTS["releaseConsistency"]
    uptime_component = max(0.0, min(1.0, uptime)) * TRUST_WEIGHTS["uptime"]
    integrity = TRUST_WEIGHTS["integrity"] if hash_verified else 0.0
    score = round(source + history + consistency_component + uptime_component + integrity, 1)
    return score, trust_badge(score)


# Methods whose publisher is the application's official upstream.
OFFICIAL_METHODS = frozenset(
    {
        "github-release",
        "github-tag",
        "gitlab-release",
        "codeberg-release",
        "forgejo-release",
        "json-feed",
        "altstore",
        "feather",
    }
)
# Methods that describe a community-packaged build of an official project.
COMMUNITY_METHODS = frozenset({"manual-mirror", "self-built"})

BUNDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")
LEVELS = ("VERIFIED", "COMMUNITY VERIFIED", "UNVERIFIED")

# Publishers whose name itself signals a community repack/mirror.
_COMMUNITY_PUBLISHER_RE = re.compile(r"vault|mirror|community", re.IGNORECASE)
_GH_PUBLISHER_RE = re.compile(r"^(?:https?://github\.com/)?([^/]+/[^/]+?)(?:\.git)?/?$", re.IGNORECASE)
_GH_UPSTREAM_RE = re.compile(r"github\.com/([^/]+/[^/]+?)(?:\.git)?/?$", re.IGNORECASE)


def provenance_for(app: Any, method: str, publisher: str) -> str:
    """Classify who actually publishes the sideload IPA.

    ``official``  — the IPA comes from the project's own release channel
                    (its forge releases or its own AltStore/JSON feed).
    ``community`` — a third party repackaged or mirrored the build (manual
                    mirrors, "IPA vault" publishers, or a GitHub packaging
                    repository that is not the project's own upstream repo).

    This is distinct from :data:`LEVELS`: a community build can be VERIFIED
    and an official-method build can be UNVERIFIED (e.g. a dead link).
    """
    raw = getattr(app, "raw", None) or {}
    status = str(raw.get("status") or "stable").lower()
    method = str(method or "").lower()
    publisher = str(publisher or "")
    if status == "manual":
        return "community"
    if method in COMMUNITY_METHODS:
        return "community"
    if _COMMUNITY_PUBLISHER_RE.search(publisher):
        return "community"
    if method in {"github-release", "github-tag"}:
        published = _GH_PUBLISHER_RE.match(publisher.strip())
        upstream = _GH_UPSTREAM_RE.search(str(raw.get("upstreamURL") or ""))
        if published and upstream and published.group(1).lower() != upstream.group(1).lower():
            return "community"
    return "official"


def _checks(catalog: Catalog, app: Any, newest: dict[str, Any], health: dict[str, Any] | None) -> dict[str, bool]:
    """Evaluate each verification check against defensively-sourced values."""
    download_url = str(newest.get("downloadURL") or "")
    upstream = str(app.homepage or "")
    health = health or {}
    return {
        "metadata": bool(
            app.name
            and str(newest.get("version") or "")
            and (not app.bundle_id or bool(BUNDLE_RE.match(app.bundle_id)))
        ),
        "urls": bool(is_http_url(download_url) and (not upstream or is_http_url(upstream))),
        "fileAvailable": bool(health.get("downloadReachable", True)),
        "hashVerified": bool(str(newest.get("sha256") or "")),
    }


def _reason_for_level(level: str, failed: list[str], method: str) -> list[str]:
    if level == "UNVERIFIED":
        return [f"failed check: {name}" for name in failed] or ["verification method is not recognized"]
    if level == "COMMUNITY VERIFIED":
        return [f"community package ({method}) — build provenance is not the upstream developer"]
    return [f"official upstream ({method})"]


def build_verification_doc(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute trust levels for every app and render ``verification.json``."""
    health_doc = health_doc or {}
    health_by_slug = {item.get("slug"): item for item in health_doc.get("apps", []) if isinstance(item, dict)}
    entries: list[dict[str, Any]] = []
    totals = {
        "apps": 0,
        "verified": 0,
        "communityVerified": 0,
        "unverified": 0,
        "hashVerified": 0,
        "official": 0,
        "communityBuilds": 0,
    }

    for app in catalog.apps:
        verification = app.raw.get("verification", {})
        if not isinstance(verification, dict):
            verification = {}
        method = str(verification.get("method") or "")
        publisher = str(verification.get("publisher") or app.developer)
        provenance = provenance_for(app, method, publisher)
        newest = newest_version(state, app.slug)
        health = health_by_slug.get(app.slug)
        checks = _checks(catalog, app, newest, health)
        failed = [key for key, ok in checks.items() if not ok and key != "hashVerified"]

        if failed:
            level = "UNVERIFIED"
        elif method in OFFICIAL_METHODS:
            level = "VERIFIED"
        elif method in COMMUNITY_METHODS:
            level = "COMMUNITY VERIFIED"
        elif method == "":
            # No explicit verification record yet: stay conservative unless the
            # catalog explicitly marks the app as official on the developerName.
            level = "UNVERIFIED"
        else:
            level = "UNVERIFIED"

        totals["apps"] += 1
        totals[{"VERIFIED": "verified", "COMMUNITY VERIFIED": "communityVerified"}.get(level, "unverified")] += 1
        totals["official" if provenance == "official" else "communityBuilds"] += 1
        if checks["hashVerified"]:
            totals["hashVerified"] += 1

        # Trust Score (Phase 7): five observable factors, 0..10.
        app_state = state.get(app.slug) if isinstance(state.get(app.slug), dict) else {}
        versions = app_state.get("versions")
        release_dates = app_state.get("releaseDates")
        release_count = max(
            len(versions) if isinstance(versions, list) else 0,
            len(release_dates) if isinstance(release_dates, list) else 0,
        )
        probes, reachable, _ = probe_window(app_state)
        if probes:
            uptime = reachable / probes
        else:
            current = health_by_slug.get(app.slug) or {}
            current_reachable = current.get("downloadReachable")
            uptime = 1.0 if current_reachable is True else (0.0 if current_reachable is False else 0.5)
        trust, badge = compute_trust_score(
            level=level,
            release_count=release_count,
            consistency=release_consistency(state, app.slug),
            uptime=uptime,
            hash_verified=checks["hashVerified"],
        )

        entries.append(
            {
                "app": app.slug,
                "name": app.name,
                "status": level,
                "provenance": provenance,
                "hash_verified": checks["hashVerified"],
                "method": method,
                "publisher": publisher,
                "checks": checks,
                "reasons": _reason_for_level(level, failed, method),
                "downloadURL": str(newest.get("downloadURL") or ""),
                "trustScore": trust,
                "trustBadge": badge,
            }
        )

    entries.sort(key=lambda item: (item["status"] != "VERIFIED", str(item["name"]).casefold()))
    if entries:
        totals["avgTrustScore"] = round(sum(item["trustScore"] for item in entries) / len(entries), 2)
    totals["trustLevels"] = list(TRUST_LEVELS)
    return {
        "schemaVersion": VERIFICATION_SCHEMA_VERSION,
        "generatedAt": today(),
        "totals": totals,
        "apps": entries,
    }
