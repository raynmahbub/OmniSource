"""Verification and source-attribution metadata.

The legacy verification levels summarize catalog declarations, metadata, and
last-known link availability. They do not establish that an IPA is safe or
signed by its developer. Provenance is a separate official/community/unknown
classification, and digest evidence distinguishes a recorded checksum from a
successful comparison against downloaded bytes.
"""

from __future__ import annotations

import re
from typing import Any

from omnisource.discovery import newest_version
from omnisource.domain import Catalog, today
from omnisource.download_intel import release_consistency
from omnisource.http import is_http_url
from omnisource.integrity import current_full_verification, digest_evidence
from omnisource.transparency import evidence_for_current
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
    badge = trust_badge(score)
    # A numerical score must not turn an independently sourced community or
    # unverified build into an apparently official "Verified" badge.
    if badge == "Verified" and str(level).upper() != "VERIFIED":
        badge = "Trusted" if str(level).upper() == "COMMUNITY VERIFIED" else "Experimental"
    return score, badge


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
    """Classify the *declared* IPA source as official, community or unknown.

    Explicit reviewed catalog attribution wins. Legacy declarations are
    classified conservatively using the publishing method, publisher and
    project URL; merely having an ``upstream`` does not establish ownership.
    This is not independent binary or signature verification.
    """
    raw = app if isinstance(app, dict) else (getattr(app, "raw", None) or {})
    verification = raw.get("verification") if isinstance(raw.get("verification"), dict) else {}
    explicit = verification.get("provenance")
    if explicit is not None:
        value = str(explicit).strip().lower()
        return value if value in {"official", "community", "unknown"} else "unknown"
    status = str(raw.get("status") or "stable").lower()
    method = str(method or "").strip().lower()
    publisher = str(publisher or "").strip()
    build = str(raw.get("build") or verification.get("build") or "")
    if status == "manual" or method in COMMUNITY_METHODS or _COMMUNITY_PUBLISHER_RE.search(f"{publisher} {build}"):
        return "community"
    if method in {"github-release", "github-tag"}:
        published = _GH_PUBLISHER_RE.match(publisher)
        upstream = _GH_UPSTREAM_RE.search(str(raw.get("upstreamURL") or ""))
        if published and upstream and published.group(1).lower() != upstream.group(1).lower():
            return "community"
    if method in OFFICIAL_METHODS and publisher:
        return "official"
    return "unknown"


def _checks(
    catalog: Catalog,
    app: Any,
    newest: dict[str, Any],
    health: dict[str, Any] | None,
    evidence: dict[str, Any],
) -> dict[str, bool]:
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
        "fileAvailable": health.get("downloadReachable") is True,
        "hashVerified": evidence.get("status") == "matched",
    }


def _reason_for_level(level: str, failed: list[str], method: str) -> list[str]:
    if level == "UNVERIFIED":
        return [f"failed or unknown check: {name}" for name in failed] or ["source provenance is unknown"]
    if level == "COMMUNITY VERIFIED":
        return [f"catalog lists a community source ({method}); the project and IPA publisher may differ"]
    return [f"catalog attributes the source to the project's release channel ({method})"]


def build_verification_doc(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any] | None = None,
    transparency_log: dict[str, Any] | None = None,
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
        "hashRecorded": 0,
        "official": 0,
        "communityBuilds": 0,
        "unknownProvenance": 0,
    }

    for app in catalog.apps:
        verification = app.raw.get("verification", {})
        if not isinstance(verification, dict):
            verification = {}
        method = str(verification.get("method") or "")
        declared_publisher = str(verification.get("publisher") or "")
        publisher = declared_publisher or app.developer
        provenance = provenance_for(app, method, declared_publisher)
        newest = newest_version(state, app.slug)
        app_state = state.get(app.slug) if isinstance(state.get(app.slug), dict) else {}
        evidence = digest_evidence(newest, app_state)
        health = health_by_slug.get(app.slug)
        checks = _checks(catalog, app, newest, health, evidence)
        failed = [key for key, ok in checks.items() if not ok and key != "hashVerified"]
        full = current_full_verification(newest, app_state)
        detail = str(full.get("detail") or "") if full else ""
        mismatch = bool(
            full
            and full.get("ok") is False
            and any(
                text in detail.lower()
                for text in ("sha256 mismatch", "sha512 mismatch", "size mismatch", "bundle id mismatch")
            )
        )
        if mismatch:
            failed.append("integrity mismatch")

        if failed or provenance == "unknown":
            level = "UNVERIFIED"
        elif provenance == "community":
            level = "COMMUNITY VERIFIED"
        elif method in OFFICIAL_METHODS:
            level = "VERIFIED"
        else:
            level = "UNVERIFIED"

        totals["apps"] += 1
        totals[{"VERIFIED": "verified", "COMMUNITY VERIFIED": "communityVerified"}.get(level, "unverified")] += 1
        totals[
            {"official": "official", "community": "communityBuilds", "unknown": "unknownProvenance"}[provenance]
        ] += 1
        if evidence["status"] in {"recorded", "matched", "mismatch"}:
            totals["hashRecorded"] += 1
        if checks["hashVerified"]:
            totals["hashVerified"] += 1

        # Trust Score (Phase 7): five observable factors, 0..10.
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
                "digestEvidence": evidence,
                "transparencyEvidence": evidence_for_current(transparency_log or {}, app.slug, newest),
                "integrityFailure": {"detail": detail, "checkedAt": str(full.get("at") or "")}
                if mismatch and full
                else None,
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
