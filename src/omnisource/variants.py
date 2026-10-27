"""Static opt-in source variants for one shared bundle-ID group.

The master feed is unchanged. Other collision groups remain unchanged too;
creating every cross-product of choices would explode the static publication.
"""

from __future__ import annotations

import re
from typing import Any

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")


def build_variant_documents(master: dict[str, Any], base_url: str) -> dict[str, dict[str, Any]]:
    apps = [a for a in master.get("apps", []) if isinstance(a, dict)]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for app in apps:
        bundle = app.get("bundleIdentifier")
        if isinstance(bundle, str) and bundle:
            grouped.setdefault(bundle, []).append(app)
    docs: dict[str, dict[str, Any]] = {}
    groups = []
    for bundle, members in sorted(grouped.items()):
        if len(members) < 2:
            continue
        choices = []
        for app in sorted(members, key=lambda a: str(a.get("name") or "").casefold()):
            meta = app.get("omnisource") if isinstance(app.get("omnisource"), dict) else {}
            slug = str(meta.get("slug") or app.get("slug") or "")
            if not SLUG.fullmatch(slug):
                continue
            url = f"{base_url.rstrip('/')}/feeds/variants/{slug}.json"
            feed = dict(master)
            feed.update(
                name=f"{master.get('name', 'OmniSource')} — {app.get('name', slug)} selection",
                identifier=f"{master.get('identifier', 'com.omnisource.source')}.variant.{slug}",
                sourceURL=url,
                subtitle="One selected alternative for this bundle ID",
                apps=[item for item in apps if item.get("bundleIdentifier") != bundle or item is app],
            )
            docs[f"variants/{slug}.json"] = feed
            choices.append({"slug": slug, "name": str(app.get("name") or slug), "url": url})
        if choices:
            groups.append({"bundleIdentifier": bundle, "choices": choices})
    docs["variants/index.json"] = {
        "schemaVersion": 1,
        "groups": groups,
        "note": "Each variant resolves only the chosen bundle group; other shared IDs remain in the feed.",
    }
    return docs
