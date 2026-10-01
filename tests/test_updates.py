"""Tests for the website updates timeline document."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from omnisource.domain import Catalog
from omnisource.feeds.updates import render_updates_doc


class TestUpdatesDoc(unittest.TestCase):
    def setUp(self) -> None:
        self.raw_catalog = {
            "source": {
                "name": "OmniSource",
                "identifier": "app.omnisource",
                "baseURL": "https://raynmahbub.github.io/OmniSource",
                "icon": "OmniSource.png",
            },
            "apps": [
                {
                    "slug": "spotiflac",
                    "name": "SpotiFLAC Mobile",
                    "subtitle": "Lossless streaming",
                    "bundleIdentifier": "com.zarz.spotiflacAndroid",
                    "developerName": "zarzet",
                    "icon": "SpotiFLAC.png",
                    "status": "stable",
                },
                {
                    "slug": "feather",
                    "name": "Feather",
                    "bundleIdentifier": "thewonderofyou.Feather",
                    "developerName": "Feather Team",
                    "icon": "Feather.png",
                    "status": "manual",
                },
            ],
        }
        self.catalog = Catalog.from_dict(self.raw_catalog)

    def test_history_events_are_sorted_newest_first(self) -> None:
        state = {
            "updateHistory": [
                {
                    "appId": "feather",
                    "version": "2.9.0",
                    "releaseDate": "2026-09-01",
                    "downloadUrl": "https://example.com/Feather.ipa",
                    "changelog": "Feather 2.9.0.",
                    "kind": "updated",
                },
                {
                    "appId": "spotiflac",
                    "version": "4.9.6",
                    "releaseDate": "2026-09-07",
                    "downloadUrl": "https://example.com/SpotiFLAC.ipa",
                    "changelog": "SpotiFLAC 4.9.6.",
                    "kind": "updated",
                },
            ]
        }
        doc = render_updates_doc(self.catalog, state)
        self.assertEqual(doc["count"], 2)
        self.assertEqual([item["slug"] for item in doc["updates"]], ["spotiflac", "feather"])
        first = doc["updates"][0]
        self.assertEqual(first["name"], "SpotiFLAC Mobile")
        self.assertEqual(first["version"], "4.9.6")
        self.assertEqual(first["date"], "2026-09-07")
        self.assertIn("https://raynmahbub.github.io/OmniSource/assets/SpotiFLAC.png", first["iconURL"])
        self.assertIn(".xml", first["rssURL"])

    def test_current_versions_seed_sparse_history(self) -> None:
        state = {
            "spotiflac": {
                "versions": [
                    {
                        "version": "4.9.6",
                        "date": "2026-09-07",
                        "downloadURL": "https://example.com/SpotiFLAC.ipa",
                        "size": 34171700,
                        "localizedDescription": "Lossless downloader update.",
                    }
                ]
            }
        }
        doc = render_updates_doc(self.catalog, state)
        by_slug = {item["slug"]: item for item in doc["updates"]}
        self.assertIn("spotiflac", by_slug)
        self.assertEqual(by_slug["spotiflac"]["kind"], "available")
        self.assertEqual(by_slug["spotiflac"]["version"], "4.9.6")


if __name__ == "__main__":
    unittest.main()
