"""GitLab Releases provider.

Covers ``gitlab.com`` and self-hosted GitLab (``upstream.host``). The v4
releases API is shape-compatible with the GitHub adapter: paged releases with
asset links, per-repo caching, and the incremental page-1 fast path.
"""

from __future__ import annotations

import re
import threading
import urllib.parse

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
from omnisource.http import HttpClient
from omnisource.logutil import log
from omnisource.providers.base import INCREMENTAL_UNCHANGED, SourceProvider
from omnisource.tracking import pick_asset, release_is_eligible
from omnisource.utils.assets import detect_asset_metadata


def _project_path(repo: str) -> str:
    """URL-encode ``owner/name`` (supports nested groups) for the v4 API."""
    return urllib.parse.quote(str(repo or ""), safe="")


def _license_name(raw: object) -> str:
    return str(raw.get("name") or "") if isinstance(raw, dict) else ""


def _asset_from_gitlab(raw: dict) -> RemoteAsset | None:
    url = str(raw.get("direct_asset_url") or raw.get("url") or "")
    name = str(raw.get("name") or "")
    if not url:
        return None
    if not name:
        name = url.rsplit("/", 1)[-1].split("?", 1)[0] or "asset"
    detected = detect_asset_metadata(name, url, mime_type=str(raw.get("content_type") or ""))
    return RemoteAsset(
        name=name,
        download_url=url,
        size=int(raw.get("size") or 0),
        sha256=None,  # the releases API does not publish digests
        content_type=str(raw.get("content_type") or ""),
        platform=str(detected["platform"]),
        architecture=detected["architecture"],
        file_type=str(detected["fileType"]),
        installable=bool(detected["installable"]),
    )


def _release_from_gitlab(raw: dict) -> RemoteRelease | None:
    if not isinstance(raw, dict):
        return None
    assets_block = raw.get("assets")
    links = assets_block.get("links") if isinstance(assets_block, dict) else []
    parsed = [_asset_from_gitlab(item) for item in links or [] if isinstance(item, dict)]
    assets = tuple(asset for asset in parsed if asset is not None)
    return RemoteRelease(
        tag=str(raw.get("tag_name") or ""),
        name=str(raw.get("name") or ""),
        body=str(raw.get("description") or ""),
        published_at=str(raw.get("released_at") or raw.get("created_at") or ""),
        assets=assets,
        prerelease=False,
        draft=bool(raw.get("draft")),
        release_url=str(raw.get("_links", {}).get("self") or "") or None,
        source="gitlab",
    )


class GitLabReleasesProvider(SourceProvider):
    """GitLab v4 Releases API (gitlab.com or self-hosted via ``upstream.host``)."""

    name = "gitlab"
    source_type = SourceType.GITLAB_RELEASES
    DEFAULT_HOST = "https://gitlab.com"

    def __init__(self, http: HttpClient) -> None:
        self.http = http
        self._cache: dict[tuple[str, str, int], list[RemoteRelease]] = {}
        self._incremental_hits: set[tuple[object, ...]] = set()
        self._cache_lock = threading.Lock()
        self.requests = 0

    def _host(self, source: RepositoryRef) -> str:
        return (source.host or self.DEFAULT_HOST).rstrip("/")

    def _get(self, source: RepositoryRef, path: str) -> object:
        url = f"{self._host(source)}/api/v4{path}"
        payload = self.http.get_json(url)
        self.requests += 1
        return payload

    def _releases_path(self, source: RepositoryRef, page: int) -> str:
        return f"/projects/{_project_path(source.repo)}/releases?per_page=100&page={page}"

    def validate_repository(self, source: RepositoryRef) -> ValidationResult:
        url = f"{self._host(source)}/-{source.repo}" if source.repo else self._host(source)
        try:
            payload = self._get(source, f"/projects/{_project_path(source.repo)}")
        except ProviderError as error:
            return ValidationResult(False, str(error), url)
        if not isinstance(payload, dict) or payload.get("archived"):
            return ValidationResult(False, "project missing or archived", url)
        return ValidationResult(True, "ok", str(payload.get("web_url") or url))

    def discover_apps(self, source: RepositoryRef) -> list[DiscoveredApp]:
        if "/" in source.repo:
            meta = self.fetch_metadata(source)
            return [
                DiscoveredApp(
                    app_id=source.repo.split("/")[-1].lower(),
                    name=meta.name,
                    repository_url=f"{self._host(source)}/{source.repo}",
                    source_type=self.source_type,
                    developer=meta.developer,
                    description=meta.description,
                )
            ]
        collected: list[DiscoveredApp] = []
        for page in range(1, min(source.max_pages, 5) + 1):
            group = urllib.parse.quote(source.repo, safe="")
            path = f"/groups/{group}/projects?per_page=100&page={page}&archived=false"
            batch = self._get(source, path)
            if not isinstance(batch, list) or not batch:
                break
            for item in batch:
                if not isinstance(item, dict):
                    continue
                collected.append(
                    DiscoveredApp(
                        app_id=str(item.get("path") or "").lower(),
                        name=str(item.get("name") or ""),
                        repository_url=str(item.get("web_url") or ""),
                        source_type=self.source_type,
                        developer=source.repo,
                        description=str(item.get("description") or ""),
                    )
                )
            if len(batch) < 100:
                break
        return collected

    def fetch_metadata(self, source: RepositoryRef) -> AppMetadata:
        payload = self._get(source, f"/projects/{_project_path(source.repo)}")
        if not isinstance(payload, dict):
            raise ProviderError(f"unexpected project payload for {source.repo}")
        namespace = payload.get("namespace") if isinstance(payload.get("namespace"), dict) else {}
        return AppMetadata(
            name=str(payload.get("name") or source.repo),
            developer=str(namespace.get("full_path") or source.repo.split("/")[0]),
            description=str(payload.get("description") or ""),
            icon=str(payload.get("avatar_url") or ""),
            homepage=str(payload.get("web_url") or ""),
            license=_license_name(payload.get("license")),
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
        cache_key = (self._host(source), source.repo, source.max_pages)
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
                batch = self._get(source, self._releases_path(source, page))
                if not isinstance(batch, list):
                    raise ProviderError(f"unexpected releases payload for {source.repo}")
                page_releases = [rel for item in batch if (rel := _release_from_gitlab(item)) is not None]
                collected.extend(page_releases)

                if (
                    incremental
                    and previous_latest_url
                    and page == 1
                    and _newest_matching_url(page_releases, source) == previous_latest_url
                ):
                    log.debug("%s: incremental hit (latest asset unchanged)", source.repo)
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
