"""Incremental sync must not mistake missing or unrelated releases for hits."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from omnisource.constants import Paths
from omnisource.di import Container
from omnisource.domain import App, Catalog, RemoteAsset, RemoteRelease, RepositoryRef, SourceType, SyncReport
from omnisource.errors import ProviderError
from omnisource.http import HttpClient
from omnisource.pipeline import stage_sync, sync_app
from omnisource.providers.base import INCREMENTAL_UNCHANGED
from omnisource.providers.failover import FailoverChain, leg_label
from omnisource.providers.feed import AltStoreFeedProvider
from omnisource.providers.gitea import GiteaReleasesProvider
from omnisource.providers.gitea import _newest_matching_url as gitea_newest
from omnisource.providers.github import GitHubReleasesProvider
from omnisource.providers.github import _newest_matching_url as github_newest
from omnisource.providers.gitlab import GitLabReleasesProvider
from omnisource.providers.gitlab import _newest_matching_url as gitlab_newest
from omnisource.providers.registry import ProviderRegistry


def release(version: str, url: str, name: str = "App.ipa") -> RemoteRelease:
    return RemoteRelease(
        tag=f"v{version}",
        name=version,
        body="",
        published_at="2026-10-01",
        assets=(RemoteAsset(name=name, download_url=url, size=100),),
    )


class FakeProvider:
    name = "github"
    source_type = SourceType.GITHUB_RELEASES

    def __init__(self, result: list[RemoteRelease]) -> None:
        self.result = result
        self.incremental: bool | None = None

    def fetch_releases(self, source, *, previous_latest_url=None, incremental=False):
        self.incremental = incremental
        return self.result


class FailoverIncrementalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.primary = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/app")
        self.mirror = RepositoryRef(provider=SourceType.MIRROR, feed_url="https://example.com/app.ipa")
        self.registry = ProviderRegistry()
        self.primary_provider = MagicMock(source_type=SourceType.GITHUB_RELEASES)
        self.mirror_provider = MagicMock(source_type=SourceType.MIRROR)
        self.registry.register(self.primary_provider)
        self.registry.register(self.mirror_provider)

    def test_url_match_stops_chain_without_trying_mirror(self) -> None:
        self.primary_provider.fetch_releases.return_value = INCREMENTAL_UNCHANGED
        result = FailoverChain(self.registry, [self.primary, self.mirror]).fetch_releases(
            incremental=True, previous_latest_url="https://example.com/app.ipa"
        )
        self.assertTrue(result.unchanged)
        self.assertEqual(result.source, leg_label(self.primary))
        self.assertFalse(result.used_failover)
        self.mirror_provider.fetch_releases.assert_not_called()

    def test_error_then_empty_mirror_is_not_an_incremental_hit(self) -> None:
        self.primary_provider.fetch_releases.side_effect = ProviderError("upstream missing")
        self.mirror_provider.fetch_releases.return_value = []
        with self.assertRaisesRegex(ProviderError, "upstream missing"):
            FailoverChain(self.registry, [self.primary, self.mirror]).fetch_releases(
                incremental=True, previous_latest_url="https://example.com/app.ipa"
            )

    def test_plain_empty_results_are_not_sentinels(self) -> None:
        self.primary_provider.fetch_releases.return_value = []
        result = FailoverChain(self.registry, [self.primary]).fetch_releases(
            incremental=True, previous_latest_url="https://example.com/app.ipa"
        )
        self.assertFalse(result.unchanged)
        self.assertEqual(result.releases, [])
        self.assertEqual(result.source, "")


class PipelineIncrementalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.http = MagicMock(spec=HttpClient)
        self.http.requests = 0
        self.previous = {"versions": [{"version": "2.0", "downloadURL": "https://example.com/current.ipa"}]}

    def app(self, keep_versions: int = 1) -> App:
        return App(
            slug="app",
            raw={
                "name": "App",
                "bundleIdentifier": "example.app",
                "upstream": {"provider": "github", "repo": "owner/app", "keepVersions": keep_versions},
                "manualRelease": {"version": "0.1", "downloadURL": "https://example.com/stale.ipa"},
            },
        )

    def container(self, provider: FakeProvider) -> Container:
        registry = ProviderRegistry()
        registry.register(provider)
        return Container(paths=Paths.from_root(Path(self.tmp.name)), http=self.http, providers=registry)

    def test_empty_and_unusable_releases_report_failure_keep_cache(self) -> None:
        for releases in ([], [release("3.0", "https://example.com/source.zip", "source.zip")]):
            with self.subTest(releases=releases):
                provider = FakeProvider(releases)
                app = self.app()
                state = {"app": {"versions": list(self.previous["versions"])}}
                report = SyncReport()
                stage_sync(
                    self.container(provider),
                    Catalog(source={}, clients=[], apps=[app]),
                    state,
                    only=None,
                    incremental=True,
                    report=report,
                    workers=1,
                )
                self.assertEqual(report.apps_failed, 1)
                self.assertEqual(report.apps_incremental_hit, 0)
                self.assertEqual(state["app"]["versions"], self.previous["versions"])
                self.assertIn("retaining cached versions", state["app"]["lastError"])

    def test_unchanged_sentinel_is_counted_as_hit(self) -> None:
        provider = FakeProvider(INCREMENTAL_UNCHANGED)
        app = self.app()
        state = {"app": {"versions": list(self.previous["versions"])}}
        report = SyncReport()
        stage_sync(
            self.container(provider),
            Catalog(source={}, clients=[], apps=[app]),
            state,
            only=None,
            incremental=True,
            report=report,
            workers=1,
        )
        self.assertEqual(report.apps_incremental_hit, 1)
        self.assertEqual(report.apps_failed, 0)
        self.assertEqual(state["app"]["lastResolvedSource"], "github:owner/app")
        self.assertEqual(state["app"]["versions"], self.previous["versions"])

    def test_new_entry_can_still_use_manual_fallback(self) -> None:
        versions, source = sync_app(self.container(FakeProvider([])), self.app(), incremental=True, previous=None)
        assert versions is not None
        self.assertEqual(source, "manual")
        self.assertEqual(versions[0]["downloadURL"], "https://example.com/stale.ipa")

    def test_new_entry_without_releases_or_fallback_is_a_failure(self) -> None:
        for releases in ([], [release("3.0", "https://example.com/source.zip", "source.zip")]):
            with self.subTest(releases=releases):
                app = self.app()
                app.raw.pop("manualRelease")
                state: dict = {}
                report = SyncReport()
                stage_sync(
                    self.container(FakeProvider(releases)),
                    Catalog(source={}, clients=[], apps=[app]),
                    state,
                    only=None,
                    incremental=True,
                    report=report,
                    workers=1,
                )
                self.assertEqual(report.apps_failed, 1)
                self.assertEqual(report.apps_synced, 0)
                self.assertIn("no manual fallback", state["app"]["lastError"])
                self.assertNotIn("versions", state["app"])

    def test_multiple_versions_always_refresh_even_if_newest_is_unchanged(self) -> None:
        for keep in (0, 2):
            with self.subTest(keep=keep):
                provider = FakeProvider(
                    [
                        release("2.0", "https://example.com/current.ipa"),
                        release("1.0", "https://example.com/older-new.ipa"),
                    ]
                )
                versions, _ = sync_app(
                    self.container(provider), self.app(keep), incremental=True, previous=self.previous
                )
                self.assertFalse(provider.incremental)
                assert versions is not None
                self.assertEqual(versions[1]["downloadURL"], "https://example.com/older-new.ipa")

    def test_unchanged_multi_version_full_refresh_is_not_counted_as_fast_path(self) -> None:
        provider = FakeProvider(
            [
                release("2.0", "https://example.com/current.ipa"),
                release("1.0", "https://example.com/older.ipa"),
            ]
        )
        app = self.app(2)
        container = self.container(provider)
        versions, _ = sync_app(container, app, incremental=False, previous=None)
        state = {"app": {"versions": versions}}
        report = SyncReport()
        stage_sync(
            container,
            Catalog(source={}, clients=[], apps=[app]),
            state,
            only=None,
            incremental=True,
            report=report,
            workers=1,
        )
        self.assertFalse(provider.incremental)
        self.assertEqual(report.apps_synced, 1)
        self.assertEqual(report.apps_incremental_hit, 0)


class ProviderCacheSafetyTests(unittest.TestCase):
    def github_payload(self) -> list[dict]:
        return [
            {
                "tag_name": "v2.0",
                "published_at": "2026-10-01T00:00:00Z",
                "assets": [
                    {"name": "A.ipa", "browser_download_url": "https://example.com/A.ipa", "size": 100},
                    {"name": "B.ipa", "browser_download_url": "https://example.com/B.ipa", "size": 100},
                ],
            }
        ]

    def test_shared_newest_match_applies_asset_name_pattern(self) -> None:
        multi = RemoteRelease(
            tag="v2",
            name="v2",
            body="",
            published_at="2026-10-01",
            assets=(
                RemoteAsset("A.ipa", "https://example.com/A.ipa", 100),
                RemoteAsset("B.ipa", "https://example.com/B.ipa", 100),
            ),
        )
        ref = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/app", asset_name_pattern=r"^B\.ipa$")
        for helper in (github_newest, gitlab_newest, gitea_newest):
            with self.subTest(helper=helper.__module__):
                self.assertEqual(helper([multi], ref), "https://example.com/B.ipa")

    def test_github_incremental_cache_is_bound_to_pattern_and_previous_url(self) -> None:
        http = MagicMock(spec=HttpClient)
        http.get_json.return_value = self.github_payload()
        provider = GitHubReleasesProvider(http)
        a = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/app", asset_name_pattern=r"^A\.ipa$")
        b = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/app", asset_name_pattern=r"^B\.ipa$")
        self.assertIs(
            provider.fetch_releases(a, incremental=True, previous_latest_url="https://example.com/A.ipa"),
            INCREMENTAL_UNCHANGED,
        )
        # The same previous URL but a different selection policy is not a hit.
        self.assertIsNot(
            provider.fetch_releases(b, incremental=True, previous_latest_url="https://example.com/A.ipa"),
            INCREMENTAL_UNCHANGED,
        )
        # A different cached URL must not reuse the first app's hit either.
        other_provider = GitHubReleasesProvider(http)
        self.assertIs(
            other_provider.fetch_releases(a, incremental=True, previous_latest_url="https://example.com/A.ipa"),
            INCREMENTAL_UNCHANGED,
        )
        self.assertTrue(
            other_provider.fetch_releases(a, incremental=True, previous_latest_url="https://example.com/old.ipa")
        )

    def test_feed_incremental_hit_has_explicit_sentinel(self) -> None:
        http = MagicMock(spec=HttpClient)
        http.get_json.return_value = {
            "apps": [
                {
                    "name": "App",
                    "bundleIdentifier": "example.app",
                    "version": "2.0",
                    "downloadURL": "https://example.com/App.ipa",
                    "size": 100,
                }
            ]
        }
        provider = AltStoreFeedProvider(http)
        ref = RepositoryRef(provider=SourceType.ALTSTORE, feed_url="https://example.com/feed.json", app_id="App")
        self.assertIs(
            provider.fetch_releases(ref, incremental=True, previous_latest_url="https://example.com/App.ipa"),
            INCREMENTAL_UNCHANGED,
        )

    def test_self_hosted_forge_cache_separates_hosts(self) -> None:
        for kind in ("gitlab", "forgejo"):
            with self.subTest(provider=kind):
                http = MagicMock(spec=HttpClient)

                def payload(url, provider_kind=kind):
                    host = "a" if "a.example" in url else "b"
                    asset_url = f"https://{host}.example/App.ipa"
                    if provider_kind == "gitlab":
                        return [
                            {
                                "tag_name": "v1",
                                "assets": {"links": [{"name": "App.ipa", "direct_asset_url": asset_url}]},
                            }
                        ]
                    return [{"tag_name": "v1", "assets": [{"name": "App.ipa", "download_url": asset_url}]}]

                http.get_json.side_effect = payload
                source_type = SourceType.GITLAB_RELEASES if kind == "gitlab" else SourceType.FORGEJO_RELEASES
                provider = (
                    GitLabReleasesProvider(http) if kind == "gitlab" else GiteaReleasesProvider(http, source_type)
                )
                a = RepositoryRef(provider=source_type, repo="owner/app", host="https://a.example")
                b = RepositoryRef(provider=source_type, repo="owner/app", host="https://b.example")
                self.assertEqual(provider.fetch_releases(a)[0].assets[0].download_url, "https://a.example/App.ipa")
                self.assertEqual(provider.fetch_releases(b)[0].assets[0].download_url, "https://b.example/App.ipa")
                self.assertEqual(http.get_json.call_count, 2)


class SyncWorkflowTests(unittest.TestCase):
    def test_daily_full_metadata_refresh_is_not_incremental(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "sync.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "0 6,12,18 * * *"', workflow)
        self.assertIn('cron: "0 0 * * *"', workflow)
        self.assertIn("EVENT_SCHEDULE: ${{ github.event.schedule }}", workflow)
        self.assertIn('[ "${EVENT_SCHEDULE}" != "0 0 * * *" ]', workflow)


if __name__ == "__main__":
    unittest.main()
