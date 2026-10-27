"""Release integrity engine (Phase 3).

Two complementary layers:

1. **Metadata verification** (every build, offline).
   For every app's newest asset the report records the contract fields

       {"sha256": str | null, "size": int, "releaseId": str, "source": str}

   and evaluates the reject rules that can be decided without downloading:

   * ``zeroBytes``     — upstream reported size 0 (corrupted / empty asset)
   * ``missingIPA``    — the primary download is not an installable IPA
   * ``badDigest``     — a sha256 is recorded but is not a 64-char hex digest

   A digest *mismatch* can only be proven by downloading, so it is decided by
   layer 2 whenever an expected digest is known.

2. **Full verification** (optional, ``--verify-downloads`` / weekly
   ``verify.yml``). Streams each IPA to disk-free memory (chunked SHA-256),
   checks the byte count and digest, and records the outcome in
   ``state.json`` (``lastFullVerification``) so the next metadata report can
   also reflect real download results.

The document is rendered as ``feeds/integrity_report.json`` and fails the
offline validator when a hard reject rule fires, so a zero-byte or missing
IPA can never reach a published feed unmarked.
"""

from __future__ import annotations

import hashlib
import tempfile
import time
from typing import Any, BinaryIO

from omnisource.constants import INSTALLABLE_SUFFIXES
from omnisource.discovery import newest_version
from omnisource.domain import Catalog, today
from omnisource.ipa import inspect_ipa
from omnisource.logutil import log

INTEGRITY_SCHEMA_VERSION = 1

# Reject-rule severities.
HARD = "fail"
SOFT = "warn"
OK = "pass"

# .tipa is a renamed .ipa (TrollStore); both are installable downloads.
SHA256_HEX_LEN = 64


def _digest_ok(value: Any) -> bool:
    return isinstance(value, str) and len(value) == SHA256_HEX_LEN and all(c in "0123456789abcdefABCDEF" for c in value)


def _is_ipa(url: str) -> bool:
    return url.split("?", 1)[0].lower().endswith(INSTALLABLE_SUFFIXES)


