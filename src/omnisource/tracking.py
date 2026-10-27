"""Release tracking engine.

Version comparison, changelog extraction, update detection, and asset
selection. All functions are pure so they can be unit-tested without I/O.
"""

from __future__ import annotations

import re
from functools import cmp_to_key, lru_cache
from typing import Any

from omnisource.constants import TAG_NUMBER_RE_PATTERN, VERSION_RE_PATTERN
from omnisource.domain import RemoteAsset, RemoteRelease, RepositoryRef
from omnisource.errors import ConfigurationError
from omnisource.utils.versioning import compare_versions, is_newer

VERSION_RE = re.compile(VERSION_RE_PATTERN)
TAG_NUMBER_RE = re.compile(TAG_NUMBER_RE_PATTERN)
SHA256_RE = re.compile(r"(?:sha-?256|sha256sum)[:\s]*([0-9a-fA-F]{64})", re.IGNORECASE)
DIGEST_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")


def tag_number(tag: str) -> int:
    match = TAG_NUMBER_RE.search(tag)
    return int(match.group(1)) if match else -1


def extract_sha256(*candidates: str | None) -> str | None:
    """Pull a SHA-256 hex digest out of a digest field or changelog body."""
    for candidate in candidates:
        if not candidate:
            continue
        digest = DIGEST_RE.match(candidate.strip())
        if digest:
            return digest.group(1).lower()
        match = SHA256_RE.search(candidate)
        if match:
            return match.group(1).lower()
        stripped = candidate.strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", stripped):
            return stripped
    return None


def extract_changelog(body: str, *, limit: int = 8_000) -> str:
    """Normalise a release body into a changelog string."""
    text = (body or "").strip().replace("\r\n", "\n")
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def pick_asset(
    release: RemoteRelease,
    suffixes: tuple[str, ...],
    pattern: re.Pattern[str] | None = None,
) -> RemoteAsset | None:
    """Choose the first asset whose name matches ``pattern`` then ``suffixes``."""
    assets = list(release.assets)
    if pattern is not None:
        assets = [asset for asset in assets if pattern.search(asset.name)]
    for suffix in suffixes:
        for asset in assets:
            if asset.name.lower().endswith(suffix.lower()):
                return asset
    return None


def matches_tag_rules(tag: str, ref: RepositoryRef) -> bool:
    if ref.tag_prefix and not tag.startswith(ref.tag_prefix):
        return False
    return not any(tag.startswith(prefix) for prefix in ref.exclude_tag_prefixes)


def release_is_eligible(release: RemoteRelease, ref: RepositoryRef) -> bool:
    """Apply draft/pre-release and tag policy without losing source history."""
    if release.draft and not ref.include_drafts:
        return False
    if release.prerelease and not ref.include_prereleases:
        return False
    return matches_tag_rules(release.tag, ref)


def version_numbers(
    release: RemoteRelease,
    asset_name: str,
    *,
    from_tag: bool,
    version_pattern: str = "",
) -> list[str]:
    """Return the version numbers for a release, most significant first.

    ``version_pattern`` wins when it matches: it names the number that is the
    published version, which matters when a filename carries two of them (for
    example ``YTKACE_0.9.2_YouTube_21.35.3.ipa``, where the YouTube version is
    what an installed app reports). Remaining numbers stay available through
    ``{secondary}``.
    """
    selected = _match_version_pattern(release, asset_name, version_pattern)
    if selected:
        chosen, haystack = selected
        others = [number for number in VERSION_RE.findall(haystack) if number != chosen]
        return [chosen, *others]

    numbers: list[str] = []
    if from_tag:
        numbers = VERSION_RE.findall(release.tag)
    if not numbers:
        numbers = VERSION_RE.findall(asset_name)
    if not numbers:
        numbers = VERSION_RE.findall(release.tag) or VERSION_RE.findall(release.name)
    return numbers


@lru_cache(maxsize=64)
def compile_version_pattern(pattern: str) -> re.Pattern[str] | None:
    """Compile ``versionPattern``; an invalid regex is a configuration error."""
    if not pattern:
        return None
    try:
        return re.compile(pattern)
    except re.error as error:
        raise ConfigurationError(f"upstream.versionPattern does not compile: {error}") from error


def _match_version_pattern(release: RemoteRelease, asset_name: str, pattern: str) -> tuple[str, str] | None:
    """Return ``(version, haystack)`` for the first candidate the regex hits."""
    compiled = compile_version_pattern(pattern)
    if compiled is None:
        return None
    for candidate in (asset_name, release.tag, release.name):
        if not candidate:
            continue
        match = compiled.search(candidate)
        if not match:
            continue
        value = (match.group(1) if match.groups() else match.group(0)).strip()
        if value:
            return value, candidate
    return None


