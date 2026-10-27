"""Command-line entry points for the OmniSource pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from omnisource import __version__
from omnisource.errors import SyncError
from omnisource.logutil import configure_logging, log
from omnisource.pipeline import run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OmniSource distribution pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="rebuild from feeds/state.json without hitting upstream APIs",
    )
    parser.add_argument("--no-health", action="store_true", help="skip download link probing")
    parser.add_argument(
        "--verify-downloads",
        action="store_true",
        help="stream-download and hash every app's newest asset (full integrity; fails on rejection)",
    )
    parser.add_argument(
        "--inspect-ipa", action="store_true", help="inspect bounded temporary copies during download verification"
    )
    parser.add_argument(
        "--verification-receipt",
        type=Path,
        help="write a completion receipt after a verification run finishes (for automation)",
    )
    parser.add_argument(
        "--verify-changed",
        action="store_true",
        help="with --verify-downloads, hash assets absent from the transparency log",
    )
    parser.add_argument("--only", metavar="SLUG", action="append", help="restrict the sync stage to these app slugs")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="skip pagination when the newest matching asset URL is unchanged",
    )
    parser.add_argument("--workers", type=int, default=8, help="concurrent link probes (default: 8)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument("--version", action="store_true", help="show the OmniSource version and exit")
    args = parser.parse_args(argv)
    if (args.inspect_ipa or args.verify_changed or args.verification_receipt) and not args.verify_downloads:
        parser.error("--inspect-ipa, --verify-changed and --verification-receipt require --verify-downloads")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    configure_logging(args.verbose)
    if args.verification_receipt:
        try:
            args.verification_receipt.unlink(missing_ok=True)
        except OSError as error:
            log.error("cannot clear verification receipt: %s", error)
            return 1
    try:
        code, _report = run(
            no_sync=args.no_sync,
            no_health=args.no_health,
            verify=args.verify_downloads,
            verify_changed=args.verify_changed,
            inspect_ipa=args.inspect_ipa,
            only=set(args.only) if args.only else None,
            incremental=args.incremental,
            workers=args.workers,
        )
        if args.verification_receipt:
            args.verification_receipt.write_text(
                json.dumps({"completed": True, "exitCode": code}) + "\n", encoding="utf-8"
            )
        return code
    except SyncError as error:
        log.error("%s", error)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":
    sys.exit(main())
