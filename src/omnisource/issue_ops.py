"""Read-only triage for untrusted GitHub issue-form submissions."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from omnisource.discovery import newest_version

HEADINGS = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
BUNDLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{1,254}$")
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}$")


def fields(body: str) -> dict[str, str]:
    """Parse GitHub's fixed form headings, without executing their contents."""
    body = str(body or "")[:30000]
    matches = list(HEADINGS.finditer(body))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip().casefold()
        value = body[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(body)].strip()
        if name in result:  # Ambiguous repeated field: require human review.
            result[name] = ""
        else:
            result[name] = value[:2048] if value != "_No response_" else ""
    return result


def github_repo(value: str) -> str:
    value = value.strip().removesuffix(".git").strip("/")
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/") :]
    if not REPO.fullmatch(value) or ".." in value or value.endswith("."):
        return ""
    return value


def probe_github(repo: str) -> str:
    """Only request the fixed GitHub API host, never a user-selected network URL."""
    if not github_repo(repo):
        return "not checked"
    owner, name = repo.split("/")
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}"

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
            return None

    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "OmniSource-issue-triage"}
    )
    try:
        with opener.open(request, timeout=10) as response:
            return f"GitHub repository API responded HTTP {response.status}"
    except urllib.error.HTTPError as error:
        return f"GitHub repository API responded HTTP {error.code}; this does not establish whether an IPA exists"
    except (OSError, ValueError):
        return "GitHub repository API unavailable; no availability conclusion"


def _safe_json(value: Any) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=True)
    for char, escaped in (("`", r"\u0060"), ("@", r"\u0040"), ("<", r"\u003c"), (">", r"\u003e"), ("&", r"\u0026")):
        text = text.replace(char, escaped)
    return text


def analyze(issue: dict[str, Any], catalog: dict[str, Any], state: dict[str, Any], *, network: bool = False) -> str:
    labels = {str(item.get("name") or "") for item in issue.get("labels", []) if isinstance(item, dict)}
    data = fields(str(issue.get("body") or ""))
    apps = [item for item in catalog.get("apps", []) if isinstance(item, dict)]
    lines = ["## Automated intake (review required)", ""]
    if "app-request" in labels:
        name = data.get("app name", "").splitlines()[0][:120] if data.get("app name") else ""
        bundle = data.get("bundle identifier", "").strip()
        upstream = data.get("official upstream", "").strip()
        repo = github_repo(upstream)
        valid_url = False
        try:
            parsed = urllib.parse.urlsplit(upstream)
            valid_url = (
                parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
            )
        except ValueError:
            pass
        matches = [
            str(app.get("name") or app.get("slug") or "")
            for app in apps
            if bundle and str(app.get("bundleIdentifier") or "").casefold() == bundle.casefold()
        ]
        name_status = "provided" if name else "missing"
        bundle_status = "valid syntax" if BUNDLE.fullmatch(bundle) else "missing or invalid syntax"
        lines.append(f"- Name: {name_status}; bundle identifier: {bundle_status}.")
        lines.append(
            f"- Upstream: {'GitHub repository' if repo else 'HTTPS URL' if valid_url else 'missing or invalid'}."
        )
        lines.append(
            f"- Existing shared bundle entries: {len(matches)}. A shared ID can be an alternative or a conflict."
        )
        if repo and network:
            lines.append("- " + probe_github(repo) + ".")
        draft = {
            "name": name,
            "bundleIdentifier": bundle,
            "upstreamURL": "https://github.com/" + repo if repo else upstream,
        }
        lines += [
            "",
            "Draft fields only (not a complete or validated catalog entry):",
            "```json",
            _safe_json(draft),
            "```",
        ]
    elif "broken-link" in labels:
        app_name = data.get("app", "").strip().casefold()
        matches = [
            app
            for app in apps
            if app_name and app_name in {str(app.get("slug") or "").casefold(), str(app.get("name") or "").casefold()}
        ]
        reported = data.get("url that fails", "").strip()
        current = newest_version(state, str(matches[0].get("slug"))) if len(matches) == 1 else {}
        same = bool(reported and reported == str(current.get("downloadURL") or ""))
        lines.append(f"- Catalog match: {'one app' if len(matches) == 1 else 'ambiguous or not found'}.")
        lines.append(f"- Reported URL matches current download: {'yes' if same else 'no or unknown'}.")
        lines.append("- A single report does not establish that the project is unmaintained or authorize a fallback.")
    else:
        return ""
    lines += [
        "",
        "This intake does not run a sync, execute submitted text, update the catalog, publish binaries, "
        "or open a PR. Maintainer verification is required.",
    ]
    return "\n".join(lines) + "\n"
