#!/usr/bin/env python3
"""Render a read-only issue-form triage report; never evaluate submitted text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from omnisource.io import read_json
from omnisource.issue_ops import analyze


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe-github", action="store_true")
    args = parser.parse_args(argv)
    event = read_json(args.event)
    catalog = read_json(ROOT / "catalog.json")
    state = read_json(ROOT / "feeds/state.json")
    if not all(isinstance(item, dict) for item in (event, catalog, state)):
        print("issue_ops: invalid input", file=sys.stderr)
        return 1
    report = analyze(event.get("issue") or {}, catalog, state, network=args.probe_github)
    args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
