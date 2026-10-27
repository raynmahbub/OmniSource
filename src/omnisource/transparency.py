"""Append-only, hash-chained record of *observed* download bytes.

The hash chain can be checked against a previously saved head; without an
external checkpoint it cannot prevent a complete rewrite or truncation. It is
not a publisher signature or a safety guarantee. An unchanged version/size
can be swapped between incremental checks; a full recheck is needed to see it.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ZERO = "0" * 64
HEX = re.compile(r"^[0-9a-f]{64}$")


def _digest(record: dict[str, Any]) -> str:
    payload = json.dumps(
        {k: v for k, v in record.items() if k != "entryHash"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_log(doc: dict[str, Any]) -> None:
    entries = doc.get("entries")
    if not isinstance(entries, list):
        raise ValueError("transparency log has no entries array")
    previous = ZERO
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or entry.get("seq") != index or entry.get("prev") != previous:
            raise ValueError(f"broken transparency chain at entry {index}")
        if entry.get("entryHash") != _digest(entry):
            raise ValueError(f"invalid transparency hash at entry {index}")
        previous = entry["entryHash"]
    if doc.get("schemaVersion") != 1 or doc.get("count") != len(entries) or doc.get("head") != previous:
        raise ValueError("invalid transparency log schema, count or head")


def append_observations(doc: dict[str, Any], state: dict[str, Any], results: list[dict[str, Any]]) -> int:
    """Append distinct complete byte observations; never log a failed fetch."""
    validate_log(doc)
    entries = doc["entries"]
    keys = {(e.get("slug"), e.get("version"), e.get("url"), e.get("size"), e.get("sha256")) for e in entries}
    count = 0
    for result in sorted(results, key=lambda x: str(x.get("slug") or "")):
        slug = str(result.get("slug") or "")
        node = state.get(slug)
        versions = node.get("versions", []) if isinstance(node, dict) else []
        newest = versions[0] if versions and isinstance(versions[0], dict) else {}
        sha = str(result.get("sha256") or "").lower()
        url = str(result.get("url") or "")
        size = result.get("size")
        at = str(result.get("at") or "")
        version = str(newest.get("version") or "")
        if not slug or not version or not at or not HEX.fullmatch(sha) or not isinstance(size, int) or size <= 0:
            continue
        if not url.startswith("https://") or url != newest.get("downloadURL"):
            continue
        key = (slug, version, url, size, sha)
        if key in keys:
            continue
        different = any(
            e.get("slug") == slug and e.get("version") == version and e.get("sha256") != sha for e in entries
        )
        entry = {
            "seq": len(entries) + 1,
            "prev": entries[-1]["entryHash"] if entries else ZERO,
            "slug": slug,
            "version": version,
            "url": url,
            "size": size,
            "sha256": sha,
            "verifiedAt": at,
            "matchesRecorded": result.get("ok") is True and str(result.get("expectedSha256") or "").lower() == sha,
            "sameVersionDifferentDigest": different,
        }
        entry["entryHash"] = _digest(entry)
        entries.append(entry)
        keys.add(key)
        count += 1
    doc["count"] = len(entries)
    doc["head"] = entries[-1]["entryHash"] if entries else ZERO
    return count


def changed_slugs(doc: dict[str, Any], state: dict[str, Any], slugs: set[str]) -> set[str]:
    """Select assets without a matching successful recorded observation."""
    validate_log(doc)
    latest: dict[str, dict[str, Any]] = {}
    for entry in doc["entries"]:
        latest[str(entry.get("slug") or "")] = entry
    changed: set[str] = set()
    for slug in slugs:
        node = state.get(slug)
        versions = node.get("versions", []) if isinstance(node, dict) else []
        current = versions[0] if versions and isinstance(versions[0], dict) else {}
        old = latest.get(slug, {})
        expected = str(current.get("sha256") or "").lower()
        if (
            not current
            or not old
            or old.get("version") != current.get("version")
            or old.get("url") != current.get("downloadURL")
            or old.get("size") != current.get("size")
            or (expected and old.get("sha256") != expected)
        ):
            changed.add(slug)
    return changed


def empty_log() -> dict[str, Any]:
    return {"schemaVersion": 1, "count": 0, "head": ZERO, "entries": []}
