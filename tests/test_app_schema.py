"""Tests for the centralized app schema (schemas/app.schema.json)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from omnisource.app_schema import (
    REQUIRED_RECORD_FIELDS,
    build_record,
    declared_bundle_groups,
    load_schema,
    record_from_feed_entry,
    schema_path,
    validate_app_records,
)
from omnisource.domain import Catalog

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
                "localizedDescription": "Alpha does things.",
                "compatibility": {"minOSVersion": "16.0", "clients": ["altstore"]},
                "verification": {"method": "github-release", "publisher": "example/alpha"},
                "upstreamURL": "https://github.com/example/alpha",
            },
            {
                "slug": "tube-one",
                "name": "Tube One",
                "bundleIdentifier": "com.google.ios.youtube",
                "developerName": "Dev",
                "icon": "TubeOne.webp",
                "category": "photo-video",
                "status": "stable",
                "localizedDescription": "Tube tweak one.",
                "alternativeTo": "tube-two",
                "compatibility": {"minOSVersion": "16.0", "clients": ["altstore"]},
                "verification": {"method": "github-release", "publisher": "example/tube-one"},
                "upstreamURL": "https://github.com/example/tube-one",
            },
            {
                "slug": "tube-two",
                "name": "Tube Two",
                "bundleIdentifier": "com.google.ios.youtube",
                "developerName": "Dev",
                "icon": "TubeTwo.webp",
                "category": "photo-video",
                "status": "stable",
                "localizedDescription": "Tube tweak two.",
                "alternativeTo": "tube-one",
                "compatibility": {"minOSVersion": "16.0", "clients": ["altstore"]},
                "verification": {"method": "github-release", "publisher": "example/tube-two"},
                "upstreamURL": "https://github.com/example/tube-two",
            },
        ],
    }


def _state() -> dict:
    def version(tag: str) -> dict:
        return {
            "version": tag,
            "date": "2026-09-01",
            "localizedDescription": f"Release {tag}",
            "downloadURL": f"https://example.com/{tag}.ipa",
            "size": 1000,
            "sha256": "0" * 64,
        }

    return {
        "alpha": {"versions": [version("1.2.0")]},
        "tube-one": {"versions": [version("2.0.0")]},
        "tube-two": {"versions": [version("3.1.0")]},
    }


class TestAppSchemaDocument(unittest.TestCase):
    def test_schema_file_exists_and_requires_client_fields(self) -> None:
        self.assertTrue(schema_path().is_file())
        schema = load_schema()
        for field in REQUIRED_RECORD_FIELDS:
            self.assertIn(field, schema["required"])
            self.assertIn(field, schema["properties"])

    def test_schema_required_fields_match_contract(self) -> None:
        self.assertEqual(
            set(REQUIRED_RECORD_FIELDS),
            {
                "id",
                "name",
                "bundleIdentifier",
                "version",
                "versionDate",
                "description",
                "category",
                "icon",
                "screenshots",
                "downloadURL",
                "source",
                "checksum",
            },
        )


class TestBuildRecord(unittest.TestCase):
    def test_record_carries_every_required_field(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        record = build_record(catalog, catalog.apps[0], _state())
        for field in REQUIRED_RECORD_FIELDS:
            self.assertIn(field, record)
        self.assertEqual(record["id"], "alpha")
        self.assertEqual(record["version"], "1.2.0")
        self.assertEqual(record["feedURL"], "https://example.com/OmniSource/feeds/alpha.json")
        self.assertEqual(record["icon"], "https://example.com/OmniSource/assets/Alpha.webp")
        self.assertEqual(record["checksum"], "0" * 64)
        self.assertEqual(record["source"], "example/alpha")

    def test_missing_icon_falls_back_to_placeholder(self) -> None:
        data = _catalog_dict()
        data["apps"][0]["icon"] = ""
        catalog = Catalog.from_dict(data)
        record = build_record(catalog, catalog.apps[0], _state())
        self.assertEqual(record["icon"], "https://example.com/OmniSource/assets/placeholders/app.svg")

    def test_description_falls_back_to_name(self) -> None:
        data = _catalog_dict()
        data["apps"][0]["localizedDescription"] = ""
        catalog = Catalog.from_dict(data)
        record = build_record(catalog, catalog.apps[0], _state())
        self.assertEqual(record["description"], "Alpha")

    def test_record_from_feed_entry_reads_slug(self) -> None:
        entry = {
            "name": "Alpha",
            "bundleIdentifier": "com.example.alpha",
            "developerName": "Dev",
            "version": "1.2.0",
            "versionDate": "2026-09-01",
            "localizedDescription": "Alpha does things.",
            "downloadURL": "https://example.com/1.2.0.ipa",
            "size": 1000,
            "iconURL": "https://example.com/OmniSource/assets/Alpha.webp",
            "versions": [{"sha256": "0" * 64}],
            "omnisource": {
                "slug": "alpha",
                "upstreamURL": "https://github.com/example/alpha",
                "verification": {"publisher": "example/alpha"},
            },
        }
        record = record_from_feed_entry(entry)
        self.assertEqual(record["id"], "alpha")
        self.assertEqual(record["source"], "https://github.com/example/alpha")
        self.assertEqual(record["checksum"], "0" * 64)


class TestDeclaredBundleGroups(unittest.TestCase):
    def test_declared_alternatives_form_a_group(self) -> None:
        groups = declared_bundle_groups(Catalog.from_dict(_catalog_dict()))
        self.assertEqual(groups["com.google.ios.youtube"], {"tube-one", "tube-two"})
        self.assertNotIn("com.example.alpha", groups)

    def test_undeclared_sharing_forms_no_group(self) -> None:
        data = _catalog_dict()
        del data["apps"][1]["alternativeTo"]
        del data["apps"][2]["alternativeTo"]
        self.assertEqual(declared_bundle_groups(data), {})


class TestValidateAppRecords(unittest.TestCase):
    def _records(self) -> list[dict]:
        catalog = Catalog.from_dict(_catalog_dict())
        return [build_record(catalog, app, _state()) for app in catalog.apps]

    def test_valid_records_pass(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        report = validate_app_records(self._records(), catalog)
        self.assertEqual(report.errors, [])

    def test_duplicate_ids_fail(self) -> None:
        records = self._records()
        records[1]["id"] = records[0]["id"]
        report = validate_app_records(records, _catalog_dict())
        self.assertTrue(any("duplicate id" in error for error in report.errors))

    def test_undeclared_duplicate_bundles_fail(self) -> None:
        records = self._records()
        records[0]["bundleIdentifier"] = "com.google.ios.youtube"
        report = validate_app_records(records, _catalog_dict())
        self.assertTrue(any("duplicate bundleIdentifier" in error for error in report.errors))

    def test_declared_duplicate_bundles_pass(self) -> None:
        catalog = Catalog.from_dict(_catalog_dict())
        records = [build_record(catalog, app, _state()) for app in catalog.apps]
        report = validate_app_records(records, catalog)
        self.assertEqual(report.errors, [])

    def test_empty_icon_fails(self) -> None:
        records = self._records()
        records[0]["icon"] = ""
        report = validate_app_records(records, _catalog_dict())
        self.assertTrue(any("empty icon" in error for error in report.errors))

    def test_relative_icon_fails(self) -> None:
        records = self._records()
        records[0]["icon"] = "assets/Alpha.webp"
        report = validate_app_records(records, _catalog_dict())
        self.assertTrue(any("icon must be an absolute" in error for error in report.errors))

    def test_invalid_versions_fail(self) -> None:
        for bad in ("", "latest release", "v"):
            records = self._records()
            records[0]["version"] = bad
            report = validate_app_records(records, _catalog_dict())
            self.assertTrue(report.errors, f"version {bad!r} should fail")

    def test_bad_date_fails(self) -> None:
        records = self._records()
        records[0]["versionDate"] = "yesterday"
        report = validate_app_records(records, _catalog_dict())
        self.assertTrue(any("versionDate" in error for error in report.errors))

    def test_missing_download_url_fails(self) -> None:
        records = self._records()
        records[0]["downloadURL"] = ""
        report = validate_app_records(records, _catalog_dict())
        self.assertTrue(any("empty downloadURL" in error for error in report.errors))

    def test_malformed_checksum_fails(self) -> None:
        records = self._records()
        records[0]["checksum"] = "not-a-hash"
        report = validate_app_records(records, _catalog_dict())
        self.assertTrue(any("checksum" in error for error in report.errors))

    def test_null_checksum_passes(self) -> None:
        records = self._records()
        records[0]["checksum"] = None
        report = validate_app_records(records, _catalog_dict())
        self.assertEqual(report.errors, [])

    def test_empty_description_warns_but_passes(self) -> None:
        records = self._records()
        records[0]["description"] = ""
        report = validate_app_records(records, _catalog_dict())
        self.assertEqual(report.errors, [])
        self.assertTrue(any("empty description" in warning for warning in report.warnings))

    def test_bad_screenshot_url_fails(self) -> None:
        records = self._records()
        records[0]["screenshots"] = ["not-a-url"]
        report = validate_app_records(records, _catalog_dict())
        self.assertTrue(any("screenshot" in error for error in report.errors))

    def test_real_repository_records_pass(self) -> None:
        import json

        catalog = Catalog.from_dict(json.loads((ROOT / "catalog.json").read_text(encoding="utf-8")))
        state = json.loads((ROOT / "feeds" / "state.json").read_text(encoding="utf-8"))
        health_doc = json.loads((ROOT / "feeds" / "health.json").read_text(encoding="utf-8"))
        from omnisource.app_schema import build_app_records

        report = validate_app_records(build_app_records(catalog, state, health_doc), catalog)
        self.assertEqual(report.errors, [])


if __name__ == "__main__":
    unittest.main()
