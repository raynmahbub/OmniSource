"""Direct-URL and Mirror providers.

These serve a *single* known asset from a static host instead of paging a
release API:

* ``direct``  — the canonical asset URL for an app that ships no forge
  releases (a static CDN, a self-hosted bucket, …).
* ``mirror``  — the same contract, used as a fallback leg of the failover
  chain (``upstream.mirrors``).

Version and date are not discoverable from a bare file, so the catalog
supplies them: ``upstream.version`` / ``upstream.versionDate`` (and
``manualRelease`` is used by the pipeline as the last resort). The provider
HEAD-probes the URL so a dead mirror is reported as a provider failure and
the chain moves on to the next leg.
"""

from __future__ import annotations

import contextlib

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
from omnisource.http import HttpClient, is_http_url
from omnisource.logutil import log
from omnisource.providers.base import INCREMENTAL_UNCHANGED, SourceProvider
from omnisource.tracking import extract_sha256
from omnisource.utils.assets import detect_asset_metadata


def _asset_from_url(url: str, known_size: int = 0) -> RemoteAsset:
    name = url.rsplit("/", 1)[-1].split("?", 1)[0] or "asset"
    detected = detect_asset_metadata(name, url)
    return RemoteAsset(
        name=name,
        download_url=url,
        size=known_size,
        sha256=None,
        content_type="",
        platform=str(detected["platform"]),
        architecture=detected["architecture"],
        file_type=str(detected["fileType"]),
        installable=bool(detected["installable"]),
    )


class DirectURLProvider(SourceProvider):
    """One asset at a fixed URL (``upstream.url``/``feedURL``)."""

    def __init__(self, http: HttpClient, source_type: SourceType) -> None:
        self.http = http
        self.source_type = source_type
        self.name = source_type.value

    def _url(self, source: RepositoryRef) -> str:
        url = source.feed_url
        if not url:
            raise ProviderError(f"{self.name} provider requires upstream.url (or feedURL)")
        return url

    def validate_repository(self, source: RepositoryRef) -> ValidationResult:
        url = source.feed_url
        if not is_http_url(url):
            return ValidationResult(False, "url is not an HTTP(S) URL", url)
        result = self.http.probe(url, timeout=source.request_timeout)
        return ValidationResult(result.reachable, result.detail, url)

    def verify(self, source: RepositoryRef) -> ValidationResult:
        return self.validate_repository(source)

    def discover_apps(self, source: RepositoryRef) -> list[DiscoveredApp]:
        url = source.feed_url
        if not url:
            return []
        app_id = source.app_id or url.rsplit("/", 1)[-1].split(".")[0].lower() or "app"
        return [
            DiscoveredApp(
                app_id=app_id,
                name=app_id,
                repository_url=url,
                source_type=self.source_type,
            )
        ]

    def fetch_metadata(self, source: RepositoryRef) -> AppMetadata:
        url = self._url(source)
        return AppMetadata(name=source.app_id or url.rsplit("/", 1)[-1], developer="", homepage=url)

    def fetch_releases(
        self,
        source: RepositoryRef,
        *,
        previous_latest_url: str | None = None,
        incremental: bool = False,
    ) -> list[RemoteRelease]:
        url = self._url(source)
        if not is_http_url(url):
            raise ProviderError(f"{self.name}: upstream.url must be an HTTP(S) URL")

        # A dead URL is a chain failure, not an empty release list.
        probe = self.http.probe(url, timeout=source.request_timeout)
        if not probe.reachable:
            raise ProviderError(f"{self.name}: asset URL unreachable ({probe.detail})")

        if incremental and previous_latest_url == url:
            return INCREMENTAL_UNCHANGED

        asset = _asset_from_url(url)
        version = source.version or source.app_id or "0.0.0"
        release = RemoteRelease(
            tag=version,
            name=version,
            body=source.description_template if source.version_date else "",
            published_at=source.version_date,
            assets=(asset,),
            source=self.source_type.value,
            release_url=url,
        )
        log.debug("%s: direct asset %s (v%s)", self.name, url, version)
        return [release]


