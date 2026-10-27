"""Comparison engine.

Builds ``feeds/compare.json`` — a precomputed lookup of every pair of apps
the website's ``compare.html`` page can render. The structure is dense but
flat enough to be consumed by any framework.

Each comparison row carries:

* **version**           — newer / older / equal
* **source**            — which upstream published each
* **verification**      — VERIFIED / COMMUNITY / MANUAL / UNVERIFIED
* **updateFrequency**   — average gap in days between versions
* **compatibility**     — minOSVersion + clients that can install
* **screenshots**       — both apps' icon URLs (so compare.html can render
                          the icon gallery when the screenshot gallery is
                          empty)
"""

from __future__ import annotations

import html
import json
from itertools import combinations
from pathlib import Path
from typing import Any

from omnisource.discovery import newest_version, source_label
from omnisource.domain import Catalog, today
from omnisource.io import atomic_write_text
from omnisource.utils.dates import average_update_gap_days

COMPARE_SCHEMA_VERSION = 1


def _update_frequency(state: dict[str, Any], slug: str) -> float:
    return round(average_update_gap_days(state, slug), 1)


def _compatibility(app: Any) -> dict[str, Any]:
    compat = app.raw.get("compatibility") if isinstance(app.raw.get("compatibility"), dict) else {}
    return {
        "minOSVersion": app.minimum_ios_version or "",
        "devices": list(compat.get("devices") or []),
    }


def _summary(app: Any, state: dict[str, Any], verification_level: str, health_ok: bool | None) -> dict[str, Any]:
    newest = newest_version(state, app.slug)
    return {
        "slug": app.slug,
        "name": app.name,
        "icon": f"assets/{app.icon}" if app.icon else "",
        "category": app.category,
        "version": str(newest.get("version") or ""),
        "releaseDate": str(newest.get("date") or ""),
        "source": source_label(app),
        "sourceURL": app.source_url,
        "verificationLevel": verification_level,
        "updateFrequencyDays": _update_frequency(state, app.slug),
        "downloadReachable": health_ok,
        "compatibility": _compatibility(app),
    }


