#!/usr/bin/env python3
"""Gate publication of a completed verification run's evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from omnisource.transparency import validate_log


def validate_evidence(receipt: object, state: object, report: object, ledger: object) -> None:
    """Reject interrupted or structurally inconsistent output, including a broken chain."""
    if not isinstance(receipt, dict) or receipt.get("completed") is not True:
        raise ValueError("verification did not complete")
    code = receipt.get("exitCode")
    if type(code) is not int or code not in (0, 1):
        raise ValueError("invalid verification exit code")
    if not isinstance(state, dict) or not state:
        raise ValueError("state is not a populated object")
    if not isinstance(report, dict) or not isinstance(report.get("apps"), list) or not report["apps"]:
        raise ValueError("integrity report has no apps")
    totals = report.get("totals")
    if not isinstance(totals, dict) or totals.get("apps") != len(report["apps"]):
        raise ValueError("integrity report app count is inconsistent")
    for app in report["apps"]:
        if not isinstance(app, dict) or not isinstance(app.get("slug"), str) or app["slug"] not in state:
            raise ValueError("integrity report app is missing from state")
    if not isinstance(ledger, dict):
        raise ValueError("transparency ledger is not an object")
    validate_log(ledger)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=ROOT / "feeds/state.json")
    parser.add_argument("--report", type=Path, default=ROOT / "feeds/integrity_report.json")
    parser.add_argument("--ledger", type=Path, default=ROOT / "feeds/transparency.json")
    args = parser.parse_args(argv)
    try:
        docs = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (args.receipt, args.state, args.report, args.ledger)
        ]
        validate_evidence(*docs)
    except (OSError, ValueError, TypeError) as error:
        print(f"Verification evidence cannot be published: {error}", file=sys.stderr)
        return 1
    print("Verification completed; evidence structure and transparency chain are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
