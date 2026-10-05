"""Guard the Cloudflare Workers Builds configuration used for PR previews."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CloudflareWorkersConfigTests(unittest.TestCase):
    def test_preview_build_has_required_wrangler_configuration(self) -> None:
        config_path = ROOT / "wrangler.jsonc"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(config["name"], "omnisource")
        self.assertEqual(config["previews"], {})
        self.assertEqual(config["assets"]["directory"], "./_site")
        self.assertEqual(config["build"]["command"], "python3 scripts/build_site.py")
        self.assertTrue((ROOT / "scripts/build_site.py").is_file())


if __name__ == "__main__":
    unittest.main()
