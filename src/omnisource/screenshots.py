"""Screenshot validation, mirror and thumbnail generation.

This module is the static-site counterpart of the catalog ``screenshots`` array.
Catalog authors can declare remote screenshot URLs; the build pipeline

* validates that each URL is well-formed and points to an image,
* mirrors reachable screenshots to ``assets/screenshots/<slug>/...`` so the
  Pages deployment never depends on a third-party CDN,
* produces 480px-wide WebP thumbnails for fast gallery rendering, and
* publishes an honest content gap when no real screenshot is available.

The module never raises during the build — every issue is recorded and the
final ``feeds/screenshots.json`` document lists what is in place. This keeps
the "missing screenshot" case from blocking feed generation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omnisource.constants import GITHUB_API_ROOT
from omnisource.domain import Catalog, today
from omnisource.http import github_accept_headers

SCREENSHOTS_SCHEMA_VERSION = 1
ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
# We never want to balloon the Pages deployment: anything above this many
# screenshots per app is rejected (extra URLs are reported as warnings).
MAX_PER_APP = 12
# Screenshots are small website assets, not release payloads. Keep a corrupted
# or unexpected upstream response from turning a metadata sync into a huge
# download. ``get_bytes`` reads one extra byte so oversized files are detected.
MAX_SCREENSHOT_BYTES = 12 * 1024 * 1024


@dataclass
class ScreenshotIssue:
    slug: str
    detail: str
    severity: str = "warning"  # one of "warning" or "info"

    def as_dict(self) -> dict[str, str]:
        return {"slug": self.slug, "severity": self.severity, "detail": self.detail}


@dataclass
class ScreenshotReport:
    entries: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ScreenshotIssue] = field(default_factory=list)

    def to_doc(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCREENSHOTS_SCHEMA_VERSION,
            "generatedAt": today(),
            "count": len(self.entries),
            "issues": [issue.as_dict() for issue in self.issues],
            "screenshots": self.entries,
        }


def _slugify(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-").lower()
    return cleaned or "image"


def _filename_for(slug: str, index: int, ext: str) -> str:
    return f"{slug}-{index + 1:02d}{ext.lower()}"


def _is_allowed_image(url: str) -> bool:
    # Strip query/fragment (e.g. GitHub's ?raw=true) before checking extension.
    lower = url.lower().split("?", 1)[0].split("#", 1)[0]
    return any(lower.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def _validate_remote_urls(slug: str, urls: Iterable[str], report: ScreenshotReport) -> list[str]:
    """Return the list of URLs that pass basic shape validation."""
    valid: list[str] = []
    seen: set[str] = set()
    for url in urls:
        url = str(url or "").strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            report.issues.append(ScreenshotIssue(slug, f"Ignored non-http URL: {url}", "warning"))
            continue
        if url in seen:
            continue
        seen.add(url)
        if not _is_allowed_image(url):
            report.issues.append(ScreenshotIssue(slug, f"Ignored non-image URL: {url}", "info"))
            continue
        valid.append(url)
        if len(valid) >= MAX_PER_APP:
            report.issues.append(
                ScreenshotIssue(
                    slug,
                    f"Truncated to {MAX_PER_APP} screenshots (catalog declared more).",
                    "info",
                )
            )
            break
    return valid


def _github_contents_location(url: str) -> tuple[str, str, str] | None:
    """Translate a raw GitHub image URL to its Contents API endpoint.

    The normal raw URL remains the first request. This fallback keeps image
    mirroring usable on runners that can reach the GitHub API but block the
    separate raw-content host. Owner, repository, ref and path all come from
    the already validated catalog URL; the endpoint always stays on the fixed
    GitHub API origin, where ``HttpClient`` can apply its host-scoped token.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com":
        return None
    parts = [urllib.parse.unquote(segment) for segment in parsed.path.lstrip("/").split("/")]
    if len(parts) < 4:
        return None
    owner, repo, ref = parts[:3]
    path = "/".join(parts[3:])
    if not owner or not repo or not ref or not path:
        return None
    if any(segment in {"", ".", ".."} for segment in parts):
        return None
    owner_part = urllib.parse.quote(owner, safe="")
    repo_part = urllib.parse.quote(repo, safe="")
    path_part = urllib.parse.quote(path, safe="/")
    endpoint = (
        f"{GITHUB_API_ROOT}/repos/{owner_part}/{repo_part}/contents/{path_part}?{urllib.parse.urlencode({'ref': ref})}"
    )
    return owner_part, repo_part, endpoint


def _decode_github_base64(payload: Any) -> bytes | None:
    """Decode a bounded Contents/Git Blob API response, or return ``None``."""
    if not isinstance(payload, dict) or payload.get("type") not in {None, "file"}:
        return None
    try:
        size = int(payload.get("size") or 0)
    except (TypeError, ValueError):
        return None
    if size > MAX_SCREENSHOT_BYTES or payload.get("encoding") != "base64":
        return None
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        # Contents responses wrap base64 lines; Git Blob responses normally do
        # not. Removing ASCII whitespace lets one strict decoder handle both.
        decoded = base64.b64decode("".join(content.split()), validate=True)
    except (ValueError, binascii.Error):
        return None
    if not decoded or len(decoded) > MAX_SCREENSHOT_BYTES:
        return None
    return decoded


