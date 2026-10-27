#!/usr/bin/env python3
"""Probe sources + downloads and write the ``data/status.json`` board.

States: ``online`` (everything reachable), ``degraded`` (partial outage),
``offline`` (total outage). Keeps a 30-sample rolling history. With
``--offline`` no request is made and the previous snapshot is left untouched;
an offline build must never make an old observation appear newly checked.

Usage
-----
    python3 scripts/monitoring/report_status.py
    python3 scripts/monitoring/report_status.py --offline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from omnisource.io import read_json, write_json
from omnisource.probes import build_status, check_downloads, check_sources

ROOT = Path(__file__).resolve().parents[2]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", default=str(ROOT / "feeds" / "sources.json"))
    parser.add_argument("--feed", default=str(ROOT / "feeds" / "apps.json"))
    parser.add_argument("--out", default=str(ROOT / "data" / "status.json"))
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--offline", action="store_true", help="re-emit the previous document untouched")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out = Path(args.out)
    if args.offline:
        previous = read_json(out)
        if isinstance(previous, dict):
            print(f"report_status: offline, preserving last check ({previous.get('overall', '?')}) -> {out}")
            return 0
        print("report_status: no previous status document; nothing to re-emit")
        return 1
    sources_doc = read_json(Path(args.sources))
    feed_doc = read_json(Path(args.feed))
    sources = sources_doc.get("sources", []) if isinstance(sources_doc, dict) else []
    apps = feed_doc.get("apps", []) if isinstance(feed_doc, dict) else []
    source_results = check_sources(
        [item for item in sources if isinstance(item, dict)],
        timeout=max(5, args.timeout),
        workers=max(1, args.workers),
    )
    download_results = check_downloads(
        [item for item in apps if isinstance(item, dict)],
        timeout=max(5, args.timeout),
        workers=max(1, args.workers),
    )
    previous = read_json(out)
    doc = build_status(source_results, download_results, previous=previous if isinstance(previous, dict) else None)
    write_json(out, doc)
    summary = doc["summary"]
    print(
        f"report_status: {doc['overall']} "
        f"(sources {summary['sourcesOk']}/{summary['sources']}, "
        f"downloads {summary['downloadsOk']}/{summary['downloads']}) -> {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
