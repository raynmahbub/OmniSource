"""Security posture engine: hashes, binaries, downloads, provenance.

Builds ``data/security.json`` — the machine-readable security report every
release is gated on (``security.yml`` fails the pipeline when a *critical*
finding appears):

* SHA-256 / SHA-512 format and coverage checks for recorded digests;
* optional byte comparison against recorded digests (not proof of authorship);
* duplicate-binary detection (the same digest shipping under two bundle IDs
  is either a rebrand or a trojan — both deserve a human look);
* download-integrity rollup from the latest health probes;
* provenance audit (official upstream vs community build vs unknown).

Offline: all signals come from ``feeds/state.json``, ``feeds/apps.json``
and the latest health / status documents. Nothing here downloads binaries.
"""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omnisource.integrity import stream_sha256
from omnisource.verification import provenance_for

SECURITY_SCHEMA_VERSION = 1

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA512_RE = re.compile(r"^[0-9a-f]{128}$")


def utcnow() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _digests(entry: dict[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    for field, pattern in (
        ("sha256", SHA256_RE),
        ("digest", SHA256_RE),
        ("sha512", SHA512_RE),
    ):
        raw = entry.get(field)
        if isinstance(raw, str) and raw.strip():
            value = raw.strip().lower().removeprefix("sha256:").removeprefix("sha512:")
            if pattern.match(value):
                found["sha512" if field == "sha512" else "sha256"] = value
            else:
                found[f"{field}_invalid"] = raw.strip()[:128]
    text = str(entry.get("localizedDescription", ""))
    match = re.search(r"\b[0-9a-f]{64}\b", text.lower())
    if match and "sha256" not in found:
        found["sha256_changelog"] = match.group(0)
    return found


def verify_hashes(apps: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit SHA-256 / SHA-512 coverage across the newest versions."""
    report: dict[str, Any] = {
        "apps": 0,
        "sha256": 0,
        "sha512": 0,
        "missing": [],
        "invalid": [],
    }
    for app in apps:
        if not isinstance(app, dict):
            continue
        report["apps"] += 1
        slug = str(app.get("slug") or app.get("id") or app.get("name") or "?")
        versions = app.get("versions")
        newest = versions[0] if isinstance(versions, list) and versions else app
        if not isinstance(newest, dict):
            report["missing"].append(slug)
            continue
        digests = _digests(newest)
        if "sha256" in digests or "sha256_changelog" in digests:
            report["sha256"] += 1
        else:
            report["missing"].append(slug)
        if "sha512" in digests:
            report["sha512"] += 1
        if any(key.endswith("_invalid") for key in digests):
            report["invalid"].append(slug)
    report["missing"] = sorted(report["missing"])
    report["invalid"] = sorted(report["invalid"])
    return report


def find_duplicate_binaries(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find digests shared by two or more distinct bundle identifiers."""
    owners: dict[str, set[str]] = {}
    for app in apps:
        if not isinstance(app, dict):
            continue
        bundle = str(app.get("bundleIdentifier", ""))
        versions = app.get("versions")
        newest = versions[0] if isinstance(versions, list) and versions else app
        if not isinstance(newest, dict):
            continue
        digest = _digests(newest).get("sha256", "")
        if bundle and digest:
            owners.setdefault(digest, set()).add(bundle)
    dupes = [{"sha256": digest, "bundles": sorted(bundles)} for digest, bundles in owners.items() if len(bundles) > 1]
    return sorted(dupes, key=lambda item: (-len(item["bundles"]), item["sha256"]))


def download_integrity(
    apps: list[dict[str, Any]],
    health: dict[str, Any] | None,
) -> dict[str, Any]:
    """Roll health probes into reachable / failing / unknown buckets."""
    health = health if isinstance(health, dict) else {}
    nodes = health.get("downloads", health.get("apps", health.get("sources", [])))
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                key = str(node.get("slug") or node.get("id") or node.get("app") or "")
                if key:
                    by_id[key] = node
    elif isinstance(nodes, dict):
        by_id = {str(key): {"reachable": value} for key, value in nodes.items()}
    integrity: dict[str, Any] = {"reachable": [], "failing": [], "unknown": []}
    for app in apps:
        if not isinstance(app, dict):
            continue
        omni = app.get("omnisource") if isinstance(app.get("omnisource"), dict) else {}
        slug = str(app.get("slug") or omni.get("slug") or app.get("id") or app.get("name") or "")
        node = next(
            (
                by_id[key]
                for key in (slug, str(app.get("name") or ""), str(app.get("bundleIdentifier") or ""))
                if key in by_id
            ),
            {},
        )
        # A probe for an older release is not evidence about the current URL.
        if node.get("url") and node.get("url") != app.get("downloadURL"):
            node = {}
        value = next((node[key] for key in ("downloadReachable", "reachable", "ok") if key in node), None)
        status = str(value if value is not None else node.get("status") or node.get("health") or "unknown").lower()
        if status in ("healthy", "online", "reachable", "ok", "true"):
            integrity["reachable"].append(slug)
        elif status in ("unavailable", "offline", "failing", "failed", "false"):
            integrity["failing"].append(slug)
        else:
            integrity["unknown"].append(slug)
    for key in integrity:
        integrity[key] = sorted(integrity[key])
    return integrity


def provenance_audit(catalog_apps: list[dict[str, Any]]) -> dict[str, Any]:
    """Count official vs community vs unknown provenance declarations."""
    audit: dict[str, Any] = {"official": 0, "community": 0, "unknown": [], "total": 0}
    for app in catalog_apps:
        if not isinstance(app, dict):
            continue
        audit["total"] += 1
        verification = app.get("verification")
        method = str(verification.get("method") or "") if isinstance(verification, dict) else ""
        publisher = str(verification.get("publisher") or "") if isinstance(verification, dict) else ""
        provenance = provenance_for(app, method, publisher)
        if provenance == "unknown":
            audit["unknown"].append(str(app.get("slug") or app.get("name") or "?"))
        else:
            audit[provenance] += 1
    audit["unknown"] = sorted(audit["unknown"])
    return audit


def hash_file(path: Path, *, chunk_size: int = 1024 * 1024) -> dict[str, Any]:
    """Compute SHA-256 and SHA-512 for a local binary without loading it all."""
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()
    total = 0
    with Path(path).open("rb") as handle:
        while chunk := handle.read(max(1, chunk_size)):
            sha256.update(chunk)
            sha512.update(chunk)
            total += len(chunk)
    return {"bytes": total, "sha256": sha256.hexdigest(), "sha512": sha512.hexdigest()}


def verify_file(path: Path, *, sha256: str = "", sha512: str = "", expected_size: int | None = None) -> dict[str, Any]:
    """Verify a local downloaded asset against published digest/size metadata."""
    try:
        actual = hash_file(path)
    except OSError as error:
        return {"ok": False, "kind": "unavailable", "detail": str(error), "path": str(path)}
    problems: list[str] = []
    if expected_size is not None and actual["bytes"] != int(expected_size):
        problems.append("size mismatch")
    if sha256 and actual["sha256"].casefold() != str(sha256).removeprefix("sha256:").casefold():
        problems.append("sha256 mismatch")
    if sha512 and actual["sha512"].casefold() != str(sha512).removeprefix("sha512:").casefold():
        problems.append("sha512 mismatch")
    return {
        **actual,
        "ok": not problems,
        "kind": "mismatch" if problems else "checked",
        "detail": "; ".join(problems) or "ok",
        "path": str(path),
    }


def verify_url(
    url: str,
    *,
    sha256: str = "",
    sha512: str = "",
    expected_size: int | None = None,
    timeout: float = 300.0,
    max_bytes: int = 512 * 1024 * 1024,
    http_stream: Any | None = None,
) -> dict[str, Any]:
    """Stream an HTTPS asset and verify published size/digests.

    This opt-in operation is used by the weekly security job, not by normal
    metadata builds.  It follows redirects through urllib but never attaches
    API credentials, caps the body size, and computes both modern hashes.
    """
    if not isinstance(url, str) or not url.startswith("https://"):
        return {"ok": False, "kind": "unavailable", "detail": "asset URL must be HTTPS", "url": url}
    if http_stream is not None:
        try:
            total, digest = stream_sha256(http_stream, url, timeout=timeout)
        except (OSError, TimeoutError, ValueError) as error:
            return {"ok": False, "kind": "unavailable", "detail": str(error), "url": url}
        problems: list[str] = []
        if expected_size is not None and total != int(expected_size):
            problems.append("size mismatch")
        if sha256 and digest.casefold() != str(sha256).removeprefix("sha256:").casefold():
            problems.append("sha256 mismatch")
        return {
            "ok": not problems,
            "kind": "mismatch" if problems else "checked",
            "detail": "; ".join(problems) or "ok",
            "url": url,
            "bytes": total,
            "sha256": digest,
        }
    sha_a = hashlib.sha256()
    sha_b = hashlib.sha512()
    total = 0
    request = urllib.request.Request(url, headers={"User-Agent": "OmniSource-Security/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    return {
                        "ok": False,
                        "kind": "unavailable",
                        "detail": f"asset exceeds {max_bytes} bytes",
                        "url": url,
                    }
                sha_a.update(chunk)
                sha_b.update(chunk)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as error:
        return {"ok": False, "kind": "unavailable", "detail": str(error), "url": url}
    problems: list[str] = []
    if expected_size is not None and total != int(expected_size):
        problems.append("size mismatch")
    if sha256 and sha_a.hexdigest().casefold() != str(sha256).removeprefix("sha256:").casefold():
        problems.append("sha256 mismatch")
    if sha512 and sha_b.hexdigest().casefold() != str(sha512).removeprefix("sha512:").casefold():
        problems.append("sha512 mismatch")
    return {
        "ok": not problems,
        "kind": "mismatch" if problems else "checked",
        "detail": "; ".join(problems) or "ok",
        "url": url,
        "bytes": total,
        "sha256": sha_a.hexdigest(),
        "sha512": sha_b.hexdigest(),
    }


def build_security_report(
    *,
    apps: list[dict[str, Any]],
    catalog_apps: list[dict[str, Any]] | None = None,
    health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``data/security.json`` document and its findings."""
    hashes = verify_hashes(apps)
    duplicates = find_duplicate_binaries(apps)
    downloads = download_integrity(apps, health)
    snapshot_at = ""
    if isinstance(health, dict):
        if isinstance(health.get("downloads"), list):
            snapshot_at = str(health.get("generatedAt") or "")
        elif isinstance(health.get("apps"), list):
            snapshot_at = max(
                (str(item.get("lastCheckedAt") or "") for item in health["apps"] if isinstance(item, dict)),
                default="",
            )
    provenance = provenance_audit(catalog_apps if catalog_apps is not None else apps)
    findings: list[dict[str, Any]] = []
    for slug in hashes["invalid"]:
        findings.append(
            {"severity": "critical", "check": "hash-format", "id": slug, "detail": "recorded digest is malformed"}
        )
    for dupe in duplicates:
        findings.append(
            {
                "severity": "high",
                "check": "duplicate-binary",
                "id": ",".join(dupe["bundles"]),
                "detail": f"digest {dupe['sha256'][:16]}… ships under {len(dupe['bundles'])} bundle IDs",
            }
        )
    for slug in downloads["failing"]:
        findings.append(
            {
                "severity": "medium",
                "check": "download-unreachable",
                "id": slug,
                "detail": "last recorded health probe could not reach the download; a retry may succeed",
            }
        )
    for slug in hashes["missing"]:
        findings.append(
            {
                "severity": "low",
                "check": "hash-missing",
                "id": slug,
                "detail": "no SHA-256 recorded for the newest version",
            }
        )
    critical = sum(1 for item in findings if item["severity"] == "critical")
    return {
        "schemaVersion": SECURITY_SCHEMA_VERSION,
        "generatedAt": utcnow(),
        "verdict": "fail" if critical else "pass",
        "summary": {
            "apps": hashes["apps"],
            "sha256": hashes["sha256"],
            "sha512": hashes["sha512"],
            "hashesMissing": len(hashes["missing"]),
            "hashesInvalid": len(hashes["invalid"]),
            "duplicateBinaries": len(duplicates),
            "downloadsFailing": len(downloads["failing"]),
            "downloadsUnknown": len(downloads["unknown"]),
            "provenanceOfficial": provenance["official"],
            "provenanceCommunity": provenance["community"],
            "provenanceUnknown": len(provenance["unknown"]),
        },
        "downloadSnapshotAt": snapshot_at,
        "hashes": hashes,
        "duplicateBinaries": duplicates,
        "downloads": downloads,
        "provenance": provenance,
        "findings": findings,
    }
