"""HTTP client with retry, host-scoped credentials, and download probing.

Security invariant
------------------
Credentials are attached *only* when the request URL matches a configured
:class:`AuthRule` prefix (GitHub API, GitLab API, …). Download probes construct
their own header dict with no ``Authorization``. Third-party IPA URLs must
never receive a token.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omnisource.constants import ALIVE_CODES, RETRYABLE_CODES, USER_AGENT
from omnisource.errors import ProviderError
from omnisource.logutil import log


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward credentials to a different origin or outside their rule."""

    def __init__(self, auth_rules: tuple[AuthRule, ...]) -> None:
        super().__init__()
        self.auth_rules = auth_rules

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        old = urllib.parse.urlsplit(req.full_url)
        new = urllib.parse.urlsplit(newurl)
        if old.scheme == "https" and new.scheme != "https":
            raise urllib.error.HTTPError(req.full_url, code, "refusing HTTPS downgrade", headers, fp)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        old_origin = (old.scheme, old.hostname, old.port)
        new_origin = (new.scheme, new.hostname, new.port)
        sensitive = {"authorization", "proxy-authorization", "cookie", "private-token", "x-api-key"}
        sensitive.update(rule.header_name.lower() for rule in self.auth_rules)
        for name, _value in redirected.header_items():
            lower = name.lower()
            matching_rules = [rule for rule in self.auth_rules if rule.header_name.lower() == lower]
            if lower in sensitive and (
                old_origin != new_origin
                or (matching_rules and not any(rule.matches(newurl) for rule in matching_rules))
            ):
                redirected.remove_header(name)
        return redirected


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Stop at the first 3xx.

    Release hosts answer ``302`` and point at a signed CDN URL. Following that
    redirect proves nothing extra, costs an extra TLS handshake per app, and
    can start streaming a 120 MB IPA into the runner. A 3xx from the origin is
    sufficient evidence that the asset exists.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_PROBE_OPENER = urllib.request.build_opener(_NoRedirect)


@dataclass(frozen=True)
class AuthRule:
    """Attach a credential only to one configured API origin/path."""

    url_prefix: str
    header_name: str
    header_value: str

    def matches(self, url: str) -> bool:
        try:
            expected = urllib.parse.urlparse(self.url_prefix)
            actual = urllib.parse.urlparse(url)
        except ValueError:
            return False
        if (expected.scheme, expected.hostname, expected.port) != (
            actual.scheme,
            actual.hostname,
            actual.port,
        ):
            return False
        expected_path = expected.path.rstrip("/")
        return actual.path == expected_path or actual.path.startswith(expected_path + "/")


@dataclass(frozen=True)
class ProbeResult:
    reachable: bool
    detail: str
    url: str


