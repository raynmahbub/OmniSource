"""Gitea Releases provider — serves Codeberg and any Forgejo instance.

The Gitea API v1 release shape (``repos/{owner}/{name}/releases``) is shared
by codeberg.org and self-hosted Forgejo; ``upstream.host`` selects the server
(required for ``forgejo``, defaulted for ``codeberg``).
"""

from __future__ import annotations

import re
import threading

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

# Host -> (provider display name, default host) for the two registered kinds.
GITEA_HOSTS = {
    SourceType.CODEBERG_RELEASES: ("codeberg", "https://codeberg.org"),
    SourceType.FORGEJO_RELEASES: ("forgejo", ""),
}


def _asset_from_gitea(raw: dict) -> RemoteAsset | None:
    url = str(raw.get("download_url") or "")
    name = str(raw.get("name") or "")
    if not url or not name:
        return None
    detected = detect_asset_metadata(name, url, mime_type=str(raw.get("content_type") or ""))
    return RemoteAsset(
        name=name,
        download_url=url,
        size=int(raw.get("size") or 0),
        sha256=None,  # the Gitea API does not publish digests
        content_type=str(raw.get("content_type") or ""),
        platform=str(detected["platform"]),
        architecture=detected["architecture"],
        file_type=str(detected["fileType"]),
        installable=bool(detected["installable"]),
    )


def _release_from_gitea(raw: dict) -> RemoteRelease | None:
    if not isinstance(raw, dict):
        return None
    parsed = [_asset_from_gitea(item) for item in raw.get("assets") or [] if isinstance(item, dict)]
    assets = tuple(asset for asset in parsed if asset is not None)
    return RemoteRelease(
        tag=str(raw.get("tag_name") or ""),
        name=str(raw.get("name") or ""),
        body=str(raw.get("body") or ""),
        published_at=str(raw.get("published_at") or raw.get("created_at") or ""),
        assets=assets,
        prerelease=bool(raw.get("prerelease")),
        draft=False,  # Gitea has no draft releases
        release_url=str(raw.get("html_url") or "") or None,
        source="gitea",
    )


class GiteaReleasesProvider(SourceProvider):
    """Gitea-compatible Releases API (Codeberg and self-hosted Forgejo)."""

    def __init__(self, http: HttpClient, source_type: SourceType) -> None:
        if source_type not in GITEA_HOSTS:
            raise ValueError(f"GiteaReleasesProvider requires a codeberg/forgejo source type, got {source_type}")
        self.http = http
        self.source_type = source_type
        self.name = GITEA_HOSTS[source_type][0]
        self._default_host = GITEA_HOSTS[source_type][1]
        self._cache: dict[tuple[str, str, int], list[RemoteRelease]] = {}
        self._incremental_hits: set[tuple[object, ...]] = set()
        self._cache_lock = threading.Lock()
        self.requests = 0

    def _host(self, source: RepositoryRef) -> str:
        host = source.host or self._default_host
        if not host:
            raise ProviderError(f"{self.name} provider requires upstream.host")
        return host.rstrip("/")

    def _get(self, source: RepositoryRef, path: str) -> object:
        payload = self.http.get_json(f"{self._host(source)}/api/v1{path}")
        self.requests += 1
        return payload

    def validate_repository(self, source: RepositoryRef) -> ValidationResult:
        url = f"{self._host(source)}/{source.repo}"
        try:
            payload = self._get(source, f"/repos/{source.repo}")
        except ProviderError as error:
            return ValidationResult(False, str(error), url)
        if not isinstance(payload, dict) or payload.get("archived"):
            return ValidationResult(False, "repository missing or archived", url)
        return ValidationResult(True, "ok", str(payload.get("html_url") or url))

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
            batch = self._get(source, f"/users/{source.repo}/repos?limit=50&page={page}")
            if not isinstance(batch, list) or not batch:
                break
            for item in batch:
                if not isinstance(item, dict) or item.get("archived") or item.get("mirror"):
                    continue
                collected.append(
                    DiscoveredApp(
                        app_id=str(item.get("name") or "").lower(),
                        name=str(item.get("name") or ""),
                        repository_url=str(item.get("html_url") or ""),
                        source_type=self.source_type,
                        developer=source.repo,
                        description=str(item.get("description") or ""),
                    )
                )
            if len(batch) < 50:
                break
        return collected

    def fetch_metadata(self, source: RepositoryRef) -> AppMetadata:
        payload = self._get(source, f"/repos/{source.repo}")
        if not isinstance(payload, dict):
            raise ProviderError(f"unexpected repository payload for {source.repo}")
        owner = payload.get("owner") if isinstance(payload.get("owner"), dict) else {}
        return AppMetadata(
            name=str(payload.get("name") or source.repo),
            developer=str(owner.get("login") or source.repo.split("/")[0]),
            description=str(payload.get("description") or ""),
            icon=str(owner.get("avatar_url") or ""),
            homepage=str(payload.get("html_url") or ""),
            license=str(payload.get("license") or "") if isinstance(payload.get("license"), str) else "",
            stars=int(payload.get("stars_count") or 0),
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
                batch = self._get(source, f"/repos/{source.repo}/releases?limit=50&page={page}")
                if not isinstance(batch, list):
                    raise ProviderError(f"unexpected releases payload for {source.repo}")
                page_releases = [rel for item in batch if (rel := _release_from_gitea(item)) is not None]
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

                if len(batch) < 50:
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
