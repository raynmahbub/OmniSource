"""Generic JSON feed provider: raw JSON documents and AltStore sources.

AltStore sources publish a document with an ``apps`` array; a raw JSON feed may
contain one app object or an array. The provider normalises both into
:class:`RemoteRelease` values.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from functools import cmp_to_key
from typing import Any

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
from omnisource.providers.base import SourceProvider
from omnisource.screenshots import _download_github_raw_via_api, _github_contents_location
from omnisource.utils.assets import detect_asset_metadata
from omnisource.utils.versioning import compare_versions


def _apps_from_payload(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        apps = payload.get("apps")
        if isinstance(apps, list):
            return [item for item in apps if isinstance(item, dict)]
        # Obtainium / generic: a single app object.
        if "name" in payload and ("downloadURL" in payload or "versions" in payload):
            return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def validate_feed_payload(payload: object) -> list[str]:
    """Return structural problems in a generic/AltStore-compatible feed."""
    apps = _apps_from_payload(payload)
    if not apps:
        return ["feed contains no application objects"]
    problems: list[str] = []
    seen: set[str] = set()
    for index, app in enumerate(apps):
        app_id = str(app.get("id") or app.get("appId") or app.get("bundleIdentifier") or app.get("name") or "")
        if not app_id:
            problems.append(f"apps[{index}] has no stable id/name/bundle identifier")
        elif app_id in seen:
            problems.append(f"duplicate application id '{app_id}'")
        seen.add(app_id)
        if not app.get("name"):
            problems.append(f"apps[{index}] is missing name")
        versions = app.get("versions")
        if not isinstance(versions, list) or not versions:
            versions = [app]
        for release_index, release in enumerate(versions):
            if not isinstance(release, dict):
                problems.append(f"apps[{index}].versions[{release_index}] is not an object")
                continue
            version = release.get("version") or release.get("latestVersion")
            if not version:
                problems.append(f"apps[{index}].versions[{release_index}] is missing version")
            assets = release.get("assets") or release.get("downloadAssets")
            urls = [release.get("downloadURL") or release.get("downloadUrl")]
            if isinstance(assets, list):
                urls.extend(
                    item.get("downloadURL") or item.get("downloadUrl") for item in assets if isinstance(item, dict)
                )
            urls = [url for url in urls if url]
            if not urls:
                problems.append(f"apps[{index}].versions[{release_index}] has no download URL")
            for url in urls:
                if not is_http_url(url):
                    problems.append(f"apps[{index}].versions[{release_index}] has invalid download URL")
    return problems


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value or default))
    except (TypeError, ValueError):
        return default


def _asset_from_feed(raw: dict[str, Any], fallback_url: str = "") -> RemoteAsset | None:
    url = str(raw.get("downloadUrl") or raw.get("downloadURL") or fallback_url or "")
    if not url:
        return None
    name = str(raw.get("filename") or raw.get("name") or "")
    if not name:
        name = url.rsplit("/", 1)[-1].split("?", 1)[0] or "asset"
    detected = detect_asset_metadata(name, url, mime_type=str(raw.get("mimeType") or raw.get("contentType") or ""))
    return RemoteAsset(
        name=name,
        download_url=url,
        size=_as_int(raw.get("size")),
        sha256=str(raw["sha256"]) if raw.get("sha256") else None,
        content_type=str(raw.get("mimeType") or raw.get("contentType") or ""),
        platform=str(raw.get("platform") or detected["platform"]),
        architecture=(str(raw["architecture"]) if raw.get("architecture") else detected["architecture"]),
        file_type=str(raw.get("fileType") or detected["fileType"]),
        installable=bool(raw.get("installable", detected["installable"])),
    )


def _releases_from_app(app: dict[str, Any]) -> list[RemoteRelease]:
    versions = app.get("versions")
    entries: list[dict[str, Any]]
    if isinstance(versions, list) and versions:
        entries = [item for item in versions if isinstance(item, dict)]
    else:
        entries = [
            {
                "version": app.get("version") or app.get("latestVersion"),
                "date": app.get("versionDate") or app.get("releaseDate") or app.get("date"),
                "releaseDate": app.get("latestReleaseDate"),
                "localizedDescription": app.get("versionDescription")
                or app.get("localizedDescription")
                or app.get("description")
                or "",
                "releaseNotes": app.get("latestReleaseNotes"),
                "downloadURL": app.get("downloadURL") or app.get("downloadUrl"),
                "downloadAssets": app.get("downloadAssets"),
                "size": app.get("size") or 0,
                "sha256": app.get("sha256"),
                "build": app.get("buildNumber") or app.get("latestBuild"),
            }
        ]

    releases: list[RemoteRelease] = []
    for entry in entries:
        version = str(entry.get("version") or "")
        if not version:
            continue
        raw_assets = entry.get("assets") or entry.get("downloadAssets")
        assets: list[RemoteAsset] = []
        if isinstance(raw_assets, list):
            assets = [
                asset for raw in raw_assets if isinstance(raw, dict) if (asset := _asset_from_feed(raw)) is not None
            ]
        if not assets:
            asset = _asset_from_feed(entry)
            if asset is not None:
                assets.append(asset)
        if not assets:
            continue
        releases.append(
            RemoteRelease(
                tag=str(entry.get("tag") or version),
                name=str(entry.get("name") or version),
                body=str(entry.get("releaseNotes") or entry.get("localizedDescription") or ""),
                published_at=str(entry.get("releaseDate") or entry.get("date") or ""),
                assets=tuple(assets),
                prerelease=bool(entry.get("isPrerelease", entry.get("prerelease", False))),
                draft=bool(entry.get("isDraft", entry.get("draft", False))),
                build_number=(str(entry["build"]) if entry.get("build") is not None else None),
                release_url=(str(entry["releaseUrl"]) if entry.get("releaseUrl") else None),
                source="json-feed",
            )
        )
    return releases


class GenericFeedProvider(SourceProvider):
    """Fetch a JSON document and expose it as apps + releases."""

    name = "json-feed"
    source_type = SourceType.JSON_FEED

    def __init__(self, http: HttpClient, source_type: SourceType | None = None) -> None:
        self.http = http
        if source_type is not None:
            self.source_type = source_type
            self.name = source_type.value
        self._payload_cache: dict[str, object] = {}
        self._payload_lock = threading.Lock()

    def _load(self, source: RepositoryRef) -> object:
        url = source.feed_url
        if not url:
            raise ProviderError("feed provider requires upstream.feedURL")
        with self._payload_lock:
            if url in self._payload_cache:
                return self._payload_cache[url]
            payload: object | None = None
            if isinstance(self.http, HttpClient) and _github_contents_location(url) is not None:
                try:
                    raw_bytes = _download_github_raw_via_api(self.http, url)
                    if raw_bytes is not None:
                        payload = json.loads(raw_bytes.decode("utf-8"))
                except Exception:
                    payload = None
            if payload is None:
                try:
                    payload = self.http.get_json(url)
                except ProviderError as primary_error:
                    raw_bytes = None
                    try:
                        raw_bytes = _download_github_raw_via_api(self.http, url)
                    except Exception:
                        raw_bytes = None
                    if raw_bytes is None:
                        raise primary_error
                    try:
                        payload = json.loads(raw_bytes.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as decode_error:
                        raise primary_error from decode_error
            self._payload_cache[url] = payload
            return payload

    def validate_repository(self, source: RepositoryRef) -> ValidationResult:
        if not is_http_url(source.feed_url):
            return ValidationResult(False, "feedURL is not an HTTP(S) URL", source.feed_url)
        try:
            payload = self._load(source)
        except ProviderError as error:
            return ValidationResult(False, str(error), source.feed_url)
        problems = validate_feed_payload(payload)
        if problems:
            return ValidationResult(False, "; ".join(problems[:5]), source.feed_url, {"problems": problems})
        apps = _apps_from_payload(payload)
        return ValidationResult(True, f"{len(apps)} app(s)", source.feed_url, {"apps": len(apps)})

    def discover_apps(self, source: RepositoryRef) -> list[DiscoveredApp]:
        payload = self._load(source)
        discovered: list[DiscoveredApp] = []
        for app in _apps_from_payload(payload):
            name = str(app.get("name") or "")
            bundle = str(app.get("bundleIdentifier") or app.get("bundleId") or "")
            raw_id = str(app.get("id") or app.get("appId") or "")
            slug = raw_id.lower() or bundle.lower().replace(".", "-") or name.lower().replace(" ", "-")
            discovered.append(
                DiscoveredApp(
                    app_id=slug,
                    name=name or slug,
                    repository_url=source.feed_url,
                    source_type=self.source_type,
                    developer=str(app.get("developerName") or app.get("developer") or ""),
                    description=str(app.get("localizedDescription") or app.get("subtitle") or ""),
                )
            )
        return discovered

    def fetch_metadata(self, source: RepositoryRef) -> AppMetadata:
        payload = self._load(source)
        if isinstance(payload, dict) and not payload.get("apps"):
            name = str(payload.get("name") or "feed")
            description = str(payload.get("description") or payload.get("subtitle") or "")
            icon = str(payload.get("iconURL") or payload.get("icon") or "")
            return AppMetadata(
                name=name,
                developer=str(payload.get("developer") or payload.get("developerName") or ""),
                description=description,
                icon=icon,
                homepage=str(payload.get("homepage") or source.feed_url),
                license=str(payload.get("license") or ""),
            )
        apps = self.discover_apps(source)
        first = apps[0] if apps else None
        return AppMetadata(
            name=first.name if first else "feed",
            developer=first.developer if first else "",
            description=first.description if first else "",
            homepage=source.feed_url,
        )

    def fetch_releases(
        self,
        source: RepositoryRef,
        *,
        previous_latest_url: str | None = None,
        incremental: bool = False,
    ) -> list[RemoteRelease]:
        payload = self._load(source)
        apps = _apps_from_payload(payload)
        # A catalog entry tracking a whole source uses every app in it;
        # upstream.appId narrows it to one id, bundle identifier or name.
        # Never fall back to the entire multi-app feed when a requested appId
        # is missing from the upstream source (that would silently pick an
        # unrelated app's release).
        target = apps
        selector = source.app_id or source.repo
        if selector:
            target = [
                app
                for app in apps
                if str(app.get("id") or app.get("appId") or "") == selector
                or str(app.get("bundleIdentifier") or app.get("bundleId") or "") == selector
                or str(app.get("name") or "") == selector
            ]
            if not target and not source.app_id and len(apps) == 1:
                target = apps
        releases: list[RemoteRelease] = []
        for app in target:
            releases.extend(replace(release, source=self.source_type.value) for release in _releases_from_app(app))

        def release_order(left: RemoteRelease, right: RemoteRelease) -> int:
            version_order = compare_versions(left.tag, right.tag)
            if version_order:
                return -version_order  # newest first
            return (right.published_at > left.published_at) - (right.published_at < left.published_at)

        releases.sort(key=cmp_to_key(release_order))
        if incremental and previous_latest_url and releases:
            newest = releases[0].assets[0].download_url if releases[0].assets else None
            if newest == previous_latest_url:
                return []
        return releases


class AltStoreFeedProvider(GenericFeedProvider):
    name = "altstore"
    source_type = SourceType.ALTSTORE
