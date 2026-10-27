"""Tests for release notification dispatchers."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from omnisource.domain import UpdateEvent
from omnisource.notify import (
    send_discord_notification,
    send_generic_webhook,
    send_ntfy_notification,
    send_telegram_notification,
)


class TestNotify(unittest.TestCase):
    def setUp(self) -> None:
        self.update = UpdateEvent(
            app_id="spotiflac",
            name="Mornye",
            version="4.9.6",
            previous_version="4.9.5",
            release_date="2026-09-07",
            download_url="https://example.com/Mornye.ipa",
            changelog="Lossless audio downloads.",
            kind="updated",
        )

    @patch("urllib.request.urlopen")
    def test_discord_notification(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 204
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        success = send_discord_notification("https://discord.com/api/webhooks/test", [self.update])
        self.assertTrue(success)
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_telegram_notification(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        success = send_telegram_notification("token123", "chat456", [self.update])
        self.assertTrue(success)
        mock_urlopen.assert_called_once()

    def test_empty_updates(self) -> None:
        self.assertFalse(send_discord_notification("https://discord.com/api/webhooks/test", []))
        self.assertFalse(send_telegram_notification("token123", "chat456", []))
        self.assertFalse(send_ntfy_notification("https://ntfy.sh/test", []))
        self.assertFalse(send_generic_webhook("https://example.com/hook", []))

    @patch("urllib.request.urlopen")
    def test_ntfy_notification(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        success = send_ntfy_notification("omnisource-test", [self.update])
        self.assertTrue(success)
        mock_urlopen.assert_called_once()
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://ntfy.sh/omnisource-test")
        payload = json.loads(request.data)
        self.assertIn("Mornye", payload["title"])
        self.assertEqual(payload["tags"], ["tada"])

    @patch("urllib.request.urlopen")
    def test_generic_webhook(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 204
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        success = send_generic_webhook("https://example.com/hook", [self.update])
        self.assertTrue(success)
        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["event"], "release-update")
        self.assertEqual(payload["updates"][0]["appId"], "spotiflac")
        self.assertEqual(payload["updates"][0]["version"], "4.9.6")


if __name__ == "__main__":
    unittest.main()
