"""Regressions for static-source observations, links and unknown health."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from omnisource.app_schema import build_record
from omnisource.discovery import build_discovery_doc
from omnisource.domain import App, Catalog
from omnisource.feeds.altstore import render_altstore_app
from omnisource.intelligence import build_source_insights
from omnisource.search_index import build_search_index
from omnisource.source_registry import build_registry
from omnisource.transparency import append_observations, empty_log
from omnisource.trending import compute_trending
from omnisource.verification import build_verification_doc


class RegistrySnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = {
            "id": "owner/repo",
            "name": "Example",
            "sourceURL": "https://github.com/owner/repo",
            "score": 70,
            "apps": [{"slug": "example", "name": "Example", "version": "1"}],
        }
        self.status = {
            "generatedAt": "2026-10-28T04:23:28Z",
            "sources": [{"id": "owner/repo", "url": "https://github.com/owner/repo", "ok": True, "status": 200}],
        }

    def test_only_new_dated_exact_url_probe_is_counted(self) -> None:
        with patch("omnisource.source_registry.utcnow", return_value="2026-10-28T10:00:00Z"):
            first = build_registry([self.source], status=self.status)
        row = first["sources"][0]
        self.assertEqual(row["health_status"], "online")
        self.assertEqual(row["history"][-1]["observedAt"], self.status["generatedAt"])
        self.assertEqual(row["history"][-1]["observationURL"], self.status["sources"][0]["url"])
        with patch("omnisource.source_registry.utcnow", return_value="2026-10-28T12:00:00Z"):
            second = build_registry([self.source], status=self.status, previous=first)
        self.assertEqual(second, first, "offline rebuilds must not invent observations or new build times")
        changed = copy.deepcopy(self.status)
        changed["generatedAt"] = "2026-10-29T04:23:28Z"
        third = build_registry([self.source], status=changed, previous=second)
        self.assertEqual(len(third["sources"][0]["history"]), 2)
        self.assertEqual(build_source_insights(third)["sources"][0]["health_samples"], 2)
        self.assertEqual(build_source_insights(third)["sources"][0]["observed_uptime_percent"], 100)

    def test_older_or_replayed_snapshot_does_not_replace_newer_observation(self) -> None:
        latest = copy.deepcopy(self.status)
        latest["generatedAt"] = "2026-10-29T04:23:28Z"
        latest["sources"][0]["ok"] = False
        first = build_registry([self.source], status=latest)
        older = build_registry([self.source], status=self.status, previous=first)
        self.assertEqual(older["sources"][0]["health_status"], "offline")
        self.assertEqual(older["sources"][0]["last_health_observation"]["at"], latest["generatedAt"])
        self.assertEqual(len(older["sources"][0]["history"]), 1)
        # Even if the history cap eventually evicts an observation, a replay
        # of that same snapshot must not reinsert it as a fresh probe.
        capped = copy.deepcopy(first)
        capped["sources"][0]["history"] = [
            {"health": "unknown", "reputation": 70, "appCount": 1, "verification": "unverified"} for _ in range(90)
        ]
        replay = build_registry([self.source], status=latest, previous=capped)
        self.assertEqual(len(replay["sources"][0]["history"]), 90)
        self.assertFalse(any(item.get("observedAt") for item in replay["sources"][0]["history"]))

    def test_changed_metadata_is_not_a_new_health_probe(self) -> None:
        first = build_registry([self.source], status=self.status)
        revised = {**self.source, "score": 90}
        second = build_registry([revised], status=self.status, previous=first)
        self.assertEqual(second["sources"][0]["history"][-1]["health"], "unknown")
        self.assertEqual(build_source_insights(second)["sources"][0]["health_samples"], 1)

    def test_host_root_or_undated_probe_is_not_source_availability(self) -> None:
        for status in (
            {**self.status, "sources": [{**self.status["sources"][0], "url": "https://github.com"}]},
            {**self.status, "generatedAt": ""},
        ):
            with self.subTest(status=status):
                row = build_registry([self.source], status=status)["sources"][0]
                self.assertEqual(row["health_status"], "unknown")
                self.assertEqual(row["history"][-1]["health"], "unknown")
                self.assertNotIn("observedAt", row["history"][-1])

    def test_uptime_deduplicates_and_does_not_mix_endpoints(self) -> None:
        history = [
            {"health": "online", "observedAt": "2026-10-27T04:00:00Z", "observationURL": "https://old.test/feed"},
            {"health": "offline", "observedAt": "2026-10-28T04:00:00Z", "observationURL": "https://new.test/feed"},
            {"health": "offline", "observedAt": "2026-10-28T04:00:00Z", "observationURL": "https://new.test/feed"},
        ]
        row = build_source_insights({"sources": [{"source_id": "s", "history": history}]})["sources"][0]
        self.assertEqual(row["health_samples"], 1)
        self.assertEqual(row["observed_uptime_percent"], 0)

    def test_archiving_does_not_claim_a_failed_probe(self) -> None:
        first = build_registry([self.source], status=self.status)
        row = build_registry([], previous=first)["sources"][0]
        self.assertEqual(row["classification"], "Archived")
        self.assertEqual(row["health_status"], "unknown")
        self.assertEqual(row["history"], first["sources"][0]["history"])


class PublishedDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = App(
            slug="example",
            raw={
                "slug": "example",
                "name": "Example",
                "bundleIdentifier": "com.example.app",
                "developerName": "Dev",
                "icon": "app.png",
                "status": "stable",
                "localizedDescription": "Description",
                "compatibility": {"minOSVersion": "16.0", "clients": ["altstore"]},
                "features": ["downloads"],
                "bestFor": "Downloads",
                "featuresReviewed": {"version": "1.0", "downloadURL": "https://example.com/app.ipa"},
            },
        )
        self.catalog = Catalog(source={"baseURL": "https://example.com/source"}, clients=[], apps=[self.app])
        self.newest = {
            "version": "1.0",
            "date": "2026-10-28",
            "localizedDescription": "Release",
            "downloadURL": "https://example.com/app.ipa",
            "size": 4,
            "sha256": "a" * 64,
        }
        self.state = {"example": {"versions": [self.newest]}}

    def test_discovery_and_app_records_point_to_published_feed(self) -> None:
        discovery = build_discovery_doc(self.catalog, self.state)["apps"][0]
        record = build_record(self.catalog, self.app, self.state, {"downloadReachable": None})
        self.assertEqual(discovery["feedURL"], "https://example.com/source/feeds/example.json")
        self.assertEqual(record["feedURL"], discovery["feedURL"])
        self.assertIsNone(discovery["health"]["reachable"])
        self.assertIsNone(record["health"]["reachable"])
        self.assertIsNone(build_search_index(self.catalog, self.state)["documents"][0]["downloadReachable"])
        self.assertIsNone(compute_trending(self.app, self.state, None, "UNVERIFIED")["downloadReachable"])

    def test_features_are_additive_and_keep_the_reviewed_asset(self) -> None:
        entry = render_altstore_app(self.catalog, self.app, [self.newest], {})
        self.assertEqual(entry["omnisource"]["features"], ["downloads"])
        self.assertEqual(entry["omnisource"]["featuresReviewed"]["downloadURL"], self.newest["downloadURL"])
        self.assertEqual(entry["omnisource"]["bestFor"], "Downloads")

    def test_verification_projects_only_observations_for_current_asset(self) -> None:
        log = empty_log()
        record = {
            "slug": "example",
            "url": self.newest["downloadURL"],
            "size": 4,
            "sha256": "a" * 64,
            "expectedSha256": "a" * 64,
            "ok": True,
            "at": "2026-10-28",
        }
        append_observations(log, self.state, [record])
        doc = build_verification_doc(self.catalog, self.state, transparency_log=log)
        self.assertEqual(doc["apps"][0]["transparencyEvidence"]["lastHashedAt"], "2026-10-28")
        self.state["example"]["versions"][0]["downloadURL"] = "https://example.com/new.ipa"
        doc = build_verification_doc(self.catalog, self.state, transparency_log=log)
        self.assertIsNone(doc["apps"][0]["transparencyEvidence"])


class GeneratedLinkTests(unittest.TestCase):
    def test_published_local_urls_in_main_feed_projections_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        prefix = "https://raynmahbub.github.io/OmniSource/"
        files = (
            "feeds/apps.json",
            "feeds/updates.json",
            "feeds/discovery.json",
            "feeds/install.json",
            "feeds/sources.json",
            "feeds/clients/altstore.json",
        )
        missing: list[str] = []
        checked = 0

        def visit(value: object) -> None:
            nonlocal checked
            if isinstance(value, dict):
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, str) and value.startswith(prefix):
                relative = value[len(prefix) :].split("?", 1)[0].split("#", 1)[0]
                checked += 1
                if not (root / relative).exists():
                    missing.append(relative)

        for filename in files:
            visit(json.loads((root / filename).read_text(encoding="utf-8")))
        self.assertGreater(checked, 1000)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
