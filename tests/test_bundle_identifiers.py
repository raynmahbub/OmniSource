"""Regression coverage for upstream bundle identities and published surfaces."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Evidence and the distinction between developer and community-built IPAs are
# recorded in docs/BUNDLE-ID-AUDIT-2026-10-27.md. These are the IDs of the
# releases being offered, not necessarily those of their untweaked base apps.
EXPECTED_IDS = {
    "spotiflac": "com.zarz.mornye",
    "nebuloiptv": "tv.onside.app",
    "nuvio": "com.nuvio.media",
    "redditfilter": "com.reddit.Reddit",
    "bhinstagram": "com.burbn.instagram",
    "swiftgram": "app.swiftgram.ios.mxgram",
    "telegram-mxgram": "ph.telegra.Telegraph.mxgram",
    "ime": "com.olcorporation.olai.mxgram",
    "turrit-mxgram": "com.seastar.turrit.mxgram",
}


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class BundleIdentifierTests(unittest.TestCase):
    def test_audited_identifiers_and_collisions(self) -> None:
        apps = {app["slug"]: app for app in load("catalog.json")["apps"]}
        for slug, expected in EXPECTED_IDS.items():
            with self.subTest(slug=slug):
                self.assertEqual(apps[slug]["bundleIdentifier"], expected)
        self.assertNotEqual(apps["redditfilter"].get("alternativeTo"), "bhtwitter")
        self.assertEqual(apps["bhinstagram"]["alternativeTo"], "ryukgram")
        self.assertEqual(apps["spotiflac"]["name"], "Mornye")

    def test_every_published_surface_uses_catalog_identifiers(self) -> None:
        catalog = {app["slug"]: app["bundleIdentifier"] for app in load("catalog.json")["apps"]}
        combined = load("feeds/apps.json")
        by_slug = {app["omnisource"]["slug"]: app["bundleIdentifier"] for app in combined["apps"]}
        self.assertEqual(by_slug, catalog)
        self.assertEqual(load("apps.json")["apps"], combined["apps"])

        v3_by_slug = {}
        for path in (ROOT / "api/v3/apps").glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))["data"]
            slug = record.get("omnisource", {}).get("slug")
            if slug:
                self.assertNotIn(slug, v3_by_slug)
                v3_by_slug[slug] = record["bundleIdentifier"]
        self.assertEqual(v3_by_slug, catalog)

        for slug, expected in catalog.items():
            with self.subTest(slug=slug):
                self.assertEqual(load(f"feeds/{slug}.json")["apps"][0]["bundleIdentifier"], expected)
                self.assertEqual(load(f"feeds/api/v2/apps/{slug}.json")["app"]["bundleIdentifier"], expected)
                self.assertEqual(load(f"api/v2/apps/{slug}.json")["app"]["bundleIdentifier"], expected)


if __name__ == "__main__":
    unittest.main()