def build_compare_doc(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any] | None = None,
    verification_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build ``feeds/compare.json``.

    V2: instead of emitting every one of the 2,926 (n*(n-1)/2) pairs as a
    3.6 MB document — which made the initial payload huge — we emit only the
    per-app summaries plus the *interesting* pairs (same bundle ID = natural
    side-by-side comparisons). The client-side compare engine
    (``src/js/compare-engine.js``) computes the matrix and recommendation for
    arbitrary pairs on demand, using the cached summaries. This keeps the
    document under ~100 KB while preserving every comparison URL.
    """
    health_doc = health_doc or {}
    health_by_slug = {item.get("slug"): item for item in health_doc.get("apps", []) if isinstance(item, dict)}
    verification_by_slug = {
        item.get("app"): item for item in (verification_doc or {}).get("apps", []) if isinstance(item, dict)
    }

    summaries: dict[str, dict[str, Any]] = {}
    for app in catalog.apps:
        summaries[app.slug] = _summary(
            app,
            state,
            str((verification_by_slug.get(app.slug) or {}).get("status") or "UNVERIFIED"),
            (health_by_slug.get(app.slug) or {}).get("downloadReachable"),
        )

    # Only pre-emit bundle-sharing pairs (the natural "you can only install one"
    # comparisons users actually click). Same-category pairs are not precomputed.
    pairs: list[dict[str, Any]] = []
    for left, right in combinations(catalog.apps, 2):
        share_bundle = left.bundle_id == right.bundle_id and bool(left.bundle_id)
        if not share_bundle:
            continue
        left_summary = summaries[left.slug]
        right_summary = summaries[right.slug]

        def _rank(summary: dict[str, Any]) -> tuple[int, str, int]:
            order = {"VERIFIED": 3, "COMMUNITY": 2, "MANUAL": 1, "UNVERIFIED": 0}
            return (
                order.get(summary["verificationLevel"], 0),
                summary["releaseDate"],
                1 if summary["downloadReachable"] else 0,
            )

        left_rank = _rank(left_summary)
        right_rank = _rank(right_summary)
        if left_rank > right_rank:
            winner = left_summary["slug"]
        elif right_rank > left_rank:
            winner = right_summary["slug"]
        else:
            winner = ""
        pairs.append(
            {
                "left": left_summary,
                "right": right_summary,
                "winner": winner,
                "shareBundle": True,
                "shareCategory": left.category == right.category,
            }
        )

    pairs.sort(
        key=lambda item: (
            item["left"]["name"].casefold(),
            item["right"]["name"].casefold(),
        )
    )

    return {
        "schemaVersion": 2,
        "generatedAt": today(),
        "count": len(catalog.apps),
        "apps": list(summaries.values()),
        "bundlePairs": pairs,
        # Keep the legacy "pairs" key as just the bundle pairs so old code that
        # iterates it doesn't see an empty list but also doesn't pay the cost.
        "pairs": pairs,
    }


# ---------------------------------------------------------------------------
# Static pair pages:  compare/<a>-vs-<b>/index.html  (Phase 9)
# ---------------------------------------------------------------------------


def _page_app(
    app: Any,
    state: dict[str, Any],
    verification: dict[str, Any],
    health: dict[str, Any],
) -> dict[str, Any]:
    newest = newest_version(state, app.slug)
    size = newest.get("size")
    return {
        "slug": app.slug,
        "name": app.name,
        "icon": f"../../assets/{app.icon}" if app.icon else "",
        "category": app.category,
        "developer": app.developer,
        "version": str(newest.get("version") or ""),
        "releaseDate": str(newest.get("date") or ""),
        "sizeBytes": int(size) if isinstance(size, (int, float)) and not isinstance(size, bool) else 0,
        "updateFrequencyDays": _update_frequency(state, app.slug),
        "verificationLevel": str(verification.get("status") or "UNVERIFIED"),
        "trustScore": float(verification.get("trustScore") or 0.0),
        "trustBadge": str(verification.get("trustBadge") or "Experimental"),
        "healthScore": int(health.get("healthScore") or 0),
        "healthStatus": str(health.get("healthStatus") or "unknown"),
        "features": app.short_description or app.description[:160],
        "detailURL": f"../../apps/{app.slug}/",
    }


def _fmt_size(size: int) -> str:
    if size <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "—"


def _health_tone(status: str) -> str:
    return {"healthy": "ok", "warning": "warn", "critical": "bad"}.get(status, "muted")


def _trust_tone(score: float) -> str:
    if score >= 7.5:
        return "ok"
    if score >= 5.0:
        return "warn"
    return "muted"


def _row(label: str, left: str, right: str, left_tone: str = "", right_tone: str = "") -> str:
    def cell(text: str, tone: str) -> str:
        cls = f' class="cmp-val {tone}"' if tone else ' class="cmp-val"'
        return f"<td{cls}>{text}</td>"

    left_td = cell(html.escape(left), left_tone)
    right_td = cell(html.escape(right), right_tone)
    return f'<tr><th scope="row">{html.escape(label)}</th>{left_td}{right_td}</tr>'


def render_compare_page(
    *,
    catalog: Catalog,
    left: dict[str, Any],
    right: dict[str, Any],
    base_url: str,
) -> str:
    """Render one ``compare/<a>-vs-<b>/index.html`` page (Phase 9)."""
    title = f"{left['name']} vs {right['name']}"
    page_url = f"{base_url}/compare/{left['slug']}-vs-{right['slug']}/"
    interactive = f"{base_url}/compare/?left={left['slug']}&right={right['slug']}"
    meta_desc = (
        f"Side-by-side comparison of {left['name']} and {right['name']}: "
        "size, category, developer, update frequency, trust, health and features."
    )
    interactive_link = f'<a href="{html.escape(interactive)}">Open interactive comparison</a>'

    rows = [
        _row("Category", left["category"], right["category"]),
        _row("Developer", left["developer"], right["developer"]),
        _row("Latest version", left["version"] or "—", right["version"] or "—"),
        _row("Release date", left["releaseDate"] or "—", right["releaseDate"] or "—"),
        _row("Download size", _fmt_size(left["sizeBytes"]), _fmt_size(right["sizeBytes"])),
        _row(
            "Update frequency",
            f"every {left['updateFrequencyDays']:g} days" if left["updateFrequencyDays"] else "no history",
            f"every {right['updateFrequencyDays']:g} days" if right["updateFrequencyDays"] else "no history",
        ),
        _row(
            "Verification",
            left["verificationLevel"].title(),
            right["verificationLevel"].title(),
        ),
        _row(
            "Trust score",
            f"{left['trustScore']:.1f}/10 · {left['trustBadge']}",
            f"{right['trustScore']:.1f}/10 · {right['trustBadge']}",
            _trust_tone(left["trustScore"]),
            _trust_tone(right["trustScore"]),
        ),
        _row(
            "Health score",
            f"{left['healthScore']}/100 · {left['healthStatus']}",
            f"{right['healthScore']}/100 · {right['healthStatus']}",
            _health_tone(left["healthStatus"]),
            _health_tone(right["healthStatus"]),
        ),
    ]

    def feature_block(app: dict[str, Any]) -> str:
        text = html.escape(app["features"]) or "No description."
        return f'<div class="cmp-feature"><h2>{html.escape(app["name"])}</h2><p>{text}</p></div>'

    def app_card(app: dict[str, Any]) -> str:
        name = html.escape(app["name"])
        sub = f"{html.escape(app['category'])} · v{html.escape(app['version'])}"
        return (
            f'<a class="cmp-app" href="{html.escape(app["detailURL"])}">\n'
            f'  <img src="{html.escape(app["icon"])}" alt="{name} icon" width="56" height="56" loading="lazy">\n'
            f'  <span><span class="nm">{name}</span><br><span class="sub">{sub}</span></span>\n'
            "</a>"
        )

    return f"""<!doctype html>
