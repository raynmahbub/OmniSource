"""Safely inspect the main app's bundle identifier in a local IPA archive.

The archive is never extracted or executed. A bundle match is evidence about
this file's Info.plist, not a signature, publisher, or safety verification.
"""

from __future__ import annotations

import plistlib
import re
import struct
import zipfile
from pathlib import Path
from typing import Any, BinaryIO
from xml.parsers.expat import ExpatError

MAX_INFO_PLIST_BYTES = 1024 * 1024
MAX_DIRECTORY_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20000
APP_INFO_PATH = re.compile(r"^Payload/[^/]+\.app/Info\.plist$")
BUNDLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")


def _check_directory_bounds(source: Path | BinaryIO) -> None:
    """Reject enormous central directories before zipfile loads them into RAM.

    ZIP64 and multi-volume archives stay unknown rather than being parsed
    without this bound. The byte payload itself is not extracted.
    """
    close = isinstance(source, Path)
    stream = source.open("rb") if close else source
    try:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
        offset = tail.rfind(b"PK\x05\x06")
        if offset < 0 or len(tail) - offset < 22:
            raise ValueError("missing ZIP end-of-directory record")
        signature, disk, start_disk, disk_entries, entries, directory_size, _directory_offset, comment = struct.unpack(
            "<4s4H2LH", tail[offset : offset + 22]
        )
        if signature != b"PK\x05\x06" or offset + 22 + comment != len(tail):
            raise ValueError("invalid ZIP directory trailer")
        if disk or start_disk or disk_entries != entries or entries == 0xFFFF or directory_size == 0xFFFFFFFF:
            raise ValueError("ZIP64 or multi-volume inspection is unavailable")
        if entries > MAX_ARCHIVE_ENTRIES or directory_size > MAX_DIRECTORY_BYTES:
            raise ValueError("ZIP central directory exceeds the inspection size limit")
    finally:
        if close:
            stream.close()


def inspect_ipa(path: Path | BinaryIO, expected_bundle_id: str = "") -> dict[str, Any]:
    """Read one main ``Payload/*.app/Info.plist`` with bounded decompression.

    Ambiguous archives, oversized plists, invalid plists, and missing bundle
    identifiers are rejected instead of guessing from an extension or widget.
    """
    expected = str(expected_bundle_id or "").strip()
    if expected and not BUNDLE_ID.fullmatch(expected):
        raise ValueError("expected bundle identifier is invalid")
    try:
        _check_directory_bounds(path)
        with zipfile.ZipFile(path) as archive:
            candidates = [item for item in archive.infolist() if APP_INFO_PATH.fullmatch(item.filename)]
            if len(candidates) != 1:
                raise ValueError("IPA must contain exactly one main Payload/*.app/Info.plist")
            info = candidates[0]
            if info.file_size > MAX_INFO_PLIST_BYTES or info.compress_size > MAX_INFO_PLIST_BYTES:
                raise ValueError("Info.plist exceeds the inspection size limit")
            with archive.open(info) as stream:
                data = stream.read(MAX_INFO_PLIST_BYTES + 1)
            if len(data) > MAX_INFO_PLIST_BYTES:
                raise ValueError("Info.plist exceeds the inspection size limit")
            plist = plistlib.loads(data)
            # Optional plist declarations are not a code-signature check. Most
            # IPAs do not contain either file; absence stays unknown.
            entitlements = None
            app_dir = info.filename.rsplit("/", 1)[0]
            for name in ("archived-expanded-entitlements.xcent", "Entitlements.plist"):
                try:
                    item = archive.getinfo(f"{app_dir}/{name}")
                except KeyError:
                    continue
                if item.file_size > MAX_INFO_PLIST_BYTES or item.compress_size > MAX_INFO_PLIST_BYTES:
                    raise ValueError("entitlements plist exceeds the inspection size limit")
                with archive.open(item) as stream:
                    raw_entitlements = stream.read(MAX_INFO_PLIST_BYTES + 1)
                if len(raw_entitlements) > MAX_INFO_PLIST_BYTES:
                    raise ValueError("entitlements plist exceeds the inspection size limit")
                parsed = plistlib.loads(raw_entitlements)
                if isinstance(parsed, dict):
                    entitlements = sorted(str(key) for key in parsed)
                    break
    except (
        OSError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        plistlib.InvalidFileException,
        ExpatError,
        EOFError,
        RuntimeError,
    ) as error:
        raise ValueError(f"unable to inspect IPA: {error}") from error
    if not isinstance(plist, dict):
        raise ValueError("main Info.plist is not a dictionary")
    bundle = plist.get("CFBundleIdentifier")
    if not isinstance(bundle, str) or not BUNDLE_ID.fullmatch(bundle):
        raise ValueError("main Info.plist has no valid CFBundleIdentifier")
    return {
        "bundleIdentifier": bundle,
        "expectedBundleIdentifier": expected or None,
        "status": ("match" if bundle == expected else "mismatch") if expected else "observed",
        "infoPath": info.filename,
        "version": str(plist.get("CFBundleShortVersionString") or ""),
        "build": str(plist.get("CFBundleVersion") or ""),
        "minOSVersion": str(plist.get("MinimumOSVersion") or ""),
        "privacyUsageDescriptions": {
            str(key): value
            for key, value in sorted(plist.items())
            if isinstance(key, str)
            and key.startswith("NS")
            and key.endswith("UsageDescription")
            and isinstance(value, str)
        },
        "declaredEntitlements": entitlements,
        "entitlementsNote": "Packaged plist declaration only; not a verified code-signature entitlement list"
        if entitlements is not None
        else "Not present in a readable packaged plist",
    }
