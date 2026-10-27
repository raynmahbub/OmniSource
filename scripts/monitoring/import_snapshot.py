#!/usr/bin/env python3
"""Import an existing monitoring snapshot into feed state (dry-run by default).

Only matching app IDs and current download URLs are imported; actual recorded
probe times are preserved. Run the offline feed builder afterward to publish.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from omnisource.domain import Catalog
from omnisource.io import read_json, write_json
from omnisource.monitor_import import import_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=str(ROOT / "catalog.json"))
    parser.add_argument("--snapshot", default=str(ROOT / "data" / "status.json"))
    parser.add_argument("--state", default=str(ROOT / "feeds" / "state.json"))
    parser.add_argument("--apply", action="store_true", help="write the imported observations to state")
    args = parser.parse_args(argv)
    state, snapshot, catalog = (
        read_json(Path(args.state)),
        read_json(Path(args.snapshot)),
        read_json(Path(args.catalog)),
    )
    if not isinstance(state, dict) or not isinstance(snapshot, dict) or not isinstance(catalog, dict):
        parser.error("catalog, state, and snapshot must be valid JSON objects")
    try:
        counts = import_snapshot(Catalog.from_dict(catalog), state, snapshot)
    except ValueError as exc:
        parser.error(str(exc))
    if args.apply and counts["imported"]:
        write_json(Path(args.state), state)
    print(
        f"monitor import: {counts['imported']} matching observations, {counts['skipped']} skipped "
        f"({'written' if args.apply else 'dry run'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
