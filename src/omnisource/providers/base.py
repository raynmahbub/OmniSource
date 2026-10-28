"""Provider contract.

Python methods are snake_case. The platform contract names (``discoverApps``,
``fetchMetadata``, ``fetchReleases``, ``validateRepository``) are bound as
aliases on the ABC so both styles resolve to the same implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from omnisource.domain import (
    AppMetadata,
    DiscoveredApp,
    RemoteAsset,
    RemoteRelease,
    RepositoryRef,
    SourceType,
    ValidationResult,
)

# Sentinel: the incremental fast path matched the prior newest asset URL.
INCREMENTAL_UNCHANGED: list[RemoteRelease] = []


class SourceProvider(ABC):
    """One upstream kind (GitHub Releases, GitLab, a JSON feed, …)."""

    name: str
    source_type: SourceType

    @abstractmethod
    def validate_repository(self, source: RepositoryRef) -> ValidationResult:
        """Return whether ``source`` exists and looks distributable."""

    @abstractmethod
    def discover_apps(self, source: RepositoryRef) -> list[DiscoveredApp]:
        """List apps reachable from ``source`` (a repo, org, or feed URL)."""

    @abstractmethod
    def fetch_metadata(self, source: RepositoryRef) -> AppMetadata:
        """Fetch identity metadata (name, description, topics, …)."""

    @abstractmethod
    def fetch_releases(
        self,
        source: RepositoryRef,
        *,
        previous_latest_url: str | None = None,
        incremental: bool = False,
    ) -> list[RemoteRelease]:
        """Return published releases, newest first.

        When ``incremental`` is true and the newest matching asset URL equals
        ``previous_latest_url``, return the shared ``INCREMENTAL_UNCHANGED``
        sentinel (an empty list) without further pagination. An ordinary empty
        list means the source has no releases; callers must compare the
        sentinel by identity, not equality. URL equality is only a fast path,
        not proof that the asset bytes or other metadata are unchanged.
        """

    # Platform-contract aliases ------------------------------------------------
    def validateRepository(self, source: RepositoryRef) -> ValidationResult:
        return self.validate_repository(source)

    def discoverApps(self, source: RepositoryRef) -> list[DiscoveredApp]:
        return self.discover_apps(source)

    def fetchMetadata(self, source: RepositoryRef) -> AppMetadata:
        return self.fetch_metadata(source)

    def fetch_assets(self, source: RepositoryRef, releases: list[RemoteRelease] | None = None) -> list[RemoteAsset]:
        """Return all discovered assets, reusing release metadata when supplied."""
        material = releases if releases is not None else self.fetch_releases(source)
        return [asset for release in material for asset in release.assets]

    def health_check(self, source: RepositoryRef) -> ValidationResult:
        """Run a cheap provider health check without downloading release files."""
        return self.validate_repository(source)

    def fetchReleases(
        self,
        source: RepositoryRef,
        *,
        previous_latest_url: str | None = None,
        incremental: bool = False,
    ) -> list[RemoteRelease]:
        return self.fetch_releases(source, previous_latest_url=previous_latest_url, incremental=incremental)

    def fetchAssets(self, source: RepositoryRef, releases: list[RemoteRelease] | None = None) -> list[RemoteAsset]:
        return self.fetch_assets(source, releases)

    def healthCheck(self, source: RepositoryRef) -> ValidationResult:
        return self.health_check(source)

    def verify(self, source: RepositoryRef) -> ValidationResult:
        """Confirm ``source`` is reachable and structurally valid.

        Contract alias: the platform interface names this ``verify()``; the
        implementation is the provider's repository validation (a release
        API ping, a feed payload parse, or an asset HEAD probe).
        """
        return self.validate_repository(source)
