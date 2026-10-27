#!/usr/bin/env python3
"""Build ``data/security.json`` and gate the pipeline on critical findings.

Verifies SHA-256 / SHA-512 coverage, detects duplicate binaries, rolls up
download integrity and audits provenance. Exits 1 when a *critical*
finding exists (``security.yml`` blocks publication in that case).

Usage
-----
    python3 scripts/security/scan.py
    python3 scripts/security/scan.py --fail-on high  # also fail on high findings
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from omnisource.io import read_json, write_json, write_json_stable
from omnisource.security import build_security_report, verify_file, verify_url

ROOT = Path(__file__).resolve().parents[2]

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--feed", default=str(ROOT / "feeds" / "apps.json"))
    parser.add_argument("--catalog", default=str(ROOT / "catalog.json"))
    parser.add_argument("--health", default=str(ROOT / "data" / "status.json"))
    parser.add_argument("--out", default=str(ROOT / "data" / "security.json"))
    parser.add_argument(
        "--alias", default=str(ROOT / "security-report.json"), help="backward-compatible top-level report copy"
    )
    parser.add_argument("--fail-on", default="critical", choices=sorted(SEVERITY_RANK))
    parser.add_argument(
        "--verify-downloads", action="store_true", help="stream and hash newest assets (network and disk intensive)"
    )
    parser.add_argument(
        "--verify-file", action="append", default=[], help="verify a local binary (repeatable; useful in offline CI)"
    )
    parser.add_argument("--verify-timeout", type=float, default=300.0)
    parser.add_argument("--max-download-bytes", type=int, default=512 * 1024 * 1024)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    feed = read_json(Path(args.feed))
    apps = feed.get("apps", []) if isinstance(feed, dict) else []
    catalog = read_json(Path(args.catalog))
    catalog_apps = catalog.get("apps", []) if isinstance(catalog, dict) else []
    health = read_json(Path(args.health))
    app_records = [item for item in apps if isinstance(item, dict)]
    report = build_security_report(
        apps=app_records,
        catalog_apps=[item for item in catalog_apps if isinstance(item, dict)],
        health=health if isinstance(health, dict) else None,
    )
    if args.verify_file:
        local_results = []
        for filename in args.verify_file:
            result = verify_file(Path(filename))
            result["id"] = str(filename)
            local_results.append(result)
            if not result.get("ok"):
                report["findings"].append(
                    {
                        "severity": "critical" if result.get("kind") == "mismatch" else "medium",
                        "check": "local-binary-integrity"
                        if result.get("kind") == "mismatch"
                        else "local-verification-unavailable",
                        "id": str(filename),
                        "detail": result["detail"],
                    }
                )
        report["localFileVerification"] = local_results
    if args.verify_downloads:
        verification_results = []
        for app in app_records:
            versions = app.get("versions") if isinstance(app.get("versions"), list) else []
            newest = versions[0] if versions and isinstance(versions[0], dict) else app
            result = verify_url(
                str(newest.get("downloadURL") or app.get("downloadURL") or ""),
                sha256=str(newest.get("sha256") or app.get("sha256") or ""),
                sha512=str(newest.get("sha512") or app.get("sha512") or ""),
                expected_size=int(newest.get("size") or app.get("size") or 0) or None,
                timeout=max(1.0, args.verify_timeout),
                max_bytes=max(1, args.max_download_bytes),
            )
            result["id"] = str(app.get("slug") or app.get("id") or app.get("name") or "?")
            verification_results.append(result)
            if not result.get("ok"):
                report["findings"].append(
                    {
                        "severity": "critical" if result.get("kind") == "mismatch" else "medium",
                        "check": "binary-integrity"
                        if result.get("kind") == "mismatch"
                        else "download-verification-unavailable",
                        "id": result["id"],
                        "detail": result["detail"],
                    }
                )
        report["binaryVerification"] = verification_results
    report["verdict"] = "fail" if any(item["severity"] == "critical" for item in report["findings"]) else "pass"
    output = Path(args.out)
    if args.verify_downloads or args.verify_file:
        # A real verification is a new observation even if the result matches.
        write_json(output, report)
    else:
        # Avoid noisy commits when an offline scan only changes generatedAt.
        write_json_stable(output, report)
    if args.alias and Path(args.alias) != output:
        # Keep the public alias byte-identical even when a stable write skipped.
        write_json(Path(args.alias), read_json(output) or report)
    floor = SEVERITY_RANK[args.fail_on]
    blocking = [item for item in report["findings"] if SEVERITY_RANK[item["severity"]] >= floor]
    for item in report["findings"]:
        print(f"{item['severity']}: [{item['check']}] {item['id']} — {item['detail']}")
    summary = report["summary"]
    print(
        f"security: verdict={report['verdict']} "
        f"(sha256 {summary['sha256']}/{summary['apps']}, "
        f"dupes={summary['duplicateBinaries']}, failing={summary['downloadsFailing']}) -> {args.out}"
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