def metadata_checks(app: Any, newest: dict[str, Any], health: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate the offline reject rules for one app's newest asset."""
    url = str(newest.get("downloadURL") or "")
    size = newest.get("size")
    size = int(size) if isinstance(size, (int, float)) and not isinstance(size, bool) else 0
    sha = newest.get("sha256")
    sha = str(sha) if sha else None

    checks = {
        "sizePositive": size > 0,
        "installable": _is_ipa(url),
        "digestFormat": True if sha is None else _digest_ok(sha),
        "reachable": (health or {}).get("downloadReachable")
        if isinstance((health or {}).get("downloadReachable"), bool)
        else None,
    }
    status = OK
    if not (checks["sizePositive"] and checks["installable"] and checks["digestFormat"]):
        status = HARD
    elif sha is None:
        # Missing digest is not a corruption signal (many upstreams publish
        # none); it keeps the soft "warn" band so reports stay actionable.
        status = SOFT
    return {"checks": checks, "status": status}


def current_full_verification(newest: dict[str, Any], app_state: dict[str, Any]) -> dict[str, Any] | None:
    """Return a full-verification record only when it identifies this asset.

    New records include the probed URL. Older records without a URL remain in
    state as historical data, but cannot establish a current-asset verdict.
    A verdict for a previous release must never approve or reject a new one.
    """
    full = app_state.get("lastFullVerification")
    if not isinstance(full, dict) or not full.get("at"):
        return None
    url = str(newest.get("downloadURL") or "")
    recorded_url = str(full.get("url") or "")
    digest = str(newest.get("sha256") or "").lower()
    expected = str(full.get("expectedSha256") or "").lower()
    if not recorded_url or not url or recorded_url != url:
        return None
    if expected and digest and expected != digest:
        return None
    expected_size = full.get("expectedSize")
    current_size = newest.get("size")
    if expected_size and current_size and expected_size != current_size:
        return None
    return full


def digest_evidence(newest: dict[str, Any], app_state: dict[str, Any]) -> dict[str, Any]:
    """Describe recorded versus byte-compared SHA-256 without guessing origin."""
    digest = str(newest.get("sha256") or "").lower()
    recorded = _digest_ok(digest)
    full = current_full_verification(newest, app_state)
    actual = str(full.get("sha256") or "").lower() if full else ""
    matched = bool(
        recorded
        and full
        and full.get("ok") is True
        and str(full.get("expectedSha256") or "").lower() == digest
        and actual == digest
    )
    mismatch = bool(
        recorded
        and full
        and full.get("ok") is False
        and "sha256 mismatch" in str(full.get("detail") or "").lower()
        and str(full.get("expectedSha256") or "").lower() == digest
        and _digest_ok(actual)
        and actual != digest
    )
    return {
        "status": "mismatch" if mismatch else "matched" if matched else "recorded" if recorded else "unavailable",
        "checkedAt": str(full.get("at") or "") if (matched or mismatch) and full else "",
        # A catalog digest may originate from a forge, feed, or a previous
        # download. Its publisher origin is not established by its presence.
        "origin": "unconfirmed",
    }


def asset_record(app: Any, newest: dict[str, Any]) -> dict[str, Any]:
    """The stored per-asset integrity record (Phase 3 contract)."""
    return {
        "sha256": str(newest["sha256"]) if newest.get("sha256") else None,
        "size": int(newest.get("size") or 0),
        "releaseId": str(newest.get("version") or ""),
        "source": str(newest.get("source") or ""),
        "downloadUrl": str(newest.get("downloadURL") or ""),
    }


def build_integrity_doc(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render ``feeds/integrity_report.json`` from pipeline state."""
    health_doc = health_doc or {}
    health_by_slug = {item.get("slug"): item for item in health_doc.get("apps", []) if isinstance(item, dict)}

    entries: list[dict[str, Any]] = []
    for app in catalog.apps:
        newest = newest_version(state, app.slug)
        if not newest:
            continue
        result = metadata_checks(app, newest, health_by_slug.get(app.slug))
        app_state = state.get(app.slug) if isinstance(state.get(app.slug), dict) else {}
        full = current_full_verification(newest, app_state)
        if full:
            result["fullVerification"] = full
            if full.get("ok") is False:
                detail = str(full.get("detail") or "").lower()
                # A timeout or rate limit is an availability warning, not
                # proof that a binary is corrupt. Actual mismatches still gate.
                if "mismatch" in detail or "not an ipa" in detail or "zero bytes" in detail:
                    result["status"] = HARD
                    result["checks"]["corruptedDownload"] = False
                elif result["status"] == OK:
                    result["status"] = SOFT
        entries.append(
            {
                "slug": app.slug,
                "name": app.name,
                "asset": asset_record(app, newest),
                "digestEvidence": digest_evidence(newest, app_state),
                **result,
            }
        )

    totals = {
        "apps": len(entries),
        "pass": sum(1 for e in entries if e["status"] == OK),
        "warn": sum(1 for e in entries if e["status"] == SOFT),
        "fail": sum(1 for e in entries if e["status"] == HARD),
    }
    totals["rejected"] = totals["fail"]
    rejected = [
        {
            "slug": entry["slug"],
            "reasons": [name for name, ok in entry["checks"].items() if not ok],
        }
        for entry in entries
        if entry["status"] == HARD
    ]
    entries.sort(key=lambda entry: (entry["status"] != HARD, entry["slug"]))
    return {
        "schemaVersion": INTEGRITY_SCHEMA_VERSION,
        "generatedAt": today(),
        "totals": totals,
        "rejected": rejected,
        "apps": entries,
    }


def integrity_errors(doc: dict[str, Any]) -> list[str]:
    """Validator-facing hard failures from an integrity report."""
    problems: list[str] = []
    for item in doc.get("rejected", []):
        if not isinstance(item, dict):
            continue
        problems.append(f"integrity: {item.get('slug')} rejected ({', '.join(item.get('reasons', []))})")
    return problems


# ---------------------------------------------------------------------------
# Full download verification (streaming; memory-safe for large IPAs)
# ---------------------------------------------------------------------------


MAX_INSPECTION_BYTES = 1536 * 1024 * 1024


def stream_hashes(
    http: Any,
    url: str,
    *,
    timeout: float = 300.0,
    spool: BinaryIO | None = None,
    spool_limit: int = MAX_INSPECTION_BYTES,
) -> dict[str, Any]:
    """Download ``url`` in chunks and return byte count, SHA-256, and SHA-512.

    The stream is never retained in memory. An optional temporary-file spool
    stops at a hard limit without interrupting hashing. Raises on transport
    failure or a zero-byte body so callers cannot publish a partial verdict.
    """
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()
    total = 0
    spooled = spool is not None
    content_length: int | None = None
    with http.open_stream(url, timeout=timeout) as response:
        headers = getattr(response, "headers", None)
        raw_length = headers.get("Content-Length") if headers is not None else None
        if isinstance(raw_length, str) and raw_length.isdigit():
            content_length = int(raw_length)
        while True:
            data = response.read(1024 * 1024)
            if not data:
                break
            sha256.update(data)
            sha512.update(data)
            total += len(data)
            if spool is not None and spooled:
                if total <= spool_limit:
                    spool.write(data)
                else:
                    spool.seek(0)
                    spool.truncate()
                    spooled = False
    if total == 0:
        raise OSError("downloaded asset is zero bytes")
    if content_length is not None and total != content_length:
        # HTTPResponse.read(n) can return EOF without raising IncompleteRead.
        # A truncated transfer is not a complete transparency observation.
        raise OSError(f"incomplete download: received {total} of {content_length} bytes")
    return {"bytes": total, "sha256": sha256.hexdigest(), "sha512": sha512.hexdigest(), "spooled": spooled}


def stream_sha256(http: Any, url: str, *, timeout: float = 300.0) -> tuple[int, str]:
    """Backward-compatible SHA-256-only view of :func:`stream_hashes`."""
    result = stream_hashes(http, url, timeout=timeout)
    return int(result["bytes"]), str(result["sha256"])


def verify_downloads(
    container: Any,
    catalog: Catalog,
    state: dict[str, Any],
    *,
    only: set[str] | None = None,
    workers: int = 4,
    inspect: bool = False,
) -> list[dict[str, Any]]:
    """Stream-download and hash every selected app's newest asset.

    Results are written to ``state[slug]["lastFullVerification"]`` so the next
    metadata report (and the status board) reflects real download outcomes.
    A failing app never mutates its version state — only the verification
    record changes.
    """
    import concurrent.futures

    selected = [app for app in catalog.apps if not only or app.slug in only]
    results: list[dict[str, Any]] = []

    def _verify(app: Any) -> dict[str, Any]:
        newest = newest_version(state, app.slug)
        url = str(newest.get("downloadURL") or "")
        expected_sha = newest.get("sha256")
        expected_sha512 = newest.get("sha512")
        expected_size = newest.get("size")
        started = time.monotonic()
        record: dict[str, Any] = {
            "slug": app.slug,
            "url": url,
            "expectedSha256": str(expected_sha) if expected_sha else None,
            "expectedSha512": str(expected_sha512) if expected_sha512 else None,
            "expectedSize": int(expected_size) if isinstance(expected_size, (int, float)) else None,
        }
        try:
            timeout = max(60.0, float(container.settings.health_timeout) * 10)
            if inspect and url.split("?", 1)[0].lower().endswith((".ipa", ".tipa")):
                with tempfile.TemporaryFile() as spool:
                    hashes = stream_hashes(container.http, url, timeout=timeout, spool=spool)
                    if hashes["spooled"]:
                        try:
                            record["ipaInspection"] = inspect_ipa(spool, app.bundle_id)
                        except ValueError as error:
                            record["ipaInspection"] = {"status": "unavailable", "detail": str(error)}
                    else:
                        record["ipaInspection"] = {"status": "unavailable", "detail": "inspection size limit exceeded"}
            else:
                hashes = stream_hashes(container.http, url, timeout=timeout)
            size, sha = int(hashes["bytes"]), str(hashes["sha256"])
            record["size"] = size
            record["sha256"] = sha
            record["sha512"] = str(hashes["sha512"])
            problems = []
            if expected_sha and str(expected_sha).lower() != sha.lower():
                problems.append("sha256 mismatch")
            if expected_sha512 and str(expected_sha512).lower() != str(hashes["sha512"]).lower():
                problems.append("sha512 mismatch")
            if expected_size and int(expected_size) != size:
                problems.append("size mismatch")
            if not _is_ipa(url):
                problems.append("not an IPA")
            inspection = record.get("ipaInspection")
            if isinstance(inspection, dict) and inspection.get("status") == "mismatch":
                problems.append("bundle ID mismatch")
            record["ok"] = not problems
            record["detail"] = "; ".join(problems) or "ok"
        except Exception as error:  # network/IO failures are per-app results
            record["ok"] = False
            record["detail"] = f"verification unavailable: {error}"
        record["at"] = today()
        record["durationMs"] = int((time.monotonic() - started) * 1000)
        return record

    max_workers = max(1, min(workers, len(selected))) if selected else 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        for record in pool.map(_verify, selected):
            results.append(record)
            status = "ok" if record["ok"] else "FAIL"
            log.info(
                "%-14s full verify %s: %s (%d ms)",
                record["slug"],
                status,
                record.get("detail"),
                record.get("durationMs", 0),
            )
            entry = state.setdefault(record["slug"], {})
            # Keep the asset URL with the verdict; otherwise a later release
            # can inherit a successful (or failed) check for different bytes.
            entry["lastFullVerification"] = {key: value for key, value in record.items() if key != "slug"}
            inspection = record.get("ipaInspection")
            newest = newest_version(state, record["slug"])
            previous_inspection = newest.get("ipaInspection")
            if (
                isinstance(previous_inspection, dict)
                and record.get("sha256")
                and (
                    previous_inspection.get("sha256") != record["sha256"]
                    or (isinstance(inspection, dict) and inspection.get("status") == "mismatch")
                )
            ):
                # A replaced or differently identified binary cannot inherit
                # the prior build's inspected permission declarations.
                newest.pop("ipaInspection", None)
            if (
                record.get("ok") is True
                and isinstance(inspection, dict)
                and inspection.get("status") == "match"
                and newest.get("downloadURL") == record.get("url")
            ):
                permissions: dict[str, Any] = {"privacy": inspection.get("privacyUsageDescriptions", {})}
                if isinstance(inspection.get("declaredEntitlements"), list):
                    permissions["entitlements"] = inspection["declaredEntitlements"]
                newest["ipaInspection"] = {
                    "at": record["at"],
                    "sha256": record["sha256"],
                    "url": record["url"],
                    "bundleIdentifier": inspection["bundleIdentifier"],
                    "minOSVersion": inspection.get("minOSVersion", ""),
                    "appPermissions": permissions,
                    "note": "Packaged declarations only; entitlements are not code-signature verified.",
                }

    return results
