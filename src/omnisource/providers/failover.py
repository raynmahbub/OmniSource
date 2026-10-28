"""Provider failover chain (Phase 2 redundancy).

Every app resolves through an ordered chain of upstream legs:

    primary  →  mirror(s)  →  archive  →  cached snapshot

* A leg that **raises** (network/API failure) is skipped with its error
  recorded.
* A leg that returns **releases** ends the chain — its releases win.
* A leg that is *healthy but empty* (no matching release) also moves the
  chain on, because a mirror may carry what the primary lost.
* An incremental URL match ends the chain as unchanged, not empty.
* If no releases were found and at least one leg errored, the chain raises a
  combined :class:`ProviderError`; the cached snapshot is the final fallback.
* If every leg was healthy but empty, the chain returns an empty list so the
  pipeline can report a missing release or use a first-time manual fallback.

The chain is pure orchestration: providers stay stateless per leg, and a
single-leg chain (the common case) behaves identically to calling the
provider directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from omnisource.domain import RemoteRelease, RepositoryRef
from omnisource.errors import ConfigurationError, ProviderError
from omnisource.logutil import log
from omnisource.providers.base import INCREMENTAL_UNCHANGED
from omnisource.providers.registry import ProviderRegistry


@dataclass
class FailoverResult:
    """Outcome of walking one app's failover chain."""

    releases: list[RemoteRelease]
    source: str  # identity of the leg that produced the releases ("" when empty)
    attempts: list[str] = field(default_factory=list)
    unchanged: bool = False

    @property
    def used_failover(self) -> bool:
        return bool(self.attempts) and not self.attempts[0].startswith(("ok ", "unchanged "))


def leg_label(ref: RepositoryRef) -> str:
    """Stable human label of one chain leg, e.g. ``github:owner/repo``."""
    identity = ref.identity or ref.feed_url or ref.repo
    return f"{ref.provider.value}:{identity}"


class FailoverChain:
    """Ordered legs (primary first) resolved through one registry."""

    def __init__(self, registry: ProviderRegistry, legs: list[RepositoryRef]) -> None:
        if not legs:
            raise ConfigurationError("failover chain needs at least one leg")
        self.registry = registry
        self.legs = legs

    @classmethod
    def from_ref(cls, registry: ProviderRegistry, primary: RepositoryRef) -> FailoverChain:
        """Build the chain for a catalog ``upstream`` block (mirrors appended)."""
        legs = [primary, *(_mirror_leg(primary, mirror) for mirror in primary.mirrors)]
        return cls(registry, legs)

    def fetch_releases(
        self,
        *,
        previous_latest_url: str | None = None,
        incremental: bool = False,
    ) -> FailoverResult:
        attempts: list[str] = []
        hard_errors = 0
        for index, ref in enumerate(self.legs):
            label = leg_label(ref)
            try:
                provider = self.registry.resolve(ref)
                releases = provider.fetch_releases(
                    ref,
                    previous_latest_url=previous_latest_url,
                    incremental=incremental,
                )
            except (ProviderError, ConfigurationError) as error:
                hard_errors += 1
                attempts.append(f"{label} error: {error}")
                log.warning("failover leg %d/%d %s failed: %s", index + 1, len(self.legs), label, error)
                continue
            if releases is INCREMENTAL_UNCHANGED and incremental and previous_latest_url:
                attempts.append(f"unchanged {label}")
                return FailoverResult([], label, attempts, unchanged=True)
            if releases:
                attempts.append(f"ok {label} ({len(releases)} release(s))")
                return FailoverResult(releases, label, attempts)
            attempts.append(f"{label} empty")
            log.info("failover leg %d/%d %s returned no releases", index + 1, len(self.legs), label)

        # An error on one leg plus empty results on the others does not prove
        # the primary is unchanged. Preserve and report the failure.
        if hard_errors:
            raise ProviderError("no usable source; attempts: " + " | ".join(attempts))
        return FailoverResult([], "", attempts)


def _mirror_leg(primary: RepositoryRef, mirror: dict) -> RepositoryRef:
    """Parse one ``upstream.mirrors`` entry into a RepositoryRef.

    Mirror entries inherit the primary's asset policy (suffixes, patterns,
    keepVersions, …) unless they override a key explicitly, so a mirror of
    the same app needs only ``{"provider": "mirror", "url": "…"}``.
    """
    inherited = {
        "assetSuffixes": list(primary.asset_suffixes),
        "assetNamePattern": primary.asset_name_pattern,
        "versionPattern": primary.version_pattern,
        "tagPrefix": primary.tag_prefix,
        "excludeTagPrefixes": list(primary.exclude_tag_prefixes),
        "maxPages": primary.max_pages,
        "keepVersions": primary.keep_versions,
        "sortByTagNumber": primary.sort_by_tag_number,
        "versionFromTag": primary.version_from_tag,
        "includePrereleases": primary.include_prereleases,
        "includeDrafts": primary.include_drafts,
        "descriptionTemplate": primary.description_template,
        "minOSVersion": primary.min_os_version,
        "minOSVersionByTagNumber": dict(primary.min_os_by_tag_number),
        "minOSVersionByAssetName": dict(primary.min_os_by_asset_name),
        "isoDates": primary.iso_dates,
        "timeout": primary.request_timeout,
    }
    merged = {key: value for key, value in mirror.items() if value not in (None, "", [])}
    merged = {**inherited, **merged}
    if not merged.get("provider"):
        raise ConfigurationError("upstream.mirrors entries require a 'provider'")
    # A mirror is another source for the same catalog app, not permission to
    # publish an unrelated bundle. Keep the identity check across all legs.
    return replace(RepositoryRef.parse(merged), expected_bundle_id=primary.expected_bundle_id)
