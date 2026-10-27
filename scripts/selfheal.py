#!/usr/bin/env python3
"""Detect breakage and plan repairs (``data/selfheal_report.json``).

Reads the feed + health documents, detects broken downloads, missing
metadata and removed releases (via ``data/release_history.json``), and
writes repair plans from the most recent monitoring snapshot. ``--apply``
only changes a patched feed copy for review, never the published feed.
Reachability alone is not enough to substitute a mirror; optional streamed
verification must match the current recorded SHA-256.

Usage
-----
    python3 scripts/selfheal.py
    python3 scripts/selfheal.py --apply --reprobe
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parent)
if _SCRIPTS in sys.path:
    sys.path.remove(_SCRIPTS)
_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC in sys.path:
    sys.path.remove(_SRC)
sys.path.insert(0, _SRC)

from omnisource.io import read_json, write_json, write_json_stable
from omnisource.probes import app_key, check_downloads
from omnisource.security import verify_url
from omnisource.selfheal import apply_safe_fixes, build_report, detect_issues, plan_repairs

ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--feed", default=str(ROOT / "feeds" / "apps.json"))
    parser.add_argument("--health", default=str(ROOT / "data" / "status.json"))
    parser.add_argument("--history", default=str(ROOT / "data" / "release_history.json"))
    parser.add_argument("--out", default=str(ROOT / "data" / "selfheal_report.json"))
    parser.add_argument("--apply", action="store_true", help="write data/healed_apps.json with safe fixes")
    parser.add_argument("--reprobe", action="store_true", help="re-probe downloads live before planning")
    parser.add_argument(
        "--verify-fallbacks",
        action="store_true",
        help="stream reachable declared mirrors and compare their recorded SHA-256",
    )
    parser.add_argument("--max-download-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--verify-timeout", type=float, default=300.0)
    return parser.parse_args(argv)


def verify_reachable_fallbacks(issues: list[dict], *, max_bytes: int, timeout: float) -> None:
    """Enrich reachable mirror probes only after matching the current digest."""
    for issue in issues:
        expected = str(issue.get("expectedSha256") or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            continue
        declared = {url for url in (issue.get("fallbacks") or []) if isinstance(url, str)}
        for probe in issue.get("fallbackProbes") or []:
            if not isinstance(probe, dict) or probe.get("ok") is not True or probe.get("url") not in declared:
                continue
            result = verify_url(str(probe["url"]), sha256=expected, max_bytes=max_bytes, timeout=timeout)
            probe["digestVerified"] = result.get("ok") is True and str(result.get("sha256") or "").lower() == expected
            probe["sha256"] = str(result.get("sha256") or "")
            probe["verificationDetail"] = str(result.get("detail") or "")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    feed = read_json(Path(args.feed))
    apps = list(feed.get("apps", [])) if isinstance(feed, dict) else []
    apps = [app for app in apps if isinstance(app, dict)]
    for app in apps:
        app.setdefault("slug", app_key(app))
    health: dict = {}
    if args.reprobe:
        health = {"downloads": check_downloads(apps)}
    else:
        stored = read_json(Path(args.health))
        health = stored if isinstance(stored, dict) else {}
    ledger = read_json(Path(args.history))
    removed: dict[str, list[dict]] = {}
    if isinstance(ledger, dict) and isinstance(ledger.get("apps"), dict):
        for slug, entries in ledger["apps"].items():
            gone = [entry for entry in entries if isinstance(entry, dict) and entry.get("status") == "removed"]
            if gone:
                removed[slug] = gone
    issues = detect_issues(apps=apps, health=health, removed=removed)
    if args.verify_fallbacks:
        verify_reachable_fallbacks(
            issues, max_bytes=max(1, args.max_download_bytes), timeout=max(1.0, args.verify_timeout)
        )
    plans = plan_repairs(issues)
    applied = 0
    if args.apply:
        _fixed, applied = apply_safe_fixes(apps, plans)
        write_json(Path(ROOT / "data" / "healed_apps.json"), {"count": len(_fixed), "apps": _fixed})
    report = build_report(plans, applied=applied)
    changed = write_json_stable(Path(args.out), report)
    print(
        f"selfheal: {report['issues']} issue(s), {report['autoFixable']} auto-fixable, "
        f"{applied} applied{'' if changed else ' (unchanged)'} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