def _download_github_raw_via_api(http: Any, url: str) -> bytes | None:
    """Fetch a raw GitHub file through Contents, then Git Blob if necessary."""
    location = _github_contents_location(url)
    get_json = getattr(http, "get_json", None)
    if location is None or not callable(get_json):
        return None
    owner, repo, endpoint = location
    payload = get_json(endpoint, extra_headers=github_accept_headers())
    decoded = _decode_github_base64(payload)
    if decoded is not None:
        return decoded
    # The Contents API omits content for files above its inline limit. Its
    # blob SHA still lets us retrieve the same reviewed upstream bytes without
    # guessing a branch, mirror, or download host.
    if not isinstance(payload, dict):
        return None
    sha = payload.get("sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40,64}", sha):
        return None
    blob_url = f"{GITHUB_API_ROOT}/repos/{owner}/{repo}/git/blobs/{sha}"
    blob = get_json(blob_url, extra_headers=github_accept_headers())
    return _decode_github_base64(blob)


def _safe_download(http: Any, url: str) -> bytes | None:
    """Best-effort, bounded download used by the mirror step.

    Any network or decode failure returns ``None`` so an image can never block
    feed generation. Real ``HttpClient`` instances use ``get_bytes``; the
    ``fetch_bytes`` branch remains for lightweight integrations and tests.
    """
    if http is None:
        return None
    try:
        fetcher = getattr(http, "fetch_bytes", None)
        getter = getattr(http, "get_bytes", None)
        if callable(fetcher):
            payload = fetcher(url)
        elif callable(getter):
            payload = getter(url, limit=MAX_SCREENSHOT_BYTES + 1, timeout=12.0)
        else:
            # Compatibility for tiny HTTP adapters that expose neither method.
            import urllib.request

            with urllib.request.urlopen(url, timeout=8) as response:
                payload = response.read(MAX_SCREENSHOT_BYTES + 1)
        if payload and len(payload) <= MAX_SCREENSHOT_BYTES:
            return payload
    except Exception:  # pragma: no cover - the fallback below is the recovery path
        payload = None
    try:
        return _download_github_raw_via_api(http, url)
    except Exception:  # pragma: no cover - screenshots never block builds
        return None


