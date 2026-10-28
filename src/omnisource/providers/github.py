"""GitHub Releases and GitHub Tags providers."""

from __future__ import annotations

import re
import threading
import urllib.parse

from omnisource.constants import GITHUB_API_ROOT
from omnisource.domain import (
    AppMetadata,
    DiscoveredApp,
    RemoteAsset,
    RemoteRelease,
    RepositoryRef,
    SourceType,
    ValidationResult,
)
from omnisource.errors import ProviderError
from omnisource.http import HttpClient, github_accept_headers
from omnisource.logutil import log
from omnisource.providers.base import INCREMENTAL_UNCHANGED, SourceProvider
from omnisource.tracking import extract_sha256, pick_asset, release_is_eligible
from omnisource.utils.assets import detect_asset_metadata


def _sha_from_asset(raw: dict) -> str | None:
    digest = raw.get("digest")
    if isinstance(digest, str):
        return extract_sha256(digest)
    return None


def _asset_from_github(raw: dict) -> RemoteAsset | None:
    name = str(raw.get("name") or "")
    url = str(raw.get("browser_download_url") or "")
    if not name or not url:
        return None
    content_type = str(raw.get("content_type") or "")
    detected = detect_asset_metadata(name, url, mime_type=content_type)
    return RemoteAsset(
        name=name,
        download_url=url,
        size=int(raw.get("size") or 0),
        sha256=_sha_from_asset(raw),
        content_type=content_type,
        platform=str(detected["platform"]),
        architecture=detected["architecture"],
        file_type=str(detected["fileType"]),
        installable=bool(detected["installable"]),
        download_count=int(raw.get("download_count") or 0),
    )


def _release_from_github(raw: dict) -> RemoteRelease | None:
    if not isinstance(raw, dict):
        return None
    parsed = [_asset_from_github(item) for item in raw.get("assets") or [] if isinstance(item, dict)]
    assets = tuple(asset for asset in parsed if asset is not None)
    return RemoteRelease(
        tag=str(raw.get("tag_name") or ""),
        name=str(raw.get("name") or ""),
        body=str(raw.get("body") or ""),
        published_at=str(raw.get("published_at") or raw.get("created_at") or ""),
        assets=assets,
        prerelease=bool(raw.get("prerelease")),
        draft=bool(raw.get("draft")),
        release_url=str(raw.get("html_url") or "") or None,
        source="github",
    )


