"""Tests for Phase 2 redundancy: GitLab, Gitea (Codeberg/Forgejo), Direct-URL,
Mirror, archive.org providers and the failover chain."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import unittest

from omnisource.domain import RepositoryRef, SourceType
from omnisource.errors import ConfigurationError, ProviderError
from omnisource.http import HttpClient, ProbeResult
from omnisource.providers.direct import ArchiveProvider, DirectURLProvider
from omnisource.providers.failover import FailoverChain, leg_label
from omnisource.providers.gitea import GiteaReleasesProvider
from omnisource.providers.gitlab import GitLabReleasesProvider
from omnisource.providers.registry import build_default_registry

UP_REACHABLE = ProbeResult(reachable=True, detail="HTTP 200", url="")
UP_DEAD = ProbeResult(reachable=False, detail="HTTP 404", url="")


class _Http:
    """A small fake standing in for HttpClient."""

    def __init__(self, payloads: dict[str, object] | None = None, *, reachable: bool = True) -> None:
        self.payloads = payloads or {}
        self.probe = MagicMock(return_value=UP_REACHABLE if reachable else UP_DEAD)
        self.requests = 0

    def get_json(self, url: str, *args, **kwargs) -> object:
        self.requests += 1
        for key, value in self.payloads.items():
            if key in url:
                return value
        raise ProviderError(f"unexpected URL {url}")


def _gitlab_ref(**overrides) -> RepositoryRef:
    return RepositoryRef(
        provider=SourceType.GITLAB_RELEASES,
        repo="group/project",
        **overrides,
    )


class GitLabProviderTests(unittest.TestCase):
    def test_fetch_releases(self) -> None:
        http = _Http(
            {
                "/releases": [
                    {
                        "tag_name": "v2.1.0",
                        "name": "2.1.0",
                        "description": "changelog",
                        "released_at": "2026-09-01T10:00:00Z",
                        "created_at": "2026-09-01T10:00:00Z",
                        "draft": False,
                        "assets": {
                            "links": [
                                {
                                    "name": "app.ipa",
                                    "url": "https://gitlab.example/api/v4/projects/1/packages/generic/a.ipa",
                                    "direct_asset_url": "https://gitlab.example/direct/app.ipa",
                                    "size": 42000,
                                }
                            ]
                        },
                    }
                ]
            }
        )
        provider = GitLabReleasesProvider(http)
        releases = provider.fetch_releases(_gitlab_ref())
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].tag, "v2.1.0")
        self.assertEqual(releases[0].assets[0].download_url, "https://gitlab.example/direct/app.ipa")
        self.assertEqual(releases[0].assets[0].size, 42000)
        self.assertEqual(releases[0].source, "gitlab")

    def test_validate_repository_missing(self) -> None:
        http = _Http()
        http.get_json = MagicMock(side_effect=ProviderError("404"))
        provider = GitLabReleasesProvider(http)
        result = provider.validate_repository(_gitlab_ref())
        self.assertFalse(result.ok)

    def test_custom_host(self) -> None:
        http = _Http({"gitlab.example.com/api/v4": [{"tag_name": "v1"}]})
        provider = GitLabReleasesProvider(http)
        ref = _gitlab_ref(host="https://gitlab.example.com")
        provider.fetch_releases(ref)
        self.assertIn("gitlab.example.com", " ".join(http.payloads))


class GiteaProviderTests(unittest.TestCase):
    def test_codeberg_default_host(self) -> None:
        http = _Http({"codeberg.org/api/v1": [{"tag_name": "v1.0"}]})
        provider = GiteaReleasesProvider(http, SourceType.CODEBERG_RELEASES)
        ref = RepositoryRef(provider=SourceType.CODEBERG_RELEASES, repo="org/app")
        releases = provider.fetch_releases(ref)
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].source, "gitea")
        self.assertEqual(provider.name, "codeberg")

    def test_forgejo_requires_host(self) -> None:
        http = _Http()
        provider = GiteaReleasesProvider(http, SourceType.FORGEJO_RELEASES)
        ref = RepositoryRef(provider=SourceType.FORGEJO_RELEASES, repo="org/app")
        with self.assertRaises(ProviderError):
            provider.fetch_releases(ref)

    def test_releases_shape(self) -> None:
        http = _Http(
            {
                "/releases": [
                    {
                        "tag_name": "v3.3",
                        "name": "3.3",
                        "body": "notes",
                        "published_at": "2026-08-01T00:00:00Z",
                        "prerelease": False,
                        "assets": [
                            {"name": "app.ipa", "download_url": "https://forge.example/dl/app.ipa", "size": 999}
                        ],
                    }
                ]
            }
        )
        provider = GiteaReleasesProvider(http, SourceType.FORGEJO_RELEASES)
        ref = RepositoryRef(provider=SourceType.FORGEJO_RELEASES, repo="org/app", host="https://forge.example")
        releases = provider.fetch_releases(ref)
        self.assertEqual(releases[0].assets[0].download_url, "https://forge.example/dl/app.ipa")


class DirectProviderTests(unittest.TestCase):
    def test_fetch_returns_single_release(self) -> None:
        http = _Http(reachable=True)
        provider = DirectURLProvider(http, SourceType.DIRECT)
        ref = RepositoryRef(
            provider=SourceType.DIRECT,
            feed_url="https://cdn.example.com/app-1.2.3.ipa",
            version="1.2.3",
            version_date="2026-08-15",
        )
        releases = provider.fetch_releases(ref)
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].tag, "1.2.3")
        self.assertEqual(releases[0].published_at, "2026-08-15")
        self.assertEqual(releases[0].assets[0].download_url, "https://cdn.example.com/app-1.2.3.ipa")
        http.probe.assert_called_once()

    def test_unreachable_raises(self) -> None:
        http = _Http(reachable=False)
        provider = DirectURLProvider(http, SourceType.DIRECT)
        ref = RepositoryRef(provider=SourceType.DIRECT, feed_url="https://cdn.example.com/gone.ipa")
        with self.assertRaises(ProviderError):
            provider.fetch_releases(ref)

    def test_missing_url_raises(self) -> None:
        http = _Http()
        provider = DirectURLProvider(http, SourceType.MIRROR)
        ref = RepositoryRef(provider=SourceType.MIRROR)
        with self.assertRaises(ProviderError):
            provider.fetch_releases(ref)

    def test_incremental_unchanged(self) -> None:
        http = _Http(reachable=True)
        provider = DirectURLProvider(http, SourceType.MIRROR)
        ref = RepositoryRef(provider=SourceType.MIRROR, feed_url="https://cdn.example.com/same.ipa")
        url = "https://cdn.example.com/same.ipa"
        self.assertEqual(provider.fetch_releases(ref, previous_latest_url=url, incremental=True), [])


class ArchiveProviderTests(unittest.TestCase):
    def _metadata(self) -> dict:
        return {
            "metadata": {"title": "My App", "creator": "dev", "date": "2026-07-01", "version": "9.9"},
            "files": [
                {"name": "app-old.ipa", "size": "1000", "created": "2025-01-01T00:00:00"},
                {"name": "app-new.ipa", "size": "2000", "created": "2026-07-01T00:00:00"},
                {"name": "readme.txt", "size": "10"},
            ],
        }

    def test_selects_newest_ipa(self) -> None:
        http = _Http({"archive.org/metadata/": self._metadata()})
        provider = ArchiveProvider(http)
        ref = RepositoryRef(provider=SourceType.ARCHIVE, feed_url="https://archive.org/details/my-app")
        releases = provider.fetch_releases(ref)
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].tag, "9.9")
        self.assertIn("app-new.ipa", releases[0].assets[0].download_url)
        self.assertEqual(releases[0].assets[0].size, 2000)
        self.assertEqual(releases[0].published_at, "2026-07-01")

    def test_bare_item_id(self) -> None:
        http = _Http({"archive.org/metadata/my-app": self._metadata()})
        provider = ArchiveProvider(http)
        ref = RepositoryRef(provider=SourceType.ARCHIVE, feed_url="my-app")
        self.assertEqual(len(provider.fetch_releases(ref)), 1)

    def test_validate(self) -> None:
        http = _Http({"archive.org/metadata/": self._metadata()})
        provider = ArchiveProvider(http)
        ref = RepositoryRef(provider=SourceType.ARCHIVE, feed_url="https://archive.org/details/my-app")
        self.assertTrue(provider.validate_repository(ref).ok)


class FailoverChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry(MagicMock(spec=HttpClient))

    def _chain(self, *refs: RepositoryRef) -> FailoverChain:
        return FailoverChain(self.registry, list(refs))

    def test_single_leg_success(self) -> None:
        http = _Http({"/releases": [{"tag_name": "v1", "assets": []}]})
        primary = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/repo")
        chain = self._chain(primary)
        # Replace registry provider with one backed by the fake http.
        from omnisource.providers.github import GitHubReleasesProvider

        self.registry._providers[SourceType.GITHUB_RELEASES] = GitHubReleasesProvider(http)
        result = chain.fetch_releases()
        self.assertEqual(len(result.releases), 1)
        self.assertEqual(result.attempts[0], f"ok {leg_label(primary)} (1 release(s))")
        self.assertFalse(result.used_failover)

    def test_primary_failure_fails_over_to_mirror(self) -> None:
        # Primary: a github repo that errors. Mirror: a direct URL that works.
        from omnisource.providers.github import GitHubReleasesProvider

        bad_http = MagicMock(spec=HttpClient)
        bad_http.get_json = MagicMock(side_effect=ProviderError("api down"))
        self.registry._providers[SourceType.GITHUB_RELEASES] = GitHubReleasesProvider(bad_http)

        good_http = _Http(reachable=True)
        self.registry._providers[SourceType.MIRROR] = DirectURLProvider(good_http, SourceType.MIRROR)

        primary = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/repo")
        mirror = RepositoryRef(provider=SourceType.MIRROR, feed_url="https://mirror.example.com/app.ipa", version="1.0")
        chain = self._chain(primary, mirror)
        result = chain.fetch_releases()
        self.assertEqual(len(result.releases), 1)
        self.assertTrue(result.used_failover)
        self.assertTrue(any("error" in attempt for attempt in result.attempts))
        self.assertEqual(result.source, leg_label(mirror))

    def test_all_fail_raises(self) -> None:
        from omnisource.providers.github import GitHubReleasesProvider

        bad_http = MagicMock(spec=HttpClient)
        bad_http.get_json = MagicMock(side_effect=ProviderError("down"))
        self.registry._providers[SourceType.GITHUB_RELEASES] = GitHubReleasesProvider(bad_http)
        self.registry._providers[SourceType.MIRROR] = DirectURLProvider(_Http(reachable=False), SourceType.MIRROR)

        primary = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/repo")
        mirror = RepositoryRef(provider=SourceType.MIRROR, feed_url="https://mirror.example.com/app.ipa")
        with self.assertRaises(ProviderError):
            self._chain(primary, mirror).fetch_releases()

    def test_empty_primary_falls_through_to_empty_mirror(self) -> None:
        from omnisource.providers.github import GitHubReleasesProvider

        empty_http = _Http({"/releases": []})
        self.registry._providers[SourceType.GITHUB_RELEASES] = GitHubReleasesProvider(empty_http)
        self.registry._providers[SourceType.GITHUB_TAGS] = GitHubReleasesProvider(empty_http)
        primary = RepositoryRef(provider=SourceType.GITHUB_RELEASES, repo="owner/repo")
        mirror = RepositoryRef(provider=SourceType.GITHUB_TAGS, repo="owner/repo")
        result = self._chain(primary, mirror).fetch_releases()
        self.assertEqual(result.releases, [])
        self.assertFalse(result.source)
        self.assertEqual(result.attempts, [f"{leg_label(primary)} empty", f"{leg_label(mirror)} empty"])

    def test_from_ref_builds_mirrors_with_inherited_policy(self) -> None:
        primary = RepositoryRef(
            provider=SourceType.GITHUB_RELEASES,
            repo="owner/repo",
            asset_suffixes=(".custom.ipa",),
            keep_versions=2,
            expected_bundle_id="com.example.app",
            mirrors=({"provider": "mirror", "url": "https://m.example.com/app.custom.ipa"},),
        )
        chain = FailoverChain.from_ref(self.registry, primary)
        self.assertEqual(len(chain.legs), 2)
        mirror = chain.legs[1]
        self.assertEqual(mirror.provider, SourceType.MIRROR)
        self.assertEqual(mirror.feed_url, "https://m.example.com/app.custom.ipa")
        self.assertEqual(mirror.asset_suffixes, (".custom.ipa",))
        self.assertEqual(mirror.keep_versions, 2)
        self.assertEqual(mirror.expected_bundle_id, "com.example.app")

    def test_mirrors_missing_provider_rejected(self) -> None:
        primary = RepositoryRef(
            provider=SourceType.GITHUB_RELEASES,
            repo="owner/repo",
            mirrors=({"url": "https://m.example.com/app.ipa"},),
        )
        with self.assertRaises(ConfigurationError):
            FailoverChain.from_ref(self.registry, primary)

    def test_empty_chain_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            FailoverChain(self.registry, [])


class RegistryCoverageTests(unittest.TestCase):
    def test_every_registered_source_type_resolves(self) -> None:
        http = MagicMock(spec=HttpClient)
        registry = build_default_registry(http)
        for source_type in SourceType:
            if source_type == SourceType.MANUAL:
                continue
            self.assertIn(source_type, registry, f"missing provider for {source_type}")

    def test_verify_alias(self) -> None:
        http = _Http(reachable=True)
        provider = DirectURLProvider(http, SourceType.DIRECT)
        ref = RepositoryRef(provider=SourceType.DIRECT, feed_url="https://cdn.example.com/a.ipa")
        self.assertTrue(provider.verify(ref).ok)


class RepositoryRefParseTests(unittest.TestCase):
    def test_url_alias_and_version(self) -> None:
        ref = RepositoryRef.parse(
            {
                "provider": "mirror",
                "url": "https://m.example.com/a.ipa",
                "version": "2.0",
                "versionDate": "2026-01-02",
            }
        )
        self.assertEqual(ref.provider, SourceType.MIRROR)
        self.assertEqual(ref.feed_url, "https://m.example.com/a.ipa")
        self.assertEqual(ref.version, "2.0")
        self.assertEqual(ref.version_date, "2026-01-02")
        self.assertTrue(ref.is_url_source)

    def test_mirrors_parsed(self) -> None:
        ref = RepositoryRef.parse(
            {
                "provider": "github",
                "repo": "o/r",
                "mirrors": [{"provider": "archive", "url": "https://archive.org/details/x"}],
            }
        )
        self.assertEqual(len(ref.mirrors), 1)
        self.assertEqual(ref.mirrors[0]["provider"], "archive")

    def test_url_source_requires_url(self) -> None:
        with self.assertRaises(ConfigurationError):
            RepositoryRef.parse({"provider": "direct"})


if __name__ == "__main__":
    unittest.main()