def _persist_mirror(
    destination: Path,
    payload: bytes,
    *,
    ext: str,
) -> tuple[bool, int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(destination)
    digest = hashlib.sha256(payload).hexdigest()
    return True, len(payload), digest


def process_screenshots(
    catalog: Catalog,
    base_url: str,
    assets_dir: Path,
    *,
    http: Any = None,
    thumbnail_width: int = 480,
    refresh: bool = False,
    refresh_only: set[str] | None = None,
    previous: dict[str, Any] | None = None,
) -> ScreenshotReport:
    """Validate, mirror and produce thumbnail metadata.

    The function never raises. The returned :class:`ScreenshotReport` carries
    the on-disk artifacts and any human-readable issues.

    ``refresh`` (real sync runs) re-downloads every declared screenshot so
    upstream updates eventually replace stale local mirrors. Without it, a
    mirror already on disk is trusted as-is — rebuilds then stay
    deterministic and a transient remote failure can never demote a good
    mirror (``feeds/screenshots.json`` must be reproducible offline).

    ``previous`` supplies source identity as well as backward compatibility:
    an existing local path may be reused only while its upstream URL is
    unchanged. Actual mirror files are otherwise authoritative: an entry is
    marked mirrored only when its bytes exist and its digest can be measured,
    because a manifest that points at a deleted artifact is worse than one
    that admits the mirror must be fetched. The sync workflow commits these
    assets together with the manifest.
    """
    report = ScreenshotReport()
    base = base_url.rstrip("/")
    icons_dir = assets_dir  # Catalog icons live here.
    screenshots_dir = assets_dir / "screenshots"
    thumbnails_dir = assets_dir / "screenshots" / "thumbnails"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    previous_sources: dict[tuple[str, int], str] = {}
    if isinstance(previous, dict):
        for item in previous.get("screenshots") or []:
            if not isinstance(item, dict):
                continue
            try:
                key = (str(item.get("slug") or ""), int(item.get("index")))
            except (TypeError, ValueError):
                continue
            original_url = item.get("originalURL")
            if key[0] and isinstance(original_url, str):
                previous_sources[key] = original_url

    for app in catalog.apps:
        declared = list(getattr(app, "screenshots", []) or [])
        valid = _validate_remote_urls(app.slug, declared, report)
        if not valid and not getattr(app, "icon", ""):
            report.issues.append(ScreenshotIssue(app.slug, "No screenshots and no app icon", "warning"))
            continue
        for index, url in enumerate(valid):
            ext = Path(url.split("?", 1)[0]).suffix or ".png"
            mirror_name = _filename_for(app.slug, index, ext)
            mirror_path = screenshots_dir / app.slug / mirror_name
            mirrored_url = f"{base}/assets/screenshots/{app.slug}/{mirror_name}"
            thumbnail_name = f"{_slugify(mirror_name.rsplit('.', 1)[0])}.webp"
            thumbnail_path = thumbnails_dir / app.slug / thumbnail_name
            thumbnail_url = f"{base}/assets/screenshots/thumbnails/{app.slug}/{thumbnail_name}"
            previous_url = previous_sources.get((app.slug, index))
            source_changed = previous_url is not None and previous_url != url
            if source_changed:
                # The filename is only stable per app/index, not per remote
                # URL. Never let a changed declaration inherit unrelated bytes
                # (or an old thumbnail) merely because an offline file exists.
                mirror_path.unlink(missing_ok=True)
                thumbnail_path.unlink(missing_ok=True)
            entry: dict[str, Any] = {
                "slug": app.slug,
                "index": index,
                "originalURL": url,
                "mirroredURL": mirrored_url,
                "thumbnailURL": thumbnail_url,
                "thumbnailWidth": thumbnail_width,
                "mirrored": False,
                "size": 0,
                "sha256": "",
            }
            reused = False
            refresh_app = refresh and (refresh_only is None or app.slug in refresh_only)
            if mirror_path.exists() and not refresh_app:
                payload = mirror_path.read_bytes()
                entry["mirrored"] = True
                entry["size"] = len(payload)
                entry["sha256"] = hashlib.sha256(payload).hexdigest()
            else:
                payload = _safe_download(http, url)
                if payload:
                    ok, size, digest = _persist_mirror(mirror_path, payload, ext=ext)
                    if ok:
                        entry["mirrored"] = True
                        entry["size"] = size
                        entry["sha256"] = digest
                elif mirror_path.exists():
                    # A transient refresh failure must not demote known-good
                    # upstream art. Reuse the local bytes and their real digest;
                    # a later successful sync will replace them.
                    payload = mirror_path.read_bytes()
                    entry["mirrored"] = True
                    entry["size"] = len(payload)
                    entry["sha256"] = hashlib.sha256(payload).hexdigest()
                    reused = True
            # Thumbnail generation requires Pillow. The build environment
            # may not have it; if it is missing we record a transparent
            # placeholder and the website falls back to the full image.
            # Reused entries keep their recorded size (there is no local
            # mirror file to re-measure in an offline rebuild).
            if not reused or not thumbnail_path.exists():
                # Always present, whatever this machine has installed: with
                # Pillow available but no local mirror to resize, the block
                # below used to finish without touching the field, so the key
                # went missing on Pillow-equipped machines and was ``0`` on
                # stdlib-only ones — a build-environment-dependent document.
                entry["thumbnailSize"] = 0
                try:
                    from PIL import Image  # type: ignore

                    source = mirror_path if entry["mirrored"] else None
                    if source is not None and source.exists():
                        with Image.open(source) as img:  # type: ignore[arg-type]
                            img = img.convert("RGBA") if img.mode not in {"RGB", "RGBA"} else img
                            ratio = thumbnail_width / max(1, img.width)
                            new_height = max(1, int(img.height * ratio))
                            resized = img.resize((thumbnail_width, new_height), Image.LANCZOS)
                            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
                            resized.save(thumbnail_path, format="WEBP", quality=78, method=6)
                            entry["thumbnailSize"] = thumbnail_path.stat().st_size
                except Exception:
                    # Pillow is optional. The website gracefully falls back to
                    # the full-size mirrored image.
                    entry["thumbnailSize"] = 0
            if not entry.get("thumbnailSize") and thumbnail_path.exists():
                # The thumbnail on disk is the truth whether or not this run could
                # measure it with Pillow - reporting its real size keeps an offline
                # rebuild byte-identical instead of quietly zeroing the field.
                entry["thumbnailSize"] = thumbnail_path.stat().st_size
            report.entries.append(entry)
        # No screenshots declared: publish *nothing* for this app rather than an
        # icon-as-screenshot entry. A rendered stand-in in a machine-readable
        # manifest is indistinguishable from real art one consumer away, and an
        # app icon is not a preview of the app. The honest absence is already
        # reported: ``feeds/asset-manifest.json`` lists these slugs, and the app
        # page says upstream publishes none.
    # Hint the file system that this directory exists even on empty runs
    # so the website can probe ``/assets/screenshots/index.json`` later.
    (assets_dir / "screenshots" / "_manifest").mkdir(parents=True, exist_ok=True)
    _ = icons_dir  # silence linters — referenced for clarity
    return report
