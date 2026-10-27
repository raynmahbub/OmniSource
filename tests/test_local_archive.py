import hashlib
import tempfile
import unittest
from pathlib import Path

from omnisource.archive import archive_release


class LocalArchiveTests(unittest.TestCase):
    def test_requires_opt_in_matching_bytes_and_external_destination(self):
        body = b"local test IPA bytes"
        digest = hashlib.sha256(body).hexdigest()
        url = "https://example.test/demo.ipa"
        catalog = {"apps": [{"slug": "demo", "archive": True}]}
        state = {
            "demo": {
                "versions": [{"version": "1", "size": len(body), "downloadURL": url, "sha256": digest}],
                "lastFullVerification": {
                    "at": "2026-10-27",
                    "url": url,
                    "expectedSize": len(body),
                    "expectedSha256": digest,
                    "sha256": digest,
                    "ok": True,
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            repo = parent / "repo"
            repo.mkdir()
            source = parent / "sample.ipa"
            source.write_bytes(body)
            kwargs = {
                "catalog": catalog,
                "state": state,
                "slug": "demo",
                "source": source,
                "destination": parent / "archive",
                "repo_root": repo,
                "confirm_rights": True,
                "quota": 1000,
            }
            with self.assertRaisesRegex(ValueError, "confirmation"):
                archive_release(**{**kwargs, "confirm_rights": False})
            with self.assertRaisesRegex(ValueError, "opted in"):
                archive_release(**{**kwargs, "catalog": {"apps": [{"slug": "demo"}]}})
            with self.assertRaisesRegex(ValueError, "outside"):
                archive_release(**{**kwargs, "destination": repo / "archive"})
            output = archive_release(**kwargs)
            self.assertEqual(output.read_bytes(), body)
            self.assertTrue((parent / "archive" / "manifest.json").is_file())
            source.write_bytes(b"x" * len(body))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                archive_release(**kwargs)
            self.assertEqual(output.read_bytes(), body)

    def test_unverified_or_wrong_url_is_rejected(self):
        digest = "a" * 64
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            source = parent / "app.ipa"
            source.write_bytes(b"x")
            state = {
                "demo": {
                    "versions": [
                        {"version": "1", "downloadURL": "https://example.test/new.ipa", "size": 1, "sha256": digest}
                    ],
                    "lastFullVerification": {
                        "at": "2026-10-27",
                        "url": "https://example.test/old.ipa",
                        "ok": True,
                        "expectedSha256": digest,
                        "sha256": digest,
                    },
                }
            }
            with self.assertRaisesRegex(ValueError, "verification"):
                archive_release(
                    catalog={"apps": [{"slug": "demo", "archive": True}]},
                    state=state,
                    slug="demo",
                    source=source,
                    destination=parent / "archive",
                    repo_root=parent / "repo",
                    confirm_rights=True,
                )


if __name__ == "__main__":
    unittest.main()