class ArchiveProvider(SourceProvider):
    """archive.org item as a release source.

    ``upstream.url`` is the item (``https://archive.org/details/<item>`` or a
    bare identifier). The item's ``metadata/<item>`` endpoint lists files with
    sizes; the newest file matching the asset policy becomes the release
    asset. Version/date come from ``upstream.version``/``versionDate`` when
    present, otherwise from the item's ``date``/``created`` metadata.
    """

    name = "archive"
    source_type = SourceType.ARCHIVE
    API_ROOT = "https://archive.org"

    def __init__(self, http: HttpClient) -> None:
        self.http = http
        self._cache: dict[str, dict] = {}

    def _item(self, source: RepositoryRef) -> str:
        url = source.feed_url
        if not url:
            raise ProviderError("archive provider requires upstream.url (archive.org item)")
        detail = "details/"
        if detail in url:
            return url.rsplit(detail, 1)[1].strip("/")
        return url.rsplit("/", 1)[-1].strip("/")

    def _metadata(self, source: RepositoryRef) -> dict:
        item = self._item(source)
        cached = self._cache.get(item)
        if cached is not None:
            return cached
        payload = self.http.get_json(f"{self.API_ROOT}/metadata/{item}")
        if not isinstance(payload, dict):
            raise ProviderError(f"unexpected archive.org metadata for '{item}'")
        self._cache[item] = payload
        return payload

    def validate_repository(self, source: RepositoryRef) -> ValidationResult:
        item = self._item(source)
        url = f"{self.API_ROOT}/details/{item}"
        try:
            payload = self._metadata(source)
        except ProviderError as error:
            return ValidationResult(False, str(error), url)
        files = payload.get("files")
        count = len(files) if isinstance(files, list) else 0
        return ValidationResult(isinstance(files, list) and count > 0, f"{count} file(s)", url)

    def verify(self, source: RepositoryRef) -> ValidationResult:
        return self.validate_repository(source)

    def discover_apps(self, source: RepositoryRef) -> list[DiscoveredApp]:
        item = self._item(source)
        return [
            DiscoveredApp(
                app_id=source.app_id or item.lower(),
                name=item,
                repository_url=f"{self.API_ROOT}/details/{item}",
                source_type=self.source_type,
            )
        ]

    def fetch_metadata(self, source: RepositoryRef) -> AppMetadata:
        payload = self._metadata(source)
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        return AppMetadata(
            name=str(meta.get("title") or self._item(source)),
            developer=str(meta.get("creator") or ""),
            description=str(meta.get("description") or ""),
            homepage=f"{self.API_ROOT}/details/{self._item(source)}",
        )

    def fetch_releases(
        self,
        source: RepositoryRef,
        *,
        previous_latest_url: str | None = None,
        incremental: bool = False,
    ) -> list[RemoteRelease]:
        item = self._item(source)
        payload = self._metadata(source)
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            return []

        candidates: list[tuple[str, RemoteAsset]] = []
        for raw in files:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "")
            if not name:
                continue
            url = f"{self.API_ROOT}/download/{item}/{name}"
            detected = detect_asset_metadata(name, url)
            if not detected["installable"] and not name.lower().endswith(tuple(source.asset_suffixes)):
                continue
            size = 0
            with contextlib.suppress(TypeError, ValueError):
                size = int(raw.get("size") or 0)
            candidates.append(
                (
                    str(raw.get("created") or ""),
                    RemoteAsset(
                        name=name,
                        download_url=url,
                        size=size,
                        sha256=extract_sha256(str(raw.get("md5") or "")) if raw.get("sha256") else None,
                        content_type=str(raw.get("format") or ""),
                        platform=str(detected["platform"]),
                        architecture=detected["architecture"],
                        file_type=str(detected["fileType"]),
                        installable=bool(detected["installable"]),
                    ),
                )
            )

        if not candidates:
            return []
        # Newest file first: archive.org records ``created`` per file; the name
        # only tie-breaks items without timestamps.
        candidates.sort(key=lambda pair: (pair[0], pair[1].name), reverse=True)
        best = candidates[0][1]
        if incremental and previous_latest_url and best.download_url == previous_latest_url:
            return INCREMENTAL_UNCHANGED

        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        published_at = source.version_date or str(meta.get("date") or meta.get("created") or "")[:10]
        version = source.version or str(meta.get("version") or "0.0.0")
        return [
            RemoteRelease(
                tag=version,
                name=f"{item} {version}",
                body="",
                published_at=published_at,
                assets=(best,),
                source="archive",
                release_url=f"{self.API_ROOT}/details/{item}",
            )
        ]
