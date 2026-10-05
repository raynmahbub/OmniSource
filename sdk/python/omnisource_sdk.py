"""OmniSource Python SDK.

A single-file, dependency-free client for the public OmniSource API. Works on
Python 3.8+. The SDK is intentionally small: it consumes the same JSON
documents the website reads, so any change in the API contract is visible
in both the JS and the Python clients at the same time.

Usage
-----

    from omnisource_sdk import OmniSource

    client = OmniSource()
    trending = client.get_trending()
    related = client.get_related("uyouenhanced")
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_BASE_URL = "https://raynmahbub.github.io/OmniSource"
DEFAULT_TIMEOUT = 8.0


class OmniSourceError(Exception):
    """Raised when a request fails or returns a non-2xx response."""

    def __init__(self, message: str, *, status: int | None = None, url: str | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url
        self.body = body


@dataclass
class _Response:
    ok: bool
    status: int
    body: str
    payload: Any | None


def _default_fetch(url: str, *, timeout: float) -> _Response:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - we trust the URL
            body = response.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None
            return _Response(ok=True, status=response.status, body=body, payload=payload)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace") if error.fp else ""
        return _Response(ok=False, status=error.code, body=body, payload=None)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise OmniSourceError(str(error) or "Network error", url=url) from error


class OmniSource:
    """Public API client for OmniSource.

    All read methods return a dict (or list) and never raise on missing
    endpoints — they return the documented empty / null fallback instead.
    Transport errors propagate as :class:`OmniSourceError`.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        fetch: Callable[[str, float], _Response] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._fetch = fetch or (lambda url, *, timeout: _default_fetch(url, timeout=timeout))
        self.last_error: OmniSourceError | None = None

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}/{path.lstrip('/') }"
        response = self._fetch(url, timeout=self.timeout)
        if not response.ok:
            self.last_error = OmniSourceError(
                f"Request failed ({response.status})", status=response.status, url=url, body=response.body
            )
            raise self.last_error
        self.last_error = None
        if response.payload is None:
            raise OmniSourceError("Response was not valid JSON", status=response.status, url=url)
        return response.payload

    def _safe(self, path: str, fallback: Any) -> Any:
        try:
            return self._get(path)
        except OmniSourceError:
            return fallback

    @staticmethod
    def _fuzzy(query: str, value: Any) -> float:
        if not value:
            return 0.0
        text = str(value).lower()
        q = query.lower()
        if text == q:
            return 1.0
        if text.startswith(q):
            return 0.85
        if q in text:
            return 0.65
        tokens = [token for token in q.split() if token]
        if not tokens:
            return 0.0
        hits = sum(1 for token in tokens if token in text)
        if not hits:
            return 0.0
        return 0.45 * (hits / len(tokens))

    def search(self, query: str, *, limit: int = 12, verified_only: bool = False) -> list[dict]:
        data = self._safe("feeds/search-index.json", {"documents": [], "fuse": {"keys": []}})
        keys = (data.get("fuse") or {}).get("keys") or []
        q = (query or "").strip().lower()
        if len(q) < 2:
            return []
        results: list[tuple[float, dict]] = []
        for doc in data.get("documents") or []:
            score = 0.0
            for key in keys:
                field = doc.get(key["name"])
                if isinstance(field, list):
                    for value in field:
                        score += float(key.get("weight", 0)) * self._fuzzy(q, value)
                else:
                    score += float(key.get("weight", 0)) * self._fuzzy(q, field)
            if score >= 0.4:
                results.append((score, doc))
        results.sort(key=lambda item: item[0], reverse=True)
        items = [doc for _, doc in results[:limit]]
        if verified_only:
            items = [doc for doc in items if doc.get("verificationLevel") == "VERIFIED"]
        return items

    def get_app(self, slug: str) -> dict | None:
        discovery = self._safe("discovery.json", {"apps": []})
        install = self._safe("feeds/install.json", {"apps": []})
        meta = next((item for item in (discovery.get("apps") or []) if (item.get("slug") or item.get("id")) == slug), None)
        if not meta:
            return None
        install_entry = next((item for item in (install.get("apps") or []) if item.get("slug") == slug), None)
        return {**meta, "install": install_entry["cards"] if install_entry else []}

    def list_apps(self, *, category: str | None = None, status: str | None = None) -> list[dict]:
        data = self._safe("discovery.json", {"apps": []})
        return [
            app
            for app in (data.get("apps") or [])
            if (not category or app.get("category") == category) and (not status or app.get("status") == status)
        ]

    def get_trending(self) -> dict:
        return self._safe("feeds/trending.json", {"trending": [], "rising": [], "recentlyUpdated": []})

    def get_related(self, slug: str) -> list[dict]:
        data = self._safe("feeds/related.json", {"related": {}})
        return (data.get("related") or {}).get(slug, [])

    def get_reputation(self) -> dict:
        return self._safe("feeds/reputation.json", {"sources": []})

    def get_health(self) -> dict:
        return self._safe("feeds/download-intelligence.json", {"apps": [], "summary": {}})

    def get_analytics(self) -> dict:
        return self._safe("feeds/analytics.json", {"totals": {}})

    def get_community(self) -> dict:
        return self._safe("feeds/community.json", {"popular": [], "recentlyAdded": [], "rising": [], "requested": []})

    def get_install(self, slug: str | None = None) -> Any:
        data = self._safe("feeds/install.json", {"apps": [], "master": {"cards": []}})
        if not slug:
            return data.get("master", {})
        entry = next((item for item in (data.get("apps") or []) if item.get("slug") == slug), None)
        return entry["cards"] if entry else []

    def get_compare(self, left: str, right: str) -> dict | None:
        data = self._safe("feeds/compare.json", {"pairs": []})
        for pair in data.get("pairs") or []:
            if (pair["left"]["slug"] == left and pair["right"]["slug"] == right) or (
                pair["left"]["slug"] == right and pair["right"]["slug"] == left
            ):
                return pair
        return None

    def get_search_index(self) -> dict:
        return self._safe("feeds/search-index.json", {"documents": []})


__all__ = ["OmniSource", "OmniSourceError"]