def build_version_entry(
    *,
    app_name: str,
    ref: RepositoryRef,
    release: RemoteRelease,
    asset: RemoteAsset,
) -> dict[str, Any]:
    """Render one AltStore ``versions[]`` object from a normalised release.

    The shape is byte-compatible with the historical pipeline: ``version``,
    ``date``, ``localizedDescription``, ``downloadURL``, ``size``,
    ``minOSVersion``. Optional ``sha256`` is omitted unless known so existing
    feeds stay stable.
    """
    published = release.published_at or ""
    if not published:
        date = today_fallback()
    elif ref.iso_dates:
        date = published
    else:
        date = published[:10]

    numbers = version_numbers(
        release,
        asset.name,
        from_tag=ref.version_from_tag,
        version_pattern=ref.version_pattern,
    )
    version = numbers[0] if numbers else date
    secondary = numbers[-1] if numbers else version

    label = asset.name.removesuffix(".ipa")
    description = ref.description_template.format(
        name=app_name,
        version=version,
        secondary=secondary,
        label=label,
        tag=release.tag,
        date=date,
    )
    body = extract_changelog(release.body)
    if body:
        description = f"{description}\n\n{body}"

    min_os = ref.min_os_by_tag_number.get(str(tag_number(release.tag)), ref.min_os_version)
    entry: dict[str, Any] = {
        "version": version,
        "date": date,
        "localizedDescription": description,
        "downloadURL": asset.download_url,
        "size": int(asset.size or 0),
        "minOSVersion": min_os,
        # Canonical release/asset information is additive to AltStore v2.
        "releaseUrl": release.release_url,
        "source": release.source or ref.provider.value,
        "isPrerelease": release.prerelease,
        "isDraft": release.draft,
        "assets": [item.to_dict() for item in release.assets],
    }
    sha = asset.sha256 or extract_sha256(release.body)
    if sha:
        entry["sha256"] = sha
    if release.build_number:
        entry["buildVersion"] = release.build_number
    if asset.download_count:
        entry["downloads"] = int(asset.download_count)
    return entry


def today_fallback() -> str:
    from omnisource.domain import today

    return today()


def select_versions(
    *,
    app_name: str,
    ref: RepositoryRef,
    releases: list[RemoteRelease],
    pattern: re.Pattern[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter, sort and cap remote releases into AltStore version entries."""
    matches: list[tuple[RemoteRelease, RemoteAsset]] = []
    for release in releases:
        if not release_is_eligible(release, ref):
            continue
        asset = pick_asset(release, ref.asset_suffixes, pattern)
        if asset is None or not asset.download_url:
            continue
        matches.append((release, asset))

    def release_order(left: tuple[RemoteRelease, RemoteAsset], right: tuple[RemoteRelease, RemoteAsset]) -> int:
        left_release, left_asset = left
        right_release, right_asset = right
        if ref.sort_by_tag_number:
            tag_order = (tag_number(right_release.tag) > tag_number(left_release.tag)) - (
                tag_number(right_release.tag) < tag_number(left_release.tag)
            )
            if tag_order:
                return tag_order
        left_version = version_numbers(
            left_release,
            left_asset.name,
            from_tag=ref.version_from_tag,
            version_pattern=ref.version_pattern,
        )
        right_version = version_numbers(
            right_release,
            right_asset.name,
            from_tag=ref.version_from_tag,
            version_pattern=ref.version_pattern,
        )
        left_primary = left_version[0] if left_version else ""
        right_primary = right_version[0] if right_version else ""
        version_order = compare_versions(left_primary, right_primary)
        if version_order:
            return -version_order
        if len(left_version) > 1 or len(right_version) > 1:
            secondary_order = compare_versions(".".join(left_version[1:]), ".".join(right_version[1:]))
            if secondary_order:
                return -secondary_order
        return (right_release.published_at > left_release.published_at) - (
            right_release.published_at < left_release.published_at
        )

    matches.sort(key=cmp_to_key(release_order))

    versions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for release, asset in matches:
        entry = build_version_entry(app_name=app_name, ref=ref, release=release, asset=asset)
        url = entry["downloadURL"]
        if not url or url in seen:
            continue
        seen.add(url)
        versions.append(entry)
        if ref.keep_versions and len(versions) >= ref.keep_versions:
            break
    return versions


def matched_release_dates(
    *,
    ref: RepositoryRef,
    releases: list[RemoteRelease],
    pattern: re.Pattern[str] | None = None,
    limit: int = 12,
) -> list[str]:
    """Return up to ``limit`` chronological ISO dates for matching releases.

    ``select_versions`` caps the published ``versions`` array at
    ``ref.keep_versions`` (usually 1) to keep feed payloads small, which
    previously discarded the historical release dates already fetched in the
    same API response. Recording the dates separately in ``state.json`` gives
    the reputation and cadence engines a real release series without bloating
    ``apps.json``.
    """
    seen: set[str] = set()
    for release in releases:
        if not release_is_eligible(release, ref):
            continue
        asset = pick_asset(release, ref.asset_suffixes, pattern)
        if asset is None or not asset.download_url:
            continue
        published = str(release.published_at or "").strip()
        if len(published) >= 10:
            iso = published[:10]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", iso):
                seen.add(iso)
    return sorted(seen)[-max(1, limit) :]


def detect_update(previous: list[dict[str, Any]] | None, current: list[dict[str, Any]]) -> str:
    """Classify the relationship between two version lists.

    Returns ``new``, ``updated``, or ``unchanged``.
    """
    if not current:
        return "unchanged"
    if not previous:
        return "new"
    old = previous[0].get("version", "")
    new = current[0].get("version", "")
    old_url = previous[0].get("downloadURL", "")
    new_url = current[0].get("downloadURL", "")
    if old_url == new_url and old == new:
        return "unchanged"
    if is_newer(new, old) or old_url != new_url:
        return "updated"
    return "unchanged"
