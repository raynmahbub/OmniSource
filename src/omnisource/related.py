"""App relationship graph generator.

The catalog intentionally groups apps that share a bundle identifier (e.g.
multiple YouTube / YouTube Music tweaks). That structural signal plus the
declared ``category`` and ``tags`` is enough to surface a useful "if you
installed X you may also like Y" list without any manual curation.

Signals, in priority order:

1. **Bundle identifier** — apps that override the same target bundle are
   semantically the same kind of tool, so the relationship is "alternative".
2. **Same category** — broader affinity.
3. **Same developer** — author affinity.
4. **Shared tags** — niche affinity.

Each related entry is scored 0..1 and the document is consumed by the website
"Related apps" section, the app detail page sidebar and the ``api/related``
endpoint. The graph is symmetric: if A lists B, B lists A.
"""

from __future__ import annotations

from typing import Any

from omnisource.domain import Catalog, today

RELATED_SCHEMA_VERSION = 1
MAX_RELATED = 6

# All four signals get a fixed weight. The weights are intentionally
# conservative so the same-bundle signal (which is the strongest) dominates
# the ranking while still allowing tags / categories to break ties.
WEIGHTS = {
    "bundle": 0.55,
    "category": 0.20,
    "developer": 0.15,
    "tags": 0.10,
}


def _bundle(app: Any) -> str:
    return str(getattr(app, "bundle_id", "") or "")


def _category(app: Any) -> str:
    return str(getattr(app, "category", "") or "")


def _developer(app: Any) -> str:
    return str(getattr(app, "developer", "") or "")


def _tags(app: Any) -> set[str]:
    return {str(tag).casefold() for tag in (getattr(app, "tags", []) or []) if tag}


def _score_pair(source: Any, target: Any) -> tuple[float, list[str]]:
    """Return (score, reasons) describing why ``target`` is related to ``source``."""
    score = 0.0
    reasons: list[str] = []
    if _bundle(source) and _bundle(source) == _bundle(target):
        score += WEIGHTS["bundle"]
        reasons.append("Same bundle identifier")
    if _category(source) and _category(source) == _category(target):
        score += WEIGHTS["category"]
        reasons.append(f"Same category ({_category(source)})")
    if _developer(source) and _developer(source) == _developer(target):
        score += WEIGHTS["developer"]
        reasons.append(f"Same developer ({_developer(source)})")
    shared = _tags(source) & _tags(target)
    if shared:
        # Capped per-pair: with five shared tags we already get full credit.
        score += min(WEIGHTS["tags"], WEIGHTS["tags"] * (len(shared) / 3))
        reasons.append(f"Shared tags: {', '.join(sorted(shared))}")
    return min(1.0, round(score, 4)), reasons


def _entry(source: Any, target: Any, score: float, reasons: list[str], state: dict[str, Any]) -> dict[str, Any]:
    from omnisource.discovery import newest_version

    newest = newest_version(state, target.slug)
    return {
        "slug": target.slug,
        "name": target.name,
        "category": _category(target),
        "developer": _developer(target),
        "bundleId": _bundle(target),
        "version": str(newest.get("version") or ""),
        "score": score,
        "reasons": reasons,
    }


def build_related_doc(
    catalog: Catalog,
    state: dict[str, Any],
    *,
    max_related: int = MAX_RELATED,
) -> dict[str, Any]:
    """Build ``feeds/related.json``."""
    apps = list(catalog.apps)
    graph: dict[str, list[dict[str, Any]]] = {app.slug: [] for app in apps}

    for source in apps:
        scored: list[tuple[float, list[str], Any]] = []
        for target in apps:
            if target.slug == source.slug:
                continue
            score, reasons = _score_pair(source, target)
            if score <= 0:
                continue
            scored.append((score, reasons, target))
        scored.sort(key=lambda item: (item[0], item[2].name.casefold()), reverse=True)
        for score, reasons, target in scored[:max_related]:
            graph[source.slug].append(_entry(source, target, score, reasons, state))

    # Media section: every app whose name appears in MEDIA_BUNDLES or that
    # targets one of the media bundle identifiers is part of the "media
    # ecosystem" card. This is the curated "SpotiFLAC → MaxMusic" example.
    media_bundles = {
        "com.google.ios.youtube",
        "com.google.ios.youtubemusic",
        "com.spotify.client",
    }
    media_keywords = {
        "mornye",
        "spotiflac",
        "maxmusic",
        "maxtube",
        "ytlite",
        "ytmusic",
        "ytkp",
        "ytkace",
        "youmod",
        "youpro",
        "uyouenhanced",
    }
    media: list[dict[str, Any]] = []
    for app in apps:
        if _bundle(app) in media_bundles or any(k in app.slug for k in media_keywords):
            newest = (state.get(app.slug) or {}).get("versions", [{}])
            newest = newest[0] if isinstance(newest, list) and newest else {}
            media.append(
                {
                    "slug": app.slug,
                    "name": app.name,
                    "category": _category(app),
                    "developer": _developer(app),
                    "bundleId": _bundle(app),
                    "version": str(newest.get("version") or ""),
                }
            )
    media.sort(key=lambda item: item["name"].casefold())

    return {
        "schemaVersion": RELATED_SCHEMA_VERSION,
        "generatedAt": today(),
        "count": len(graph),
        "weights": WEIGHTS,
        "related": graph,
        "media": {
            "label": "Mornye & Media Ecosystem",
            "description": "Apps that target YouTube, YouTube Music, Spotify or their popular community builds.",
            "apps": media,
        },
    }
