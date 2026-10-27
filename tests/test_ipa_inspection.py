"""Local, bounded IPA inspection; no real application binaries are needed."""

from __future__ import annotations

import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from omnisource.ipa import MAX_INFO_PLIST_BYTES, inspect_ipa

ROOT = Path(__file__).resolve().parents[1]


def make_ipa(path: Path, bundle: str = "com.example.app", *, nested: bool = True) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "Payload/Demo.app/Info.plist",
            plistlib.dumps({"CFBundleIdentifier": bundle, "CFBundleShortVersionString": "1.2"}),
        )
        if nested:
            archive.writestr(
                "Payload/Demo.app/PlugIns/Widget.appex/Info.plist",
                plistlib.dumps({"CFBundleIdentifier": "com.example.widget"}),
            )


class IpaInspectionTests(unittest.TestCase):
    def test_matches_the_main_app_not_an_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.ipa"
            make_ipa(path)
            result = inspect_ipa(path, "com.example.app")
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["bundleIdentifier"], "com.example.app")
        self.assertEqual(result["version"], "1.2")

    def test_optional_compatibility_privacy_and_declared_entitlements(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.ipa"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "Payload/Demo.app/Info.plist",
                    plistlib.dumps(
                        {
                            "CFBundleIdentifier": "com.example.app",
                            "MinimumOSVersion": "16.4",
                            "NSCameraUsageDescription": "Scan codes",
                        }
                    ),
                )
                archive.writestr(
                    "Payload/Demo.app/Entitlements.plist",
                    plistlib.dumps({"com.apple.security.application-groups": ["group.demo"]}),
                )
            result = inspect_ipa(path, "com.example.app")
        self.assertEqual(result["minOSVersion"], "16.4")
        self.assertEqual(result["privacyUsageDescriptions"], {"NSCameraUsageDescription": "Scan codes"})
        self.assertEqual(result["declaredEntitlements"], ["com.apple.security.application-groups"])
        self.assertIn("not a verified", result["entitlementsNote"])

    def test_mismatch_is_not_reported_as_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.ipa"
            make_ipa(path)
            self.assertEqual(inspect_ipa(path, "com.example.other")["status"], "mismatch")
            self.assertEqual(inspect_ipa(path)["status"], "observed")

    def test_ambiguous_and_oversized_archives_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.ipa"
            make_ipa(path)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("Payload/Other.app/Info.plist", b"bad")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                inspect_ipa(path)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("Payload/Demo.app/Info.plist", b"x" * (MAX_INFO_PLIST_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "size limit"):
                inspect_ipa(path)

    def test_corrupt_and_malformed_plists_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.ipa"
            path.write_bytes(b"not a zip")
            with self.assertRaises(ValueError):
                inspect_ipa(path)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("Payload/Demo.app/Info.plist", b'<?xml version="1.0"?><plist><dict>')
            with self.assertRaises(ValueError):
                inspect_ipa(path)

    def test_cli_uses_catalog_slug_and_fails_on_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "example.ipa"
            make_ipa(path)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"apps": [{"slug": "demo", "bundleIdentifier": "com.example.other"}]}))
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/security/inspect_ipa.py"),
                    str(path),
                    "--slug",
                    "demo",
                    "--catalog",
                    str(catalog),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "mismatch")


if __name__ == "__main__":
    unittest.main()


class DownloadInspectionTests(unittest.TestCase):
    def test_verified_download_inspects_and_binds_permissions_to_bytes(self) -> None:
        import hashlib
        import io
        from types import SimpleNamespace

        from omnisource.domain import App, Catalog
        from omnisource.integrity import verify_downloads

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.ipa"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "Payload/Demo.app/Info.plist",
                    plistlib.dumps(
                        {
                            "CFBundleIdentifier": "com.example.app",
                            "MinimumOSVersion": "16.0",
                            "NSCameraUsageDescription": "Scan codes",
                        }
                    ),
                )
            body = path.read_bytes()
        app = App(slug="demo", raw={"name": "Demo", "bundleIdentifier": "com.example.app", "developerName": "Test"})
        catalog = Catalog(source={}, clients=[], apps=[app])
        url = "https://example.test/app.ipa"
        digest = hashlib.sha256(body).hexdigest()
        state = {"demo": {"versions": [{"version": "1.0", "downloadURL": url, "size": len(body), "sha256": digest}]}}
        container = SimpleNamespace(
            settings=SimpleNamespace(health_timeout=1),
            http=SimpleNamespace(open_stream=lambda *a, **k: io.BytesIO(body)),
        )
        records = verify_downloads(container, catalog, state, inspect=True)
        self.assertTrue(records[0]["ok"])
        self.assertEqual(records[0]["ipaInspection"]["status"], "match")
        version = state["demo"]["versions"][0]
        self.assertEqual(version["ipaInspection"]["sha256"], digest)
        self.assertEqual(
            version["ipaInspection"]["appPermissions"]["privacy"]["NSCameraUsageDescription"], "Scan codes"
        )
        self.assertNotIn("entitlements", version["ipaInspection"]["appPermissions"])

        app.raw["bundleIdentifier"] = "com.example.other"
        # An earlier inspection must not survive a new bundle-ID mismatch.
        records = verify_downloads(container, catalog, state, inspect=True)
        self.assertFalse(records[0]["ok"])
        self.assertIn("bundle ID mismatch", records[0]["detail"])
        self.assertNotIn("ipaInspection", state["demo"]["versions"][0])

    def test_truncated_stream_is_not_an_observation(self) -> None:
        import io
        from types import SimpleNamespace

        from omnisource.integrity import stream_hashes

        class Truncated(io.BytesIO):
            @property
            def headers(self):
                return {"Content-Length": "100"}

        http = SimpleNamespace(open_stream=lambda *args, **kwargs: Truncated(b"short"))
        with self.assertRaisesRegex(OSError, "incomplete download"):
            stream_hashes(http, "https://example.test/a.ipa")

    def test_spool_limit_does_not_prevent_hashing(self) -> None:
        import hashlib
        import io
        from types import SimpleNamespace

        from omnisource.integrity import stream_hashes

        body = b"x" * 20
        http = SimpleNamespace(open_stream=lambda *a, **k: io.BytesIO(body))
        with tempfile.TemporaryFile() as spool:
            result = stream_hashes(http, "https://example.test/a.ipa", spool=spool, spool_limit=5)
            self.assertFalse(result["spooled"])
            self.assertEqual(spool.tell(), 0)
            self.assertEqual(result["sha256"], hashlib.sha256(body).hexdigest())
