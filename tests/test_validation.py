"""Tests for offline validator."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import tempfile
import unittest
from pathlib import Path

from omnisource.constants import PNG_MAGIC
from omnisource.validation import (
    Report,
    _validate_upstream,
    validate_catalog,
    validate_doc_shape,
    validate_feed,
)


class TestValidation(unittest.TestCase):
    def test_asset_specific_min_os_validation(self) -> None:
        base = {"repo": "owner/repo", "provider": "github"}
        valid = {**base, "minOSVersionByAssetName": {"app_1.2.3-beta.ipa": "16.0", "app_2.0.ipa": "17"}}
        self.assertEqual(_validate_upstream("app", {"upstream": valid}).errors, [])

        for invalid in (["16.0"], {"": "16.0"}, {"app.ipa": "iOS 16"}, {"app.ipa": 16}):
            with self.subTest(invalid=invalid):
                upstream = {**base, "minOSVersionByAssetName": invalid}
                self.assertTrue(_validate_upstream("app", {"upstream": upstream}).errors)

    def test_validate_catalog_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            assets_dir = Path(tmpdir)
            (assets_dir / "Icon.png").write_bytes(PNG_MAGIC + b"data")

            catalog = {
                "source": {
                    "name": "OmniSource",
                    "identifier": "com.omnisource",
                    "baseURL": "https://example.com",
                    "icon": "Icon.png",
                },
                "apps": [
                    {
                        "slug": "app-one",
                        "name": "App One",
                        "bundleIdentifier": "com.example.appone",
                        "developerName": "Dev",
                        "icon": "Icon.png",
                        "status": "stable",
                        "localizedDescription": "A great app.",
                        "compatibility": {
                            "minOSVersion": "16.0",
                            "clients": ["altstore", "sidestore"],
                        },
                        "upstream": {
                            "provider": "github",
                            "repo": "owner/repo",
                        },
                    }
                ],
            }
            report = validate_catalog(catalog, assets_dir=assets_dir)
            self.assertEqual(len(report.errors), 0)

    def test_duplicate_bundle_identifiers_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            assets_dir = Path(tmpdir)
            (assets_dir / "Icon.png").write_bytes(PNG_MAGIC + b"data")
            catalog = {
                "source": {
                    "name": "OmniSource",
                    "identifier": "com.omnisource",
                    "baseURL": "https://example.com",
                    "icon": "Icon.png",
                },
                "apps": [
                    {
                        "slug": "app-a",
                        "name": "App A",
                        "bundleIdentifier": "com.example.shared",
                        "developerName": "Dev",
                        "icon": "Icon.png",
                        "status": "stable",
                        "localizedDescription": "A great app.",
                        "compatibility": {"minOSVersion": "16.0", "clients": ["altstore"]},
                        "upstream": {"provider": "github", "repo": "owner/repo"},
                    },
                    {
                        "slug": "app-b",
                        "name": "App B",
                        "bundleIdentifier": "com.example.shared",
                        "developerName": "Dev",
                        "icon": "Icon.png",
                        "status": "stable",
                        "localizedDescription": "Another app.",
                        "compatibility": {"minOSVersion": "16.0", "clients": ["altstore"]},
                        "upstream": {"provider": "github", "repo": "owner/repo"},
                    },
                ],
            }
            # Phase 5: an undeclared shared bundle fails CI (one error per app).
            report = validate_catalog(catalog, assets_dir=assets_dir)
            self.assertEqual(len(report.errors), 2)
            messages = " | ".join(report.errors)
            self.assertIn("com.example.shared", messages)
            self.assertIn("app-a", messages)
            self.assertIn("app-b", messages)

    def test_declared_alternatives_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            assets_dir = Path(tmpdir)
            (assets_dir / "Icon.png").write_bytes(PNG_MAGIC + b"data")
            catalog = {
                "source": {
                    "name": "OmniSource",
                    "identifier": "com.omnisource",
                    "baseURL": "https://example.com",
                    "icon": "Icon.png",
                },
                "apps": [
                    {
                        "slug": "app-a",
                        "name": "App A",
                        "bundleIdentifier": "com.example.shared",
                        "alternativeTo": "app-b",
                        "developerName": "Dev",
                        "icon": "Icon.png",
                        "status": "stable",
                        "localizedDescription": "An app.",
                        "compatibility": {"minOSVersion": "16.0", "clients": ["altstore"]},
                        "upstream": {"provider": "github", "repo": "owner/repo"},
                    },
                    {
                        "slug": "app-b",
                        "name": "App B",
                        "bundleIdentifier": "com.example.shared",
                        "alternativeTo": "app-a",
                        "developerName": "Dev",
                        "icon": "Icon.png",
                        "status": "stable",
                        "localizedDescription": "Another app.",
                        "compatibility": {"minOSVersion": "16.0", "clients": ["altstore"]},
                        "upstream": {"provider": "github", "repo": "owner/repo"},
                    },
                ],
            }
            # Declared alternatives must not error and must not warn about the
            # shared bundle any more.
            report = validate_catalog(catalog, assets_dir=assets_dir)
            self.assertEqual(len(report.errors), 0)
            self.assertNotIn("com.example.shared", " | ".join(report.warnings))

    def test_validate_catalog_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            assets_dir = Path(tmpdir)
            catalog = {
                "source": {},
                "apps": [
                    {
                        "slug": "INVALID_SLUG",
                    }
                ],
            }
            report = validate_catalog(catalog, assets_dir=assets_dir)
            self.assertGreater(len(report.errors), 0)

    def test_validate_feed(self) -> None:
        valid_feed = {
            "name": "OmniSource",
            "identifier": "com.omnisource",
            "apps": [
                {
                    "name": "Test App",
                    "bundleIdentifier": "com.test.app",
                    "developerName": "Dev",
                    "version": "1.0.0",
                    "versionDate": "2026-09-07",
                    "localizedDescription": "Description",
                    "downloadURL": "https://example.com/app.ipa",
                    "size": 1000,
                    "iconURL": "https://example.com/icon.png",
                    "tintColor": "FF0000",
                    "versions": [
                        {
                            "version": "1.0.0",
                            "date": "2026-09-07",
                            "localizedDescription": "Description",
                            "downloadURL": "https://example.com/app.ipa",
                            "size": 1000,
                        }
                    ],
                }
            ],
        }
        report = validate_feed(Path("test.json"), valid_feed, root=Path())
        self.assertEqual(len(report.errors), 0)


class TestIntegrityReportValidation(unittest.TestCase):
    """TrollStore-named IPAs (.tipa) pass the integrity hard-reject rules."""

    def _validate(self, download_url: str) -> object:
        doc = {
            "totals": {"apps": 1},
            "apps": [
                {
                    "slug": "bootstrap",
                    "asset": {
                        "sha256": None,
                        "size": 55704386,
                        "releaseId": "2.2.1",
                        "source": "github",
                        "downloadUrl": download_url,
                    },
                }
            ],
        }
        report = Report()
        validate_doc_shape(
            "integrity_report.json",
            doc,
            {"apps": [{"slug": "bootstrap"}]},
            report,
            root=Path(tempfile.gettempdir()),
            apps_count=1,
        )
        return report

    def test_tipa_counts_as_an_ipa(self) -> None:
        report = self._validate("https://example.com/Bootstrap.tipa")
        self.assertEqual(report.errors, [])

    def test_plain_ipa_still_passes(self) -> None:
        self.assertEqual(self._validate("https://example.com/Dopamine.ipa").errors, [])

    def test_other_containers_still_fail(self) -> None:
        report = self._validate("https://example.com/Bootstrap.zip")
        self.assertTrue(any("not an IPA" in message for message in report.errors))


if __name__ == "__main__":
    unittest.main()
