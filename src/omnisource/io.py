"""Atomic JSON and dataset I/O."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def dumps(data: Any) -> str:
    """Serialize compact deterministic JSON for generic callers."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n"


def dumps_pretty(data: Any) -> str:
    """Serialize a document as readable, deterministic UTF-8 JSON."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_json_stable(path: Path, data: dict[str, Any], *, volatile: tuple[str, ...] = ("generatedAt",)) -> bool:
    """Write ``data`` only when non-volatile content differs from disk.

    Derived documents (``data/*``, ``api/v3/*``) stamp ``generatedAt`` on
    every build. Rewriting them unconditionally would create an empty
    commit on each scheduled run, so this helper compares the payload
    without the volatile keys and skips the write when nothing changed.
    Returns True when the file was (re)written.
    """
    previous = read_json(path)
    if isinstance(previous, dict):
        old = {key: value for key, value in previous.items() if key not in volatile}
        new = {key: value for key, value in data.items() if key not in volatile}
        if old == new:
            return False
    return atomic_write_text(path, dumps_pretty(data))


def write_json(path: Path, data: Any) -> bool:
    """Atomically write ``data``; return True when the file actually changed."""
    return atomic_write_text(path, dumps_pretty(data))


def atomic_write_text(path: Path, payload: str) -> bool:
    """Write one UTF-8 file through a sibling temporary file."""
    # Compare bytes so deterministic CRLF formats such as iCalendar are not
    # rewritten merely because text-mode reads normalize line endings.
    if path.exists() and path.read_bytes() == payload.encode("utf-8"):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8", newline="")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return True


def atomic_write_many(
    documents: dict[Path, Any],
    *,
    validator: Callable[[Path, Any], None] | None = None,
    pretty: Callable[[Path], bool] | None = None,
) -> list[Path]:
    """Validate and publish a set of JSON documents as one guarded operation.

    All payloads are serialized and parsed before any target is touched. The
    existing bytes are copied to a private backup before replacement; if a
    filesystem error interrupts publication, changed targets are restored.
    This gives the sync engine last-known-good recovery in addition to the
    per-file atomicity of :func:`write_json`. Documents for which ``pretty``
    returns True are written human-readable (indented) instead of compact.
    """
    if not documents:
        return []
    prepared: dict[Path, str] = {}
    for path, data in sorted(documents.items(), key=lambda item: str(item[0])):
        if validator:
            validator(path, data)
        payload = dumps_pretty(data) if pretty and pretty(path) else dumps(data)
        json.loads(payload)
        prepared[path] = payload

    changed = [path for path, payload in prepared.items() if not _same_text(path, payload)]
    if not changed:
        return []
    common_parent = _common_parent(changed)
    common_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="omnisource-publish-", dir=common_parent) as temp_name:
        temp_root = Path(temp_name)
        staged: dict[Path, Path] = {}
        backups: dict[Path, Path] = {}
        for index, path in enumerate(changed):
            relative = _relative_to_common(path, common_parent)
            staged[path] = temp_root / "staged" / relative
            staged[path].parent.mkdir(parents=True, exist_ok=True)
            staged[path].write_text(prepared[path], encoding="utf-8")
            if path.exists():
                backups[path] = temp_root / "backup" / str(index)
                backups[path].parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backups[path])
        published: list[Path] = []
        try:
            for path in changed:
                path.parent.mkdir(parents=True, exist_ok=True)
                staged[path].replace(path)
                published.append(path)
        except BaseException:
            for path in reversed(published):
                backup = backups.get(path)
                if backup and backup.exists():
                    backup.replace(path)
                else:
                    path.unlink(missing_ok=True)
            raise
    return changed


def _same_text(path: Path, payload: str) -> bool:
    try:
        return path.read_text(encoding="utf-8") == payload
    except OSError:
        return False


def _common_parent(paths: list[Path]) -> Path:
    resolved = [path.resolve() for path in paths]
    try:
        return Path(os.path.commonpath([str(path.parent) for path in resolved]))
    except ValueError:
        return resolved[0].parent


def _relative_to_common(path: Path, common_parent: Path) -> Path:
    try:
        return path.resolve().relative_to(common_parent.resolve())
    except ValueError:
        # Different roots are rare in production; keep a collision-free name.
        return Path(path.name)