<html lang="en" data-theme="auto">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="light dark">
  <meta name="theme-color" content="#e8eef8" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#07070f" media="(prefers-color-scheme: dark)">
  <meta name="theme-color" content="#07070f" id="themeColor">
  <title>{html.escape(title)} — OmniSource</title>
  <meta name="description" content="{html.escape(meta_desc)}">
  <link rel="canonical" href="{html.escape(page_url)}">
  <meta property="og:site_name" content="OmniSource">
  <meta property="og:title" content="{html.escape(title)} — OmniSource">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{html.escape(page_url)}">
  <link rel="icon" type="image/png" href="../../assets/OmniSource.png">
  <link rel="apple-touch-icon" href="../../assets/OmniSource.png">
  <link rel="alternate" type="application/rss+xml" title="OmniSource releases" href="../../feeds/feed.xml">
  <link rel="preload" href="../../assets/design-system/tokens.css" as="style">
  <link rel="preload" href="../../assets/design-system/components.css" as="style">
  <link rel="stylesheet" href="../../assets/design-system/tokens.css">
  <link rel="stylesheet" href="../../assets/design-system/utilities.css">
  <link rel="stylesheet" href="../../assets/design-system/animations.css">
  <link rel="stylesheet" href="../../assets/design-system/components.css">
  <style>
    .cmp-hero{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;align-items:center;margin:1.2rem 0}}
    .cmp-app{{display:flex;align-items:center;gap:.8rem;padding:1rem;border-radius:14px;background:var(--surface-2,rgba(128,128,150,.08));text-decoration:none;color:inherit}}
    .cmp-app img{{width:56px;height:56px;border-radius:12px;object-fit:cover}}
    .cmp-app .nm{{font-weight:700}}
    .cmp-app .sub{{font-size:.85rem;opacity:.7}}
    .cmp-table{{width:100%;border-collapse:collapse;margin:1rem 0}}
    .cmp-table th,.cmp-table td{{padding:.7rem .9rem;
      border-bottom:1px solid var(--border,rgba(128,128,150,.2));
      text-align:left;vertical-align:top}}
    .cmp-table thead th{{text-align:center;font-size:1rem}}
    .cmp-table th[scope=row]{{font-weight:600;white-space:nowrap}}
    .cmp-val.ok{{color:var(--ok,#3fb950);font-weight:600}}
    .cmp-val.warn{{color:var(--warn,#d29922);font-weight:600}}
    .cmp-val.bad{{color:var(--bad,#f85149);font-weight:600}}
    .cmp-val.muted{{opacity:.75}}
    .cmp-feature{{padding:1rem;border-radius:14px;background:var(--surface-2,rgba(128,128,150,.06))}}
    .cmp-feature h2{{margin:0 0 .4rem}}
    @media(max-width:640px){{.cmp-hero{{grid-template-columns:1fr}}.cmp-table{{font-size:.92rem}}}}
  </style>
  <script>
    (function () {{
      try {{
        var t = localStorage.getItem('omnisource-theme');
        if (t !== 'light' && t !== 'dark') t = 'auto';
        document.documentElement.dataset.theme = t;
      }} catch (e) {{}}
    }})();
  </script>
  <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "Article",
      "headline": {json.dumps(title, ensure_ascii=False)},
      "url": {json.dumps(page_url, ensure_ascii=False)},
      "inLanguage": "en"
    }}
  </script>
</head>
<body data-page="compare">
  <main class="shell" id="main" style="padding-top:1.5rem;padding-bottom:3rem">
    <p><a href="../../compare/">← All comparisons</a> · <a href="../../">Home</a></p>
    <h1 style="font-size:1.7rem">{html.escape(title)}</h1>
    <p class="sub" style="opacity:.75">Static snapshot generated by the pipeline. {interactive_link}.</p>

    <div class="cmp-hero">
      {app_card(left)}
      {app_card(right)}
    </div>

    <table class="cmp-table">
      <thead><tr><th></th><th>{html.escape(left["name"])}</th><th>{html.escape(right["name"])}</th></tr></thead>
      <tbody>
        {chr(10).join(rows)}
      </tbody>
    </table>

    <h2 style="font-size:1.2rem">Features</h2>
    <div class="cmp-hero">
      {feature_block(left)}
      {feature_block(right)}
    </div>
  </main>
  <script src="../../js/core.js" defer></script>
</body>
</html>
"""


def render_compare_redirect(canonical_path: str) -> str:
    """Tiny meta-refresh stub for the reverse-ordered pair URL."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={html.escape(canonical_path)}">
  <title>Redirecting…</title>
  <link rel="canonical" href="{html.escape(canonical_path)}">
</head>
<body><p>Redirecting to <a href="{html.escape(canonical_path)}">the comparison page</a>.</p></body>
</html>
"""


def build_compare_pages(
    catalog: Catalog,
    state: dict[str, Any],
    health_doc: dict[str, Any],
    verification_doc: dict[str, Any],
    pages_dir: Path,
) -> list[Path]:
    """Generate one static page per unordered app pair under ``pages_dir``.

    Writes ``<a>-vs-<b>/index.html`` (alphabetical canonical order) plus a
    meta-refresh stub for the reverse order, so ``/compare/x-vs-y`` always
    resolves regardless of argument order.
    """
    health_by_slug = {item.get("slug"): item for item in health_doc.get("apps", []) if isinstance(item, dict)}
    verification_by_slug = {
        item.get("app"): item for item in verification_doc.get("apps", []) if isinstance(item, dict)
    }

    def page_app(app: Any) -> dict[str, Any]:
        return _page_app(
            app,
            state,
            verification_by_slug.get(app.slug, {}),
            health_by_slug.get(app.slug, {}),
        )

    changed: list[Path] = []
    apps = sorted(catalog.apps, key=lambda app: app.slug)
    for left, right in combinations(apps, 2):
        lp, rp = page_app(left), page_app(right)
        # Keep canonical order deterministic: alphabetical by slug.
        a, b = (lp, rp) if lp["slug"] < rp["slug"] else (rp, lp)
        canonical = f"../../compare/{a['slug']}-vs-{b['slug']}/"
        for primary, secondary in ((a, b), (b, a)):
            target = pages_dir / f"{primary['slug']}-vs-{secondary['slug']}" / "index.html"
            if primary["slug"] < secondary["slug"]:
                content = render_compare_page(catalog=catalog, left=primary, right=secondary, base_url=catalog.base_url)
            else:
                content = render_compare_redirect(canonical)
            if atomic_write_text(target, content):
                changed.append(target)
    return changed
