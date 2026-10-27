#!/usr/bin/env python3
"""Copy an opted-in, previously verified IPA to a local external archive.

No network access, automatic publication, or redistribution is performed.
The operator must establish rights separately before enabling an archive.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from omnisource.archive import archive_release
from omnisource.io import read_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--confirm-rights", action="store_true", help="confirm you have the necessary archival rights")
    parser.add_argument("--keep", type=int, default=2)
    parser.add_argument("--quota-bytes", type=int, default=2 * 1024**3)
    args = parser.parse_args(argv)
    try:
        result = archive_release(
            catalog=read_json(ROOT / "catalog.json"),
            state=read_json(ROOT / "feeds/state.json"),
            slug=args.slug,
            source=args.file,
            destination=args.destination,
            repo_root=ROOT,
            confirm_rights=args.confirm_rights,
            keep=args.keep,
            quota=args.quota_bytes,
        )
    except (OSError, ValueError, TypeError) as error:
        print(f"archive: {error}", file=sys.stderr)
        return 1
    print(f"archive: stored {result}; this file is not published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
