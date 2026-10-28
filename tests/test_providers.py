"""Tests for source providers and provider registry."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import unittest
from unittest.mock import MagicMock

from omnisource.domain import RemoteAsset, RemoteRelease, RepositoryRef, SourceType
from omnisource.errors import ProviderError
from omnisource.http import HttpClient
from omnisource.providers.feed import AltStoreFeedProvider
from omnisource.providers.github import GitHubReleasesProvider
from omnisource.providers.registry import build_default_registry
from omnisource.tracking import matched_release_dates
from omnisource.utils.dates import average_update_gap_days, version_dates


class TestProviders(unittest.TestCase):
    def setUp(self) -> None:
        self.http_mock = MagicMock(spec=HttpClient)
        self.registry = build_default_registry(self.http_mock)

    def test_registry_resolution(self) -> None:
        github_ref = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/repo")
        provider = self.registry.resolve(github_ref)
        self.assertIsInstance(provider, GitHubReleasesProvider)

        feed_ref = RepositoryRef(provider=SourceType.ALTSTORE, feed_url="https://example.com/repo.json")
        provider = self.registry.resolve(feed_ref)
        self.assertIsInstance(provider, AltStoreFeedProvider)

    def test_github_releases_provider(self) -> None:
        self.http_mock.get_json.return_value = [
            {
                "tag_name": "v1.0.0",
                "name": "Release 1.0.0",
                "body": "Test changelog",
                "published_at": "2026-09-07T10:00:00Z",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "App.ipa",
                        "browser_download_url": "https://example.com/App.ipa",
                        "size": 50000,
                        "content_type": "application/octet-stream",
                    }
                ],
            }
        ]
        provider = GitHubReleasesProvider(self.http_mock)
        ref = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/repo")
        releases = provider.fetch_releases(ref)
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].tag, "v1.0.0")
        self.assertEqual(len(releases[0].assets), 1)
        self.assertEqual(releases[0].assets[0].download_url, "https://example.com/App.ipa")

    def test_generic_feed_provider(self) -> None:
        self.http_mock.get_json.return_value = {
            "name": "Test Source",
            "identifier": "com.test.source",
            "apps": [
                {
                    "name": "Feed App",
                    "bundleIdentifier": "com.feed.app",
                    "version": "2.0.0",
                    "versionDate": "2026-09-07",
                    "downloadURL": "https://example.com/feedapp.ipa",
                    "size": 123456,
                    "localizedDescription": "Feed app description",
                    "versions": [
                        {
                            "version": "2.0.0",
                            "date": "2026-09-07",
                            "downloadURL": "https://example.com/feedapp.ipa",
                            "size": 123456,
                            "localizedDescription": "Feed app description",
                        }
                    ],
                }
            ],
        }
        provider = AltStoreFeedProvider(self.http_mock)
        ref = RepositoryRef(provider=SourceType.ALTSTORE, feed_url="https://example.com/repo.json")
        releases = provider.fetch_releases(ref)
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].tag, "2.0.0")

    def test_generic_feed_provider_missing_app_id_does_not_leak_sibling_apps(self) -> None:
        self.http_mock.get_json.return_value = {
            "name": "Multi App Source",
            "identifier": "com.multi.source",
            "apps": [
                {
                    "name": "Reddit (RedditFilter)",
                    "bundleIdentifier": "com.reddit.Reddit",
                    "versions": [
                        {
                            "version": "2026.42.1",
                            "date": "2026-10-21",
                            "downloadURL": "https://example.com/Reddit.ipa",
                            "size": 100000,
                        }
                    ],
                },
                {
                    "name": "Swiftgram (MxGram)",
                    "bundleIdentifier": "app.swiftgram.ios.mxgram",
                    "versions": [
                        {
                            "version": "13.0",
                            "date": "2026-10-13",
                            "downloadURL": "https://example.com/Swiftgram.ipa",
                            "size": 90000,
                        }
                    ],
                },
            ],
        }
        provider = AltStoreFeedProvider(self.http_mock)
        missing_ref = RepositoryRef(
            provider=SourceType.ALTSTORE,
            feed_url="https://example.com/multi.json",
            app_id="com.facebook.Facebook.glow",
        )
        self.assertEqual(provider.fetch_releases(missing_ref), [])
        for incremental in (False, True):
            with (
                self.subTest(incremental=incremental),
                self.assertRaisesRegex(ProviderError, "feed no longer contains tracked app"),
            ):
                provider.fetch_releases(
                    missing_ref, previous_latest_url="https://example.com/glow.ipa", incremental=incremental
                )

        matched_by_name = RepositoryRef(
            provider=SourceType.ALTSTORE,
            feed_url="https://example.com/multi.json",
            app_id="Swiftgram (MxGram)",
        )
        releases = provider.fetch_releases(matched_by_name)
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].tag, "13.0")

    def test_tracked_feed_entry_without_usable_release_is_not_an_incremental_hit(self) -> None:
        self.http_mock.get_json.return_value = {
            "apps": [{"name": "Feed App", "bundleIdentifier": "com.feed.app", "version": "2.0"}]
        }
        provider = AltStoreFeedProvider(self.http_mock)
        ref = RepositoryRef(
            provider=SourceType.ALTSTORE, feed_url="https://example.com/repo.json", app_id="com.feed.app"
        )
        for incremental in (False, True):
            with self.subTest(incremental=incremental), self.assertRaisesRegex(ProviderError, "no usable releases"):
                provider.fetch_releases(ref, previous_latest_url="https://example.com/old.ipa", incremental=incremental)

    def test_named_feed_entry_rejects_a_different_bundle_identifier(self) -> None:
        self.http_mock.get_json.return_value = {
            "apps": [
                {
                    "name": "Swiftgram (MxGram)",
                    "bundleIdentifier": "app.swiftgram.ios.mxgram",
                    "version": "13.0",
                    "downloadURL": "https://example.com/Swiftgram.ipa",
                }
            ]
        }
        provider = AltStoreFeedProvider(self.http_mock)
        ref = RepositoryRef(
            provider=SourceType.ALTSTORE,
            feed_url="https://example.com/multi.json",
            app_id="Swiftgram (MxGram)",
            expected_bundle_id="app.swiftgram.ios",
        )
        with self.assertRaisesRegex(ProviderError, "app.swiftgram.ios.mxgram.*catalog expects"):
            provider.fetch_releases(ref)

        matching = RepositoryRef(
            provider=SourceType.ALTSTORE,
            feed_url=ref.feed_url,
            app_id=ref.app_id,
            expected_bundle_id="app.swiftgram.ios.mxgram",
        )
        self.assertEqual(provider.fetch_releases(matching)[0].tag, "13.0")

    def test_feed_without_bundle_identifier_is_still_supported(self) -> None:
        self.http_mock.get_json.return_value = {
            "name": "Example",
            "version": "1.0",
            "downloadURL": "https://example.com/App.ipa",
        }
        ref = RepositoryRef(
            provider=SourceType.ALTSTORE,
            feed_url="https://example.com/app.json",
            app_id="Example",
            expected_bundle_id="com.example.app",
        )
        self.assertEqual(AltStoreFeedProvider(self.http_mock).fetch_releases(ref)[0].tag, "1.0")

    def test_ambiguous_named_feed_entry_cannot_mix_other_bundles(self) -> None:
        self.http_mock.get_json.return_value = {
            "apps": [
                {
                    "name": "Example",
                    "bundleIdentifier": bundle,
                    "version": "1.0",
                    "downloadURL": f"https://example.com/{bundle}.ipa",
                }
                for bundle in ("com.example.app", "com.other.app")
            ]
        }
        ref = RepositoryRef(
            provider=SourceType.ALTSTORE,
            feed_url="https://example.com/multi.json",
            app_id="Example",
            expected_bundle_id="com.example.app",
        )
        with self.assertRaisesRegex(ProviderError, "com.other.app"):
            AltStoreFeedProvider(self.http_mock).fetch_releases(ref)

    def test_matched_release_dates_feeds_cadence_series(self) -> None:
        ref = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/repo")
        releases = [
            RemoteRelease(
                tag="v1.2.0",
                name="v1.2.0",
                body="",
                published_at="2026-10-15T10:00:00Z",
                prerelease=False,
                draft=False,
                assets=[
                    RemoteAsset(
                        name="App.ipa",
                        download_url="https://example.com/App-1.2.0.ipa",
                        size=1000,
                    )
                ],
            ),
            RemoteRelease(
                tag="v1.1.0",
                name="v1.1.0",
                body="",
                published_at="2026-10-05T10:00:00Z",
                prerelease=False,
                draft=False,
                assets=[
                    RemoteAsset(
                        name="App.ipa",
                        download_url="https://example.com/App-1.1.0.ipa",
                        size=1000,
                    )
                ],
            ),
        ]
        dates = matched_release_dates(ref=ref, releases=releases)
        self.assertEqual(dates, ["2026-10-05", "2026-10-15"])
        state = {
            "testapp": {
                "versions": [{"version": "1.2.0", "date": "2026-10-15"}],
                "releaseDates": dates,
            }
        }
        parsed = version_dates(state, "testapp", include_history=True)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(average_update_gap_days(state, "testapp", include_history=True), 10.0)


if __name__ == "__main__":
    unittest.main()
