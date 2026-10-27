"""Explicit, local-only archive of integrity-matched bytes (never auto-published)."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from omnisource.discovery import newest_version
from omnisource.integrity import digest_evidence
from omnisource.io import atomic_write_text

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


def archive_release(
    *,
    catalog: dict[str, Any],
    state: dict[str, Any],
    slug: str,
    source: Path,
    destination: Path,
    repo_root: Path,
    confirm_rights: bool,
    keep: int = 2,
    quota: int = 2 * 1024**3,
) -> Path:
    """Copy one previously verified current IPA outside the repo, within a quota.

    Opt-in and confirmation are necessary but cannot establish legal rights;
    the operator remains responsible. This does not host or publish the file.
    """
    if not confirm_rights or not SLUG.fullmatch(slug) or not 1 <= keep <= 10 or quota <= 0:
        raise ValueError("explicit rights confirmation, valid slug, retention and quota are required")
    apps = [app for app in catalog.get("apps", []) if isinstance(app, dict) and app.get("slug") == slug]
    if len(apps) != 1 or apps[0].get("archive") is not True:
        raise ValueError("this app is not explicitly opted in to archiving")
    latest = newest_version(state, slug)
    node = state.get(slug) if isinstance(state.get(slug), dict) else {}
    evidence = digest_evidence(latest, node)
    digest = str(latest.get("sha256") or "").lower()
    verification = node.get("lastFullVerification") if isinstance(node.get("lastFullVerification"), dict) else {}
    if (
        evidence.get("status") != "matched"
        or not SHA.fullmatch(digest)
        or verification.get("url") != latest.get("downloadURL")
    ):
        raise ValueError("a current URL-bound, matched SHA-256 verification is required")
    if not str(latest.get("downloadURL") or "").split("?", 1)[0].lower().endswith((".ipa", ".tipa")):
        raise ValueError("only IPA/TIPA releases are eligible")
    root = repo_root.resolve()
    dest = destination.resolve()
    if dest == root or root in dest.parents:
        raise ValueError("archive destination must be outside the repository")
    if source.is_symlink() or not source.is_file():
        raise ValueError("source must be a regular local file, not a symlink")
    expected_size = latest.get("size")
    size = source.stat().st_size
    if not isinstance(expected_size, int) or expected_size <= 0 or size != expected_size or size > quota:
        raise ValueError("local file size does not match the verified release or exceeds the quota")
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("archive manifest cannot be a symlink")
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError("existing archive manifest is unreadable") from error
        if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
            raise ValueError("existing archive manifest is invalid")
    else:
        manifest = {"schemaVersion": 1, "entries": []}
    folder = dest / slug
    if folder.is_symlink():
        raise ValueError("archive app directory cannot be a symlink")
    folder.mkdir(exist_ok=True)
    target = folder / f"{digest}.ipa"
    if target.is_symlink():
        raise ValueError("archive target cannot be a symlink")
    used = sum(path.stat().st_size for path in dest.glob("*/*.ipa") if path.is_file() and not path.is_symlink())
    if not target.exists() and used + size > quota:
        raise ValueError("archive quota would be exceeded")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".archive-", suffix=".tmp", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            sha = hashlib.sha256()
            copied = 0
            with source.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > size:
                        raise ValueError("source changed while copying")
                    sha.update(chunk)
                    tmp.write(chunk)
            if copied != size or sha.hexdigest() != digest:
                raise ValueError("local bytes do not match the recorded SHA-256")
        tmp_path.replace(target)
        entries = [
            item
            for item in manifest["entries"]
            if isinstance(item, dict) and not (item.get("slug") == slug and item.get("sha256") == digest)
        ]
        entries.append(
            {
                "slug": slug,
                "version": str(latest.get("version") or ""),
                "sha256": digest,
                "size": size,
                "sourceURL": str(latest.get("downloadURL") or ""),
                "verifiedAt": evidence.get("checkedAt", ""),
                "path": f"{slug}/{digest}.ipa",
            }
        )
        related = [item for item in entries if item.get("slug") == slug]
        remove = related[:-keep] if len(related) > keep else []
        for item in remove:
            old_digest = str(item.get("sha256") or "")
            expected_path = f"{slug}/{old_digest}.ipa"
            if not SHA.fullmatch(old_digest) or item.get("path") != expected_path:
                raise ValueError("unsafe archive manifest entry")
        entries = [item for item in entries if item not in remove]
        atomic_write_text(manifest_path, json.dumps({"schemaVersion": 1, "entries": entries}, indent=2) + "\n")
        for item in remove:
            old = folder / f"{item['sha256']}.ipa"
            if old.is_symlink():
                raise ValueError("refusing to remove a symlink from the archive")
            old.unlink(missing_ok=True)
        return target
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
