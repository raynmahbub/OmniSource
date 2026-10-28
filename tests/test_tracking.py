"""Tests for tracking engine: version extraction, asset picking, and update detection."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import unittest

from omnisource.domain import RemoteAsset, RemoteRelease, RepositoryRef, SourceType
from omnisource.tracking import (
    build_version_entry,
    detect_update,
    extract_changelog,
    extract_sha256,
    matches_tag_rules,
    pick_asset,
    tag_number,
    version_numbers,
)


class TestTracking(unittest.TestCase):
    def test_extract_sha256(self) -> None:
        raw_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertEqual(extract_sha256(f"sha256: {raw_hash}"), raw_hash)
        self.assertEqual(extract_sha256(f"SHA256SUM: {raw_hash.upper()}"), raw_hash)
        self.assertEqual(extract_sha256(raw_hash), raw_hash)
        self.assertIsNone(extract_sha256("no hash here"))

    def test_extract_changelog(self) -> None:
        body = "Line 1\r\nLine 2\r\nLine 3"
        self.assertEqual(extract_changelog(body), "Line 1\nLine 2\nLine 3")

    def test_tag_number(self) -> None:
        self.assertEqual(tag_number("ytl-ipa4"), 4)
        self.assertEqual(tag_number("v1.2.3"), 3)
        self.assertEqual(tag_number("no-digits"), -1)

    def test_pick_asset(self) -> None:
        assets = (
            RemoteAsset(name="app.apk", download_url="https://example.com/app.apk"),
            RemoteAsset(name="app.ipa", download_url="https://example.com/app.ipa"),
        )
        release = RemoteRelease(tag="v1.0", name="1.0", body="", published_at="", assets=assets)
        picked = pick_asset(release, (".ipa",))
        self.assertIsNotNone(picked)
        self.assertEqual(picked.name, "app.ipa")

    def test_matches_tag_rules(self) -> None:
        ref = RepositoryRef(
            provider=SourceType.GITHUB_RELEASES,
            repo="owner/repo",
            tag_prefix="v",
            exclude_tag_prefixes=("v0.",),
        )
        self.assertTrue(matches_tag_rules("v1.0.0", ref))
        self.assertFalse(matches_tag_rules("1.0.0", ref))
        self.assertFalse(matches_tag_rules("v0.9.0", ref))

    def test_version_numbers_pattern(self) -> None:
        release = RemoteRelease(
            tag="v0.9.2",
            name="YTKACE 0.9.2",
            body="",
            published_at="",
        )
        asset_name = "YTKACE_0.9.2_YouTube_21.35.3.ipa"
        numbers = version_numbers(
            release,
            asset_name,
            from_tag=False,
            version_pattern=r"YouTube_(\d+\.\d+(?:\.\d+)?)",
        )
        self.assertEqual(numbers[0], "21.35.3")

    def test_build_version_entry(self) -> None:
        ref = RepositoryRef(
            provider=SourceType.GITHUB_RELEASES,
            repo="owner/repo",
            version_from_tag=True,
            description_template="{name} {version} | {label}",
        )
        asset = RemoteAsset(
            name="TestApp.ipa",
            download_url="https://example.com/TestApp.ipa",
            size=12345,
            sha256="a" * 64,
        )
        release = RemoteRelease(
            tag="v2.5.0",
            name="Release 2.5.0",
            body="Bug fixes",
            published_at="2026-09-07T12:00:00Z",
            assets=(asset,),
        )
        entry = build_version_entry(app_name="TestApp", ref=ref, release=release, asset=asset)
        self.assertEqual(entry["version"], "2.5.0")
        self.assertEqual(entry["date"], "2026-09-07")
        self.assertEqual(entry["downloadURL"], "https://example.com/TestApp.ipa")
        self.assertEqual(entry["size"], 12345)
        self.assertEqual(entry["sha256"], "a" * 64)
        self.assertIn("TestApp 2.5.0 | TestApp", entry["localizedDescription"])

    def test_asset_specific_min_os_overrides_mutable_tags(self) -> None:
        ref = RepositoryRef.parse(
            {
                "repo": "owner/repo",
                "minOSVersion": "17.0",
                "minOSVersionByTagNumber": {"1": "14.0"},
                "minOSVersionByAssetName": {"app_21.33.6_6.0b2.ipa": "16.0"},
            }
        )

        def minimum(filename: str, tag: str) -> str:
            asset = RemoteAsset(name=filename, download_url="https://example.com/app.ipa")
            release = RemoteRelease(tag=tag, name="", body="", published_at="", assets=(asset,))
            return str(build_version_entry(app_name="App", ref=ref, release=release, asset=asset)["minOSVersion"])

        self.assertEqual(minimum("app_21.33.6_6.0b2.ipa", "ytl-ipa1"), "16.0")  # asset beats tag
        self.assertEqual(minimum("app_21.33.6_6.0b2.ipa", "ytl-ipa9"), "16.0")  # renumbered tag
        self.assertEqual(minimum("app_20.21.6.ipa", "ytl-ipa1"), "14.0")  # legacy tag rule
        self.assertEqual(minimum("app_21.33.6_6.1.ipa", "ytl-ipa9"), "17.0")  # new build, same base version

    def test_detect_update(self) -> None:
        prev = [{"version": "1.0.0", "downloadURL": "https://example.com/v1.ipa"}]
        curr = [{"version": "1.1.0", "downloadURL": "https://example.com/v11.ipa"}]
        self.assertEqual(detect_update(prev, curr), "updated")

        curr_same = [{"version": "1.0.0", "downloadURL": "https://example.com/v1.ipa"}]
        self.assertEqual(detect_update(prev, curr_same), "unchanged")

        self.assertEqual(detect_update(None, curr), "new")


if __name__ == "__main__":
    unittest.main()
