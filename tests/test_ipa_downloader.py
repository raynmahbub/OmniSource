"""Security and accessibility contracts for the generated IPA downloader."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_ipa_downloader", ROOT / "scripts" / "build_ipa_downloader.py")
assert SPEC and SPEC.loader, "cannot load scripts/build_ipa_downloader.py"
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["build_ipa_downloader"] = MODULE
SPEC.loader.exec_module(MODULE)


class IpaDownloaderTemplateTests(unittest.TestCase):
    def test_keyboard_and_screen_reader_landmarks(self) -> None:
        template = MODULE.PAGE_TEMPLATE
        self.assertIn('<a class="skip-link" href="#list">', template)
        self.assertIn('<label class="sr-only" for="q">', template)
        self.assertIn('<main id="list" aria-label="App downloads">', template)
        self.assertIn('id="count" aria-live="polite"', template)
        self.assertIn("focus-visible", template)

    def test_upstream_records_never_become_markup(self) -> None:
        template = MODULE.PAGE_TEMPLATE
        self.assertNotIn(".innerHTML", template)
        self.assertIn("document.createElement", template)
        self.assertIn("textContent", template)
        self.assertIn("function safeUrl", template)
        self.assertIn("if (/^https:\\/\\//i.test(url)) return url;", template)

    def test_script_closing_text_is_escaped_in_embedded_json(self) -> None:
        hostile = "</script><script>alert(1)</script>"
        page = MODULE.render_html(
            {
                "generatedAt": "2026-10-24T00:00:00Z",
                "baseURL": "https://example.invalid/OmniSource",
                "apps": [{"name": hostile}],
            }
        )
        self.assertNotIn(hostile, page)
        self.assertIn(r"<\/script><script>alert(1)<\/script>", page)


if __name__ == "__main__":
    unittest.main()
