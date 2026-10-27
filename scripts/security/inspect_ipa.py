#!/usr/bin/env python3
"""Compare a local IPA's main bundle ID with the catalog without extraction.

Examples:
    python3 scripts/security/inspect_ipa.py /path/to/app.ipa --slug spotiflac
    python3 scripts/security/inspect_ipa.py /path/to/app.ipa --expected-bundle-id com.example.app

No network requests are made, and the IPA is never copied into the repository.
A match does not establish the publisher, signature, or safety of a binary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from omnisource.io import read_json
from omnisource.ipa import inspect_ipa


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ipa", type=Path, help="local IPA/TIPA file; never extracted")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--slug", help="catalog app slug whose bundle ID is expected")
    selector.add_argument("--expected-bundle-id", help="explicit expected CFBundleIdentifier")
    parser.add_argument("--catalog", type=Path, default=ROOT / "catalog.json")
    args = parser.parse_args(argv)
    expected = args.expected_bundle_id or ""
    if args.slug:
        catalog = read_json(args.catalog)
        apps = catalog.get("apps", []) if isinstance(catalog, dict) else []
        matches = [app for app in apps if isinstance(app, dict) and app.get("slug") == args.slug]
        if len(matches) != 1 or not matches[0].get("bundleIdentifier"):
            print(f"inspect_ipa: no unique catalog bundle ID for {args.slug!r}", file=sys.stderr)
            return 2
        expected = str(matches[0]["bundleIdentifier"])
    try:
        result = inspect_ipa(args.ipa, expected)
    except ValueError as error:
        print(f"inspect_ipa: {error}", file=sys.stderr)
        return 2
    if args.slug:
        result["slug"] = args.slug
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "match" else 1


if __name__ == "__main__":
    sys.exit(main())
