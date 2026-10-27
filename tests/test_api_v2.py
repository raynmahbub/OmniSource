"""Tests for the OmniStore Pro API contract (feeds/api/v2/)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from omnisource.api_v2 import (
    API_V2_SCHEMA_VERSION,
    MINIMUM_CLIENT_VERSION,
    build_api_v2_documents,
    build_categories_doc,
    build_featured_doc,
    build_updates_doc,
    compute_feed_version,
)
from omnisource.app_schema import build_app_records, validate_app_records
from omnisource.domain import Catalog
from omnisource.io import dumps_pretty

ROOT = Path(__file__).resolve().parents[1]


def _catalog_dict() -> dict:
    return {
        "source": {
            "name": "OmniSource",
            "identifier": "com.example.omnisource",
            "baseURL": "https://example.com/OmniSource",
            "icon": "OmniSource.png",
        },
        "clients": [{"id": "altstore", "name": "AltStore", "icon": "AltStore.png", "url": "https://example.com"}],
        "apps": [
            {
                "slug": "alpha",
                "name": "Alpha",
                "bundleIdentifier": "com.example.alpha",
                "developerName": "Dev",
                "icon": "Alpha.webp",
                "category": "utilities",
                "status": "stable",
                "featured": True,
                "localizedDescription": "Alpha does things.",
                "compatibility": {"minOSVersion": "16.0", "clients": ["altstore"]},
                "verification": {"method": "github-release", "publisher": "example/alpha"},
                "upstreamURL": "https://github.com/example/alpha",
            },
            {
                "slug": "beta",
                "name": "Beta",
                "bundleIdentifier": "com.example.beta",
                "developerName": "Dev",
                "icon": "Beta.webp",
                "category": "music",
                "status": "beta",
                "localizedDescription": "Beta plays things.",
                "compatibility": {"minOSVersion": "17.0", "clients": ["altstore"]},
                "verification": {"method": "github-release", "publisher": "example/beta"},
                "upstreamURL": "https://github.com/example/beta",
            },
        ],
    }


def _state() -> dict:
    return {
        "alpha": {
            "versions": [
                {
                    "version": "1.2.0",
                    "date": "2026-09-01",
                    "localizedDescription": "Release 1.2.0",
                    "downloadURL": "https://example.com/alpha.ipa",
                    "size": 1000,
                    "sha256": "0" * 64,
                }
            ]
        },
        "beta": {
            "versions": [
                {
                    "version": "0.9.0",
                    "date": "2026-08-01",
                    "localizedDescription": "Release 0.9.0",
                    "downloadURL": "https://example.com/beta.ipa",
                    "size": 2000,
                    "sha256": "1" * 64,
                }
            ]
        },
    }


class TestFeedVersion(unittest.TestCase):
    def test_feed_version_is_stable_and_short(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        records = build_app_records(catalog, _state())
        first = compute_feed_version(records)
        second = compute_feed_version(list(reversed(records)))
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{12}$")

    def test_feed_version_changes_with_installable_fields(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        records = build_app_records(catalog, _state())
        before = compute_feed_version(records)
        records[0]["version"] = "9.9.9"
        self.assertNotEqual(before, compute_feed_version(records))

    def test_feed_version_changes_when_installable_history_changes(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        state = _state()
        records = build_app_records(catalog, state)
        before = compute_feed_version(records, state)
        state["alpha"]["versions"].append(
            {"version": "1.0", "date": "2025-01-01", "downloadURL": "https://example.com/old.ipa", "size": 100}
        )
        self.assertNotEqual(before, compute_feed_version(records, state))

    def test_feed_version_ignores_display_metadata(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        records = build_app_records(catalog, _state())
        before = compute_feed_version(records)
        records[0]["description"] = "A brand new description"
        records[0]["icon"] = "https://example.com/other.png"
        self.assertEqual(before, compute_feed_version(records))


class TestContractDocuments(unittest.TestCase):
    def test_featured_doc_lists_featured_only(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        records = build_app_records(catalog, _state())
        doc = build_featured_doc(records, feed_version="abc", generated_at="2026-09-11")
        self.assertEqual(doc["schemaVersion"], API_V2_SCHEMA_VERSION)
        self.assertEqual(doc["count"], 1)
        self.assertEqual(doc["apps"][0]["id"], "alpha")

    def test_categories_doc_groups_and_counts(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        records = build_app_records(catalog, _state())
        doc = build_categories_doc(catalog, records, feed_version="abc", generated_at="2026-09-11")
        self.assertEqual(doc["count"], 2)
        by_id = {entry["id"]: entry for entry in doc["categories"]}
        self.assertEqual(by_id["utilities"]["apps"], ["alpha"])
        self.assertEqual(by_id["music"]["count"], 1)
        self.assertTrue(by_id["utilities"]["icon"].startswith("https://"))

    def test_updates_doc_assigns_monotonic_sequences(self) -> None:
        updates_doc = {
            "updates": [
                {"slug": "beta", "version": "0.9.0", "date": "2026-08-01", "kind": "updated"},
                {"slug": "alpha", "version": "1.2.0", "date": "2026-09-01", "kind": "updated"},
            ]
        }
        doc = build_updates_doc(updates_doc, feed_version="abc", generated_at="2026-09-11")
        # Newest first for display, but sequences rise with the date so a
        # client can persist sequenceHigh and apply only newer changes.
        self.assertEqual([change["slug"] for change in doc["changes"]], ["beta", "alpha"])
        self.assertEqual([change["sequence"] for change in doc["changes"]], [1, 2])
        self.assertEqual(doc["sequenceHigh"], 2)
        self.assertEqual(doc["sequenceLow"], 1)

    def test_manifest_covers_every_document_with_checksums(self) -> None:
        documents = build_api_v2_documents(Catalog.from_dict(_catalog_dict()), _state(), updates_doc={"updates": []})
        manifest = documents["api/v2/manifest.json"]
        self.assertEqual(manifest["schemaVersion"], 2)
        self.assertEqual(manifest["minimumClientVersion"], MINIMUM_CLIENT_VERSION)
        self.assertRegex(manifest["feedVersion"], r"^[0-9a-f]{12}$")
        self.assertEqual(manifest["appCount"], 2)
        self.assertIn("/api/v2/apps/{id}.json", manifest["endpoints"])
        self.assertIn("/api/v2/apps/{id}/versions.json", manifest["endpoints"])
        self.assertEqual(
            documents["api/v2/apps/alpha/versions.json"]["versions"], documents["api/v2/apps/alpha.json"]["versions"]
        )
        paths = {entry["path"] for entry in manifest["documents"]}
        self.assertIn("/api/v2/featured.json", paths)
        self.assertIn("/api/v2/apps/alpha.json", paths)
        self.assertNotIn("/api/v2/manifest.json", paths)
        for entry in manifest["documents"]:
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(entry["bytes"], 0)

    def test_manifest_checksums_match_serialized_bytes(self) -> None:
        documents = build_api_v2_documents(Catalog.from_dict(_catalog_dict()), _state(), updates_doc={"updates": []})
        manifest = documents["api/v2/manifest.json"]
        import hashlib

        for entry in manifest["documents"]:
            rel = "api/v2/" + entry["path"][len("/api/v2/") :]
            expected = hashlib.sha256(dumps_pretty(documents[rel]).encode("utf-8")).hexdigest()
            self.assertEqual(entry["sha256"], expected, entry["path"])

    def test_per_app_docs_validate_against_app_schema(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        documents = build_api_v2_documents(catalog, _state(), updates_doc={"updates": []})
        records = [documents[f"api/v2/apps/{slug}.json"]["app"] for slug in ("alpha", "beta")]
        report = validate_app_records(records, catalog)
        self.assertEqual(report.errors, [])
        per_app = documents["api/v2/apps/alpha.json"]
        self.assertEqual(per_app["newest"]["version"], "1.2.0")
        self.assertEqual(len(per_app["versions"]), 1)

    def test_real_repository_contract_is_consistent(self) -> None:
        contract = ROOT / "feeds" / "api" / "v2"
        manifest = json.loads((contract / "manifest.json").read_text(encoding="utf-8"))
        catalog = Catalog.from_dict(json.loads((ROOT / "catalog.json").read_text(encoding="utf-8")))
        self.assertEqual(manifest["schemaVersion"], 2)
        self.assertEqual(manifest["appCount"], len(catalog.apps))
        import hashlib

        for entry in manifest["documents"]:
            rel = "api/v2/" + entry["path"][len("/api/v2/") :]
            payload = (ROOT / "feeds" / rel).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(payload).hexdigest(), entry["path"])
        for name in ("featured.json", "categories.json", "updates.json"):
            doc = json.loads((contract / name).read_text(encoding="utf-8"))
            self.assertEqual(doc["feedVersion"], manifest["feedVersion"])


class TestSearchIndexContract(unittest.TestCase):
    def test_search_documents_carry_keywords_and_per_app_clients(self) -> None:
        from omnisource.search_index import SEARCH_INDEX_VERSION, build_search_index

        catalog = Catalog.from_dict(_catalog_dict())
        doc = build_search_index(catalog, _state())
        self.assertEqual(doc["schemaVersion"], SEARCH_INDEX_VERSION)
        by_id = {entry["id"]: entry for entry in doc["documents"]}
        self.assertIn("alpha", by_id["alpha"]["keywords"])
        self.assertIn("utilities", by_id["alpha"]["keywords"])
        self.assertEqual(by_id["alpha"]["clientCompatibility"], ["altstore"])
        key_names = {key["name"] for key in doc["fuse"]["keys"]}
        self.assertIn("keywords", key_names)


if __name__ == "__main__":
    unittest.main()
