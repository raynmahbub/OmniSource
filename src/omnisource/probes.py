"""Active health probing for sources, feeds and downloads.

:mod:`omnisource.monitor` renders the pipeline's probe history. This module
performs the probing itself as a standalone, schedule-friendly operation
(run every 30 minutes from ``monitoring.yml``):

* :func:`probe_url` — one HEAD/GET round-trip with latency measurement.
* :func:`check_sources` — probe every upstream feed / homepage concurrently.
* :func:`check_downloads` — probe every app's newest download URL.
* :func:`build_status` — roll results into ``data/status.json`` with the
  ``online`` / ``degraded`` / ``offline`` state machine.

Stdlib only; concurrency via :class:`concurrent.futures.ThreadPoolExecutor`.
Credentials are never attached: probes are anonymous by design.
"""

from __future__ import annotations

import concurrent.futures
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from omnisource.constants import USER_AGENT
from omnisource.http import is_http_url

ONLINE = "online"
DEGRADED = "degraded"
OFFLINE = "offline"

STATUS_SCHEMA_VERSION = 1


def utcnow() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def probe_url(url: str, *, timeout: int = 12, retries: int = 1) -> dict[str, Any]:
    """Probe anonymously, retrying transient failures and bounding GET reads."""
    result: dict[str, Any] = {"url": url, "ok": False, "status": 0, "latency_ms": None, "error": ""}
    if not is_http_url(url):
        result["error"] = "not an http(s) URL"
        return result
    attempts = max(1, min(retries + 1, 3))
    for attempt in range(attempts):
        transient = False
        for method in ("HEAD", "GET"):
            headers = {"User-Agent": USER_AGENT}
            if method == "GET":
                headers["Range"] = "bytes=0-0"
            started = time.monotonic()
            try:
                request = urllib.request.Request(url, method=method, headers=headers)
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    code = response.status
                    if method == "GET":
                        response.read(1)
            except urllib.error.HTTPError as exc:
                result["latency_ms"] = int((time.monotonic() - started) * 1000)
                if exc.code in (403, 405, 501) and method == "HEAD":
                    continue
                result["status"] = exc.code
                result["error"] = f"HTTP {exc.code}"
                transient = exc.code in (408, 425, 429, 500, 502, 503, 504)
                break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                result["latency_ms"] = int((time.monotonic() - started) * 1000)
                result["status"] = 0
                result["error"] = str(exc) or "unreachable"
                transient = not isinstance(exc, ValueError)
                break
            result["latency_ms"] = int((time.monotonic() - started) * 1000)
            result["status"] = code
            if 200 <= code < 400:
                result.update(ok=True, error="")
                return result
            result["error"] = f"HTTP {code}"
            transient = code in (408, 425, 429, 500, 502, 503, 504)
            break
        if not transient or attempt + 1 == attempts:
            break
        time.sleep(0.5 * (attempt + 1))
    return result


def _run(urls: list[str], *, timeout: int, workers: int) -> list[dict[str, Any]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(probe_url, url, timeout=timeout): url for url in urls}
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    return sorted(results, key=lambda item: item["url"])


def check_sources(
    sources: list[dict[str, Any]],
    *,
    timeout: int = 12,
    workers: int = 16,
) -> list[dict[str, Any]]:
    """Probe each source's feed URL (falling back to its homepage)."""
    targets = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = source.get("sourceURL") or source.get("url") or source.get("homepage") or ""
        if is_http_url(url):
            targets.append((str(source.get("id") or url), url))
    probed = {item["url"]: item for item in _run([url for _, url in targets], timeout=timeout, workers=workers)}
    results = []
    for source_id, url in targets:
        probe = probed.get(url, {})
        results.append({"id": source_id, "url": url, **{k: v for k, v in probe.items() if k != "url"}})
    return sorted(results, key=lambda item: item["id"])


def app_key(app: dict[str, Any]) -> str:
    """Prefer the stable catalog slug carried by an AltStore feed entry."""
    omni = app.get("omnisource") if isinstance(app.get("omnisource"), dict) else {}
    return str(app.get("slug") or omni.get("slug") or app.get("id") or app.get("name") or "")