class HttpClient:
    """Stdlib HTTP client used by every provider and the health probe."""

    def __init__(
        self,
        *,
        user_agent: str = USER_AGENT,
        auth_rules: tuple[AuthRule, ...] = (),
        default_timeout: float = 30.0,
        retries: int = 3,
        cache_dir: Path | None = None,
        max_backoff: float = 30.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_agent = user_agent
        self.auth_rules = auth_rules
        self._safe_opener = urllib.request.build_opener(_SafeRedirect(auth_rules))
        self.default_timeout = default_timeout
        self.retries = max(1, retries)
        self.cache_dir = cache_dir
        self.max_backoff = max(0.0, max_backoff)
        self.sleeper = sleeper
        self.requests = 0
        self._request_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._memory_cache: dict[str, tuple[Any, dict[str, str]]] = {}

    def _cache_paths(self, key: str) -> tuple[Path, Path]:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if self.cache_dir is None:
            raise RuntimeError("cache paths requested without a cache directory")
        return self.cache_dir / f"{digest}.json", self.cache_dir / f"{digest}.meta"

    def _read_cached_json(self, key: str) -> tuple[Any, dict[str, str]] | None:
        with self._cache_lock:
            if key in self._memory_cache:
                return self._memory_cache[key]
            if self.cache_dir is None:
                return None
            body_path, meta_path = self._cache_paths(key)
            try:
                payload = json.loads(body_path.read_text(encoding="utf-8"))
                metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            except (OSError, json.JSONDecodeError):
                return None
            if not isinstance(metadata, dict):
                metadata = {}
            result = (payload, {str(k): str(v) for k, v in metadata.items()})
            self._memory_cache[key] = result
            return result

    def _write_cached_json(self, key: str, payload: Any, headers: Any) -> None:
        metadata = {name.lower(): str(headers.get(name)) for name in ("ETag", "Last-Modified") if headers.get(name)}
        result = (payload, metadata)
        with self._cache_lock:
            self._memory_cache[key] = result
            if self.cache_dir is None:
                return
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            body_path, meta_path = self._cache_paths(key)
            body_tmp: Path | None = None
            meta_tmp: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.cache_dir,
                    prefix=f".{body_path.stem}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary.write(json.dumps(payload, ensure_ascii=False))
                    body_tmp = Path(temporary.name)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.cache_dir,
                    prefix=f".{meta_path.stem}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary.write(json.dumps(metadata, sort_keys=True))
                    meta_tmp = Path(temporary.name)
                body_tmp.replace(body_path)
                meta_tmp.replace(meta_path)
            finally:
                if body_tmp is not None:
                    body_tmp.unlink(missing_ok=True)
                if meta_tmp is not None:
                    meta_tmp.unlink(missing_ok=True)

    def _auth_headers(self, url: str) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": self.user_agent}
        for rule in self.auth_rules:
            if rule.matches(url):
                headers[rule.header_name] = rule.header_value
        return headers

    def _open(
        self,
        url: str,
        *,
        headers: dict[str, str],
        method: str = "GET",
        timeout: float | None = None,
        follow_redirects: bool = True,
    ):
        request = urllib.request.Request(url, headers=headers, method=method)
        opener = self._safe_opener.open if follow_redirects else _PROBE_OPENER.open
        with self._request_lock:
            self.requests += 1
        return opener(request, timeout=timeout or self.default_timeout)

    def get_json(
        self,
        url: str,
        *,
        extra_headers: dict[str, str] | None = None,
        retries: int | None = None,
        cache_key: str | None = None,
        conditional: bool = True,
    ) -> Any:
        """GET a JSON endpoint with retry, rate-limit backoff and validators.

        A small on-disk cache may be enabled by passing ``cache_dir`` to the
        constructor. Existing ETag/Last-Modified values are sent on the next
        request; a ``304`` returns the cached body. Cache keys never contain
        credentials. Failed upstream requests do not replace cached data.
        """
        if not is_http_url(url):
            raise ProviderError(f"invalid HTTP(S) URL: {url}")
        headers = self._auth_headers(url)
        headers["Accept"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        key = cache_key or url
        cached = self._read_cached_json(key) if conditional else None
        if cached:
            _, validators = cached
            if validators.get("etag"):
                headers["If-None-Match"] = validators["etag"]
            if validators.get("last-modified"):
                headers["If-Modified-Since"] = validators["last-modified"]

        attempts = max(1, retries if retries is not None else self.retries)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with self._open(url, headers=headers) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    self._write_cached_json(key, payload, response.headers)
                    return payload
            except urllib.error.HTTPError as error:
                if error.code == 304 and cached is not None:
                    return cached[0]
                last_error = error
                if error.code not in RETRYABLE_CODES:
                    break
                retry_after = error.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else float(2 ** (attempt - 1))
                except ValueError:
                    delay = float(2 ** (attempt - 1))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
                last_error = error
                delay = float(2 ** (attempt - 1))
            if attempt < attempts:
                delay = min(self.max_backoff, max(0.0, delay))
                log.warning(
                    "HTTP attempt %d/%d failed (%s); retrying in %.1fs",
                    attempt,
                    attempts,
                    last_error,
                    delay,
                )
                self.sleeper(delay)

        raise ProviderError(f"HTTP request failed after {attempts} attempts: {url} ({last_error})")

    def get_bytes(self, url: str, *, limit: int = 64_000, timeout: float = 12.0) -> bytes:
        """Fetch at most ``limit`` bytes. Never used for IPA payloads."""
        if not is_http_url(url):
            raise ProviderError(f"invalid HTTP(S) URL: {url}")
        headers = self._auth_headers(url)
        with self._open(url, headers=headers, timeout=timeout) as response:
            return response.read(limit)

    def open_stream(self, url: str, *, timeout: float | None = None):
        """Open a GET stream for a large payload; the caller must close it.

        Used only by integrity verification, which hashes in chunks so an IPA
        never sits fully in memory.
        """
        if not is_http_url(url):
            raise ProviderError(f"invalid HTTP(S) URL: {url}")
        # Binary URLs may redirect to third-party CDNs. They are always fetched
        # anonymously, even when a URL happens to match an API auth rule.
        headers = {"User-Agent": self.user_agent}
        return self._open(url, headers=headers, timeout=timeout)

    def probe(self, url: str, *, timeout: float = 12.0, retries: int = 2) -> ProbeResult:
        """Return reachability for a download URL, without credentials.

        Uses HEAD first; falls back to a one-byte ranged GET for hosts that
        reject HEAD, so a probe never downloads a whole IPA into the runner.
        """
        if not isinstance(url, str) or not url:
            return ProbeResult(False, "empty url", url or "")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ProbeResult(False, "not an http(s) url", url)

        headers = {"User-Agent": self.user_agent}
        detail = "unknown"
        for attempt in range(1, retries + 1):
            for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
                try:
                    with self._open(
                        url,
                        headers={**headers, **extra},
                        method=method,
                        timeout=timeout,
                        follow_redirects=False,
                    ) as response:
                        if response.status in ALIVE_CODES:
                            return ProbeResult(True, f"HTTP {response.status}", url)
                        detail = f"HTTP {response.status}"
                except urllib.error.HTTPError as error:
                    detail = f"HTTP {error.code}"
                    if error.code in ALIVE_CODES:
                        return ProbeResult(True, detail, url)
                    if error.code in RETRYABLE_CODES:
                        break
                    if method == "GET":
                        return ProbeResult(False, detail, url)
                    if error.code not in {403, 405, 501}:
                        return ProbeResult(False, detail, url)
                except (urllib.error.URLError, TimeoutError, OSError) as error:
                    detail = str(getattr(error, "reason", error))
                    break
            if attempt < retries:
                time.sleep(1.5 * attempt)
        return ProbeResult(False, detail, url)


def github_accept_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def is_http_url(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