class GitHubReleasesProvider(SourceProvider):
    """GitHub Releases API. Per-run, per-repo cache so sibling apps share a fetch."""

    name = "github"
    source_type = SourceType.GITHUB_RELEASES

    def __init__(self, http: HttpClient) -> None:
        self.http = http
        self._cache: dict[tuple[str, int], list[RemoteRelease]] = {}
        self._incremental_hits: set[tuple[object, ...]] = set()
        self._cache_lock = threading.Lock()
        self.requests = 0

    def _get(self, path: str) -> object:
        url = f"{GITHUB_API_ROOT}{path}"
        payload = self.http.get_json(url, extra_headers=github_accept_headers())
        self.requests += 1
        return payload

    def validate_repository(self, source: RepositoryRef) -> ValidationResult:
        try:
            payload = self._get(f"/repos/{source.repo}")
        except ProviderError as error:
            return ValidationResult(False, str(error), f"https://github.com/{source.repo}")
        if not isinstance(payload, dict):
            return ValidationResult(False, "unexpected repository payload", f"https://github.com/{source.repo}")
        archived = bool(payload.get("archived"))
        detail = "ok" if not archived else "repository is archived"
        return ValidationResult(not archived, detail, str(payload.get("html_url") or ""), {"archived": archived})

    def discover_apps(self, source: RepositoryRef) -> list[DiscoveredApp]:
        if "/" in source.repo:
            meta = self.fetch_metadata(source)
            return [
                DiscoveredApp(
                    app_id=source.repo.split("/")[-1].lower(),
                    name=meta.name,
                    repository_url=f"https://github.com/{source.repo}",
                    source_type=self.source_type,
                    developer=meta.developer,
                    description=meta.description,
                )
            ]
        # Organisation / user listing, hard-capped so a typo cannot page forever.
        collected: list[DiscoveredApp] = []
        for page in range(1, min(source.max_pages, 5) + 1):
            batch = self._get(f"/users/{source.repo}/repos?per_page=100&page={page}&type=public")
            if not isinstance(batch, list) or not batch:
                break
            for item in batch:
                if not isinstance(item, dict) or item.get("archived") or item.get("fork"):
                    continue
                full = str(item.get("full_name") or "")
                collected.append(
                    DiscoveredApp(
                        app_id=str(item.get("name") or "").lower(),
                        name=str(item.get("name") or ""),
                        repository_url=str(item.get("html_url") or f"https://github.com/{full}"),
                        source_type=self.source_type,
                        developer=source.repo,
                        description=str(item.get("description") or ""),
                    )
                )
            if len(batch) < 100:
                break
        return collected

    def fetch_metadata(self, source: RepositoryRef) -> AppMetadata:
        payload = self._get(f"/repos/{source.repo}")
        if not isinstance(payload, dict):
            raise ProviderError(f"unexpected repository payload for {source.repo}")
        owner = payload.get("owner") if isinstance(payload.get("owner"), dict) else {}
        topics = payload.get("topics") if isinstance(payload.get("topics"), list) else []
        license_info = payload.get("license") if isinstance(payload.get("license"), dict) else {}
        return AppMetadata(
            name=str(payload.get("name") or source.repo),
            developer=str(owner.get("login") or source.repo.split("/")[0]),
            description=str(payload.get("description") or ""),
            icon=str(owner.get("avatar_url") or ""),
            homepage=str(payload.get("html_url") or ""),
            license=str(license_info.get("spdx_id") or ""),
            stars=int(payload.get("stargazers_count") or 0),
            topics=tuple(str(topic) for topic in topics),
            default_branch=str(payload.get("default_branch") or ""),
            archived=bool(payload.get("archived")),
        )

    def fetch_releases(
        self,
        source: RepositoryRef,
        *,
        previous_latest_url: str | None = None,
        incremental: bool = False,
    ) -> list[RemoteRelease]:
        cache_key = (source.repo, source.max_pages)
        policy_key = (
            *cache_key,
            source.tag_prefix,
            source.exclude_tag_prefixes,
            source.asset_suffixes,
            source.asset_name_pattern,
            previous_latest_url,
            source.include_prereleases,
            source.include_drafts,
        )
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
            if incremental and previous_latest_url and policy_key in self._incremental_hits:
                return INCREMENTAL_UNCHANGED

            collected: list[RemoteRelease] = []
            for page in range(1, source.max_pages + 1):
                url = f"/repos/{source.repo}/releases?per_page=100&page={page}"
                batch = self._get(url)
                if not isinstance(batch, list):
                    raise ProviderError(f"unexpected releases payload for {source.repo}")
                page_releases = [rel for item in batch if (rel := _release_from_github(item)) is not None]
                collected.extend(page_releases)

                if (
                    incremental
                    and previous_latest_url
                    and page == 1
                    and _newest_matching_url(page_releases, source) == previous_latest_url
                ):
                    log.debug("%s: incremental hit (latest asset unchanged)", source.repo)
                    # Do not cache a partial page-1 as the full history, but
                    # remember the hit so sibling apps do not repeat it.
                    self._incremental_hits.add(policy_key)
                    return INCREMENTAL_UNCHANGED

                if len(batch) < 100:
                    break

            published = [rel for rel in collected if rel.is_published]
            self._cache[cache_key] = published
            log.debug("%s: %d published releases", source.repo, len(published))
            return published