def declared_fallbacks(app: dict[str, Any]) -> list[str]:
    """Return only configured HTTPS fallbacks, without inventing mirrors."""
    versions = app.get("versions")
    newest = versions[0] if isinstance(versions, list) and versions and isinstance(versions[0], dict) else {}
    primary = str(app.get("downloadURL") or newest.get("downloadURL") or "")
    candidates = []
    for value in (app.get("fallbackDownloadURLs"), newest.get("fallbackDownloadURLs")):
        if isinstance(value, list):
            candidates.extend(value)
    return list(
        dict.fromkeys(
            url
            for url in candidates
            if isinstance(url, str) and url.startswith("https://") and is_http_url(url) and url != primary
        )
    )


def check_downloads(
    apps: list[dict[str, Any]],
    *,
    timeout: int = 12,
    workers: int = 16,
    max_fallbacks: int = 3,
) -> list[dict[str, Any]]:
    """Probe primary URLs, then declared fallbacks only for failed primaries.

    Reachability is not proof that a mirror serves the same binary; no URL is
    automatically substituted. Results retain the primary's status.
    """
    targets: list[tuple[str, str, dict[str, Any]]] = []
    for app in apps:
        if not isinstance(app, dict):
            continue
        url = app.get("downloadURL") or ""
        if is_http_url(url):
            targets.append((app_key(app) or str(url), str(url), app))
    urls = list(dict.fromkeys(url for _, url, _ in targets))
    probed = {item["url"]: item for item in _run(urls, timeout=timeout, workers=workers)}
    fallback_by_id = {
        app_id: declared_fallbacks(app)[: max(0, max_fallbacks)]
        for app_id, url, app in targets
        if not probed.get(url, {}).get("ok")
    }
    fallback_urls = list(dict.fromkeys(url for values in fallback_by_id.values() for url in values))
    mirrors = (
        {item["url"]: item for item in _run(fallback_urls, timeout=timeout, workers=workers)} if fallback_urls else {}
    )
    results = []
    for app_id, url, _ in targets:
        probe = probed.get(url, {})
        result = {"id": app_id, "url": url, **{k: v for k, v in probe.items() if k != "url"}}
        if fallback_by_id.get(app_id):
            result["fallbacks"] = [mirrors[item] for item in fallback_by_id[app_id] if item in mirrors]
        results.append(result)
    return sorted(results, key=lambda item: item["id"])


def state_for(ok: int, total: int) -> str:
    """Roll individual probe outcomes into one state."""
    if total == 0:
        return OFFLINE
    if ok == total:
        return ONLINE
    if ok == 0:
        return OFFLINE
    return DEGRADED


def build_status(
    source_results: list[dict[str, Any]],
    download_results: list[dict[str, Any]],
    *,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``data/status.json`` monitoring document."""
    sources_ok = sum(1 for item in source_results if item.get("ok"))
    downloads_ok = sum(1 for item in download_results if item.get("ok"))
    sources_state = state_for(sources_ok, len(source_results))
    downloads_state = state_for(downloads_ok, len(download_results))
    overall = (
        ONLINE
        if sources_state == ONLINE and downloads_state == ONLINE
        else (OFFLINE if sources_state == OFFLINE and downloads_state == OFFLINE else DEGRADED)
    )
    history: list[dict[str, Any]] = []
    if isinstance(previous, dict) and isinstance(previous.get("history"), list):
        history = [entry for entry in previous["history"] if isinstance(entry, dict)][-29:]
    checked_at = utcnow()
    history.append(
        {"at": checked_at, "overall": overall, "sourcesOk": sources_ok, "downloadsOk": downloads_ok},
    )
    return {
        "schemaVersion": STATUS_SCHEMA_VERSION,
        "generatedAt": checked_at,
        "overall": overall,
        "summary": {
            "sources": len(source_results),
            "sourcesOk": sources_ok,
            "sourcesState": sources_state,
            "downloads": len(download_results),
            "downloadsOk": downloads_ok,
            "downloadsState": downloads_state,
        },
        "sources": source_results,
        "downloads": download_results,
        "failing": sorted(
            {item["id"] for item in (*source_results, *download_results) if not item.get("ok")},
        ),
        "history": history,
    }
