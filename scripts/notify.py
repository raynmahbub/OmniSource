#!/usr/bin/env python3
"""Send test or release broadcast notifications.

Transports are enabled through environment variables and dispatched together:
Discord (``DISCORD_WEBHOOK_URL``), Telegram (``TELEGRAM_BOT_TOKEN`` +
``TELEGRAM_CHAT_ID``), ntfy (``NTFY_URL``/``NTFY_TOPIC``) and a generic JSON
webhook (``OMNISOURCE_WEBHOOK_URL``). See ``omnisource.notify`` for details.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parent)
if _SCRIPTS in sys.path:
    sys.path.remove(_SCRIPTS)
_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC in sys.path:
    sys.path.remove(_SRC)
sys.path.insert(0, _SRC)

from omnisource.domain import UpdateEvent, today
from omnisource.io import read_json
from omnisource.notify import dispatch_configured_notifications


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dispatch release broadcast notifications")
    parser.add_argument("--test", action="store_true", help="send a test release event")
    args = parser.parse_args(argv)

    if args.test:
        test_event = UpdateEvent(
            app_id="spotiflac",
            name="Mornye",
            version="4.9.6",
            previous_version="4.9.5",
            release_date=today(),
            download_url="https://github.com/mornyeapp/Mornye/releases",
            changelog="Mornye v4.9.6 update test notification.",
            kind="updated",
        )
        dispatch_configured_notifications([test_event])
        print("Test notification dispatched (if env vars configured).")
        return 0

    state_path = Path(__file__).resolve().parents[1] / "feeds" / "state.json"
    state = read_json(state_path) or {}
    history = state.get("updateHistory", [])
    if not history:
        print("No update history to dispatch.")
        return 0

    dispatch_configured_notifications(history[:3])
    print("Dispatched recent updates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
