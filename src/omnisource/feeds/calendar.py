"""Deterministic all-day release calendars and filtered RSS channels."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from omnisource.domain import Catalog
from omnisource.feeds.rss import _collect_items, _render_channel


def collect_items(
    catalog: Catalog, state: dict[str, Any], slugs: set[str] | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    items = []
    for app in catalog.apps:
        if slugs is None or app.slug in slugs:
            items.extend(_collect_items(catalog, state, slug=app.slug, limit=15))

    def stamp(item: dict[str, Any]) -> datetime:
        try:
            value = parsedate_to_datetime(str(item.get("date") or ""))
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            return datetime.min.replace(tzinfo=UTC)

    return sorted(items, key=lambda item: (stamp(item), str(item.get("guid") or "")), reverse=True)[:limit]


def _escape(value: Any) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", r"\n")
        .replace(";", r"\;")
        .replace(",", r"\,")
    )


def _fold(line: str) -> str:
    # RFC 5545: 75 octets, never split a UTF-8 code point.
    result, part, size, limit = [], "", 0, 75
    for char in line:
        n = len(char.encode("utf-8"))
        if size + n > limit:
            result.append(part)
            part, size, limit = " " + char, 1 + n, 75
        else:
            part += char
            size += n
    result.append(part)
    return "\r\n".join(result)


def render_calendar(
    catalog: Catalog, state: dict[str, Any], *, slugs: set[str] | None = None, title: str = "OmniSource releases"
) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OmniSource//Release calendar//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:" + _escape(title),
    ]
    for item in collect_items(catalog, state, slugs):
        try:
            date = parsedate_to_datetime(str(item.get("date") or "")).date()
        except (TypeError, ValueError, OverflowError):
            continue
        stamp = date.strftime("%Y%m%d")
        lines += [
            "BEGIN:VEVENT",
            "UID:" + _escape(item["guid"]) + "@omnisource",
            "DTSTAMP:" + stamp + "T000000Z",
            "DTSTART;VALUE=DATE:" + stamp,
            "DTEND;VALUE=DATE:" + (date + timedelta(days=1)).strftime("%Y%m%d"),
            "SUMMARY:" + _escape(item["title"]),
            "DESCRIPTION:" + _escape(str(item.get("description") or "")[:2000]),
            "URL:" + _escape(item["link"]),
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def render_filtered_rss(catalog: Catalog, state: dict[str, Any], *, slugs: set[str], title: str, path: str) -> str:
    base = catalog.base_url.rstrip("/")
    return _render_channel(
        title=title,
        link=base + "/",
        description="Recorded releases in this catalog selection.",
        self_link=base + "/feeds/" + path,
        items=collect_items(catalog, state, slugs, 50),
    )
