"""Webhook notifications dispatcher for Discord, Telegram, ntfy and generic webhooks.

Sends rich notifications when new releases or updates are detected.
Runs using only the Python standard library.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from omnisource.constants import USER_AGENT
from omnisource.domain import UpdateEvent
from omnisource.logutil import log


def send_discord_notification(
    webhook_url: str,
    updates: list[UpdateEvent | dict[str, Any]],
    *,
    source_name: str = "OmniSource",
    base_url: str = "https://raynmahbub.github.io/OmniSource",
    timeout: float = 15.0,
) -> bool:
    """Send a rich Discord webhook embed for a list of release updates."""
    if not webhook_url or not updates:
        return False

    embeds: list[dict[str, Any]] = []
    for item in updates[:10]:
        app_id = item.app_id if isinstance(item, UpdateEvent) else str(item.get("appId") or "")
        name = item.name if isinstance(item, UpdateEvent) else str(item.get("name") or app_id)
        version = item.version if isinstance(item, UpdateEvent) else str(item.get("version") or "")
        prev_ver = item.previous_version if isinstance(item, UpdateEvent) else item.get("previousVersion")
        date_str = item.release_date if isinstance(item, UpdateEvent) else str(item.get("releaseDate") or "")
        download_url = item.download_url if isinstance(item, UpdateEvent) else str(item.get("downloadUrl") or "")
        changelog = item.changelog if isinstance(item, UpdateEvent) else str(item.get("changelog") or "")
        kind = item.kind if isinstance(item, UpdateEvent) else str(item.get("kind") or "updated")

        ver_label = f"v{prev_ver} ➔ v{version}" if prev_ver and prev_ver != version else f"v{version}"
        title = f"🚀 {name} {ver_label}" if kind != "new" else f"✨ {name} v{version} (New App)"

        description_lines = []
        if changelog:
            clean_cl = changelog.strip()
            if len(clean_cl) > 400:
                clean_cl = clean_cl[:397] + "…"
            description_lines.append(f"```{clean_cl}```")

        links = [
            f"[📥 Direct IPA]({download_url})" if download_url else "",
            f"[📱 Add Feed]({base_url}/{app_id}.json)",
            f"[🌐 Website]({base_url})",
        ]
        description_lines.append(" · ".join(link for link in links if link))

        embed = {
            "title": title,
            "url": f"{base_url}/{app_id}.json",
            "description": "\n\n".join(description_lines),
            "color": 0x5B5BD6,
            "thumbnail": {"url": f"{base_url}/assets/{app_id.capitalize()}.png"},
            "footer": {"text": f"{source_name} · Release Date: {date_str or 'Today'}"},
        }
        embeds.append(embed)

    payload = {
        "username": source_name,
        "avatar_url": f"{base_url}/assets/OmniSource.png",
        "embeds": embeds,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status in (200, 204)
    except Exception as error:
        log.warning("Discord webhook notification failed: %s", error)
        return False


def send_telegram_notification(
    bot_token: str,
    chat_id: str,
    updates: list[UpdateEvent | dict[str, Any]],
    *,
    source_name: str = "OmniSource",
    base_url: str = "https://raynmahbub.github.io/OmniSource",
    timeout: float = 15.0,
) -> bool:
    """Send formatted Telegram HTML messages for a list of release updates."""
    if not bot_token or not chat_id or not updates:
        return False

    success = True
    for item in updates[:5]:
        app_id = item.app_id if isinstance(item, UpdateEvent) else str(item.get("appId") or "")
        name = item.name if isinstance(item, UpdateEvent) else str(item.get("name") or app_id)
        version = item.version if isinstance(item, UpdateEvent) else str(item.get("version") or "")
        prev_ver = item.previous_version if isinstance(item, UpdateEvent) else item.get("previousVersion")
        download_url = item.download_url if isinstance(item, UpdateEvent) else str(item.get("downloadUrl") or "")
        changelog = item.changelog if isinstance(item, UpdateEvent) else str(item.get("changelog") or "")
        kind = item.kind if isinstance(item, UpdateEvent) else str(item.get("kind") or "updated")

        if prev_ver and prev_ver != version:
            ver_str = f"<code>{prev_ver}</code> ➔ <code>{version}</code>"
        else:
            ver_str = f"<code>{version}</code>"
        header = f"🚀 <b>{name}</b> {ver_str}" if kind != "new" else f"✨ <b>{name}</b> <code>{version}</code> (New)"

        msg_lines = [header, ""]
        if changelog:
            clean_cl = changelog.strip().replace("<", "&lt;").replace(">", "&gt;")
            if len(clean_cl) > 300:
                clean_cl = clean_cl[:297] + "…"
            msg_lines.append(f"<blockquote>{clean_cl}</blockquote>")
            msg_lines.append("")

        if download_url:
            msg_lines.append(f'📥 <a href="{download_url}">Download IPA</a>')
        msg_lines.append(f'📱 <a href="{base_url}/{app_id}.json">Add Single Feed</a>')
        msg_lines.append(f'🌐 <a href="{base_url}">{source_name} Source</a>')

        payload = {
            "chat_id": chat_id,
            "text": "\n".join(msg_lines),
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status != 200:
                    success = False
        except Exception as error:
            log.warning("Telegram notification failed for %s: %s", name, error)
            success = False
    return success


def send_ntfy_notification(
    target: str,
    updates: list[UpdateEvent | dict[str, Any]],
    *,
    source_name: str = "OmniSource",
    base_url: str = "https://raynmahbub.github.io/OmniSource",
    timeout: float = 15.0,
) -> bool:
    """Publish release updates to an ntfy.sh topic (push notifications)."""
    if not target or not updates:
        return False
    if not target.startswith(("http://", "https://")):
        target = f"https://ntfy.sh/{target.lstrip('/')}"

    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    token = os.environ.get("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    success = True
    for item in updates[:5]:
        app_id = item.app_id if isinstance(item, UpdateEvent) else str(item.get("appId") or "")
        name = item.name if isinstance(item, UpdateEvent) else str(item.get("name") or app_id)
        version = item.version if isinstance(item, UpdateEvent) else str(item.get("version") or "")
        prev_ver = item.previous_version if isinstance(item, UpdateEvent) else item.get("previousVersion")
        changelog = item.changelog if isinstance(item, UpdateEvent) else str(item.get("changelog") or "")
        download_url = item.download_url if isinstance(item, UpdateEvent) else str(item.get("downloadUrl") or "")

        ver_label = f"v{prev_ver} ➔ v{version}" if prev_ver and str(prev_ver) != str(version) else f"v{version}"
        message = f"**{name}** {ver_label} is live in {source_name}."
        if changelog:
            clean_cl = changelog.strip()
            if len(clean_cl) > 500:
                clean_cl = clean_cl[:497] + "…"
            message += f"\n\n{clean_cl}"
        if download_url:
            message += f"\n\n📥 {download_url}"

        payload = {
            "topic": target.rsplit("/", 1)[-1],
            "title": f"{name} {ver_label}",
            "message": message,
            "tags": ["tada"],
            "click": download_url or f"{base_url}/{app_id}.json",
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                target,
                data=data,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status not in (200, 201, 204):
                    success = False
        except Exception as error:
            log.warning("ntfy notification failed for %s: %s", name, error)
            success = False
    return success


def send_generic_webhook(
    webhook_url: str,
    updates: list[UpdateEvent | dict[str, Any]],
    *,
    source_name: str = "OmniSource",
    base_url: str = "https://raynmahbub.github.io/OmniSource",
    timeout: float = 15.0,
) -> bool:
    """POST a structured JSON payload to any webhook (Slack/Matrix/Pushover/...)."""
    if not webhook_url or not updates:
        return False

    serialized = []
    for item in updates[:10]:
        if isinstance(item, UpdateEvent):
            serialized.append(item.to_json())
        else:
            serialized.append(dict(item))
    payload = {
        "source": source_name,
        "baseUrl": base_url,
        "event": "release-update",
        "updates": serialized,
    }

    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    secret = os.environ.get("OMNISOURCE_WEBHOOK_SECRET")
    if secret:
        headers["X-OmniSource-Secret"] = secret

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status in (200, 201, 202, 204)
    except Exception as error:
        log.warning("generic webhook notification failed: %s", error)
        return False


def dispatch_configured_notifications(
    updates: list[UpdateEvent | dict[str, Any]],
    *,
    source_name: str = "OmniSource",
    base_url: str = "https://raynmahbub.github.io/OmniSource",
) -> None:
    """Dispatch updates to every transport configured through environment variables.

    Transports
    ----------
    ``DISCORD_WEBHOOK_URL``
        Rich embed to a Discord channel webhook.
    ``TELEGRAM_BOT_TOKEN`` + ``TELEGRAM_CHAT_ID``
        Formatted HTML message to a Telegram chat.
    ``NTFY_URL``/``NTFY_TOPIC`` (+ optional ``NTFY_TOKEN``)
        Push notification to an ntfy.sh topic.
    ``OMNISOURCE_WEBHOOK_URL`` (+ optional ``OMNISOURCE_WEBHOOK_SECRET``)
        Structured JSON POST to any webhook endpoint.
    """
    if not updates:
        return

    discord_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if discord_url:
        log.info("Dispatching update notification to Discord...")
        send_discord_notification(discord_url, updates, source_name=source_name, base_url=base_url)

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat:
        log.info("Dispatching update notification to Telegram...")
        send_telegram_notification(telegram_token, telegram_chat, updates, source_name=source_name, base_url=base_url)

    ntfy_target = os.environ.get("NTFY_URL") or os.environ.get("NTFY_TOPIC")
    if ntfy_target:
        log.info("Dispatching update notification to ntfy...")
        send_ntfy_notification(ntfy_target, updates, source_name=source_name, base_url=base_url)

    generic_url = os.environ.get("OMNISOURCE_WEBHOOK_URL")
    if generic_url:
        log.info("Dispatching update notification to generic webhook...")
        send_generic_webhook(generic_url, updates, source_name=source_name, base_url=base_url)