def _newest_matching_url(releases: list[RemoteRelease], source: RepositoryRef) -> str | None:
    pattern = re.compile(source.asset_name_pattern) if source.asset_name_pattern else None
    for release in releases:
        if not release_is_eligible(release, source):
            continue
        asset = pick_asset(release, source.asset_suffixes, pattern)
        if asset and asset.download_url:
            return asset.download_url
    return None


class GitHubTagsProvider(SourceProvider):
    """GitHub Git tags. Used when a project versions by tag rather than Release."""

    name = "github-tags"
    source_type = SourceType.GITHUB_TAGS

    def __init__(self, http: HttpClient) -> None:
        self.http = http
        self.releases_provider = GitHubReleasesProvider(http)
        self._cache: dict[tuple[str, int], list[RemoteRelease]] = {}
        self._incremental_hits: set[tuple[object, ...]] = set()
        self._cache_lock = threading.Lock()

    def validate_repository(self, source: RepositoryRef) -> ValidationResult:
        return self.releases_provider.validate_repository(source)

    def discover_apps(self, source: RepositoryRef) -> list[DiscoveredApp]:
        apps = self.releases_provider.discover_apps(source)
        return [
            DiscoveredApp(
                app_id=app.app_id,
                name=app.name,
                repository_url=app.repository_url,
                source_type=self.source_type,
                developer=app.developer,
                description=app.description,
            )
            for app in apps
        ]

    def fetch_metadata(self, source: RepositoryRef) -> AppMetadata:
        return self.releases_provider.fetch_metadata(source)

    def fetch_releases(
        self,
        source: RepositoryRef,
        *,
        previous_latest_url: str | None = None,
        incremental: bool = False,
    ) -> list[RemoteRelease]:
        cache_key = (source.repo, source.max_pages)
        policy_key = (
            *cache_key,
            source.tag_prefix,
            source.exclude_tag_prefixes,
            source.asset_suffixes,
            source.asset_name_pattern,
            previous_latest_url,
            source.include_prereleases,
            source.include_drafts,
        )
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
            if incremental and previous_latest_url and policy_key in self._incremental_hits:
                return INCREMENTAL_UNCHANGED

            # Prefer a real GitHub Release with the same tag when one exists,
            # so IPA assets still resolve. Fall back to the source archive URL.
            try:
                gh_releases = self.releases_provider.fetch_releases(source)
            except ProviderError:
                gh_releases = []
            by_tag = {rel.tag: rel for rel in gh_releases}

            collected: list[RemoteRelease] = []
            for page in range(1, source.max_pages + 1):
                batch = self.releases_provider._get(f"/repos/{source.repo}/tags?per_page=100&page={page}")
                if not isinstance(batch, list):
                    raise ProviderError(f"unexpected tags payload for {source.repo}")
                for item in batch:
                    if not isinstance(item, dict):
                        continue
                    tag = str(item.get("name") or "")
                    if not tag:
                        continue
                    if tag in by_tag:
                        collected.append(by_tag[tag])
                        continue
                    commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
                    sha = str(commit.get("sha") or "")
                    archive = (
                        f"https://github.com/{source.repo}/archive/refs/tags/{urllib.parse.quote(tag, safe='')}.zip"
                    )
                    collected.append(
                        RemoteRelease(
                            tag=tag,
                            name=tag,
                            body="",
                            published_at="",
                            assets=(RemoteAsset(name=f"{tag}.zip", download_url=archive, size=0),),
                            build_number=sha[:7] if sha else None,
                            release_url=(
                                f"https://github.com/{source.repo}/releases/tag/{urllib.parse.quote(tag, safe='')}"
                            ),
                            source="github-tags",
                        )
                    )
                if (
                    incremental
                    and previous_latest_url
                    and page == 1
                    and collected
                    and _newest_matching_url(collected, source) == previous_latest_url
                ):
                    self._incremental_hits.add(policy_key)
                    return INCREMENTAL_UNCHANGED
                if len(batch) < 100:
                    break
            self._cache[cache_key] = collected
            return collected
