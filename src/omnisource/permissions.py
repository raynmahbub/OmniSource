"""Compare version-specific declarations without inventing missing history."""

from __future__ import annotations

from typing import Any


def compare_permissions(new: Any, old: Any) -> dict[str, Any] | None:
    if not isinstance(new, dict) or not isinstance(old, dict):
        return None
    result: dict[str, Any] = {}
    if isinstance(new.get("entitlements"), list) and isinstance(old.get("entitlements"), list):
        current = {value for value in new["entitlements"] if isinstance(value, str)}
        prior = {value for value in old["entitlements"] if isinstance(value, str)}
        result["entitlementsAdded"] = sorted(current - prior)
        result["entitlementsRemoved"] = sorted(prior - current)
    if isinstance(new.get("privacy"), dict) and isinstance(old.get("privacy"), dict):
        current_priv = {str(key): value for key, value in new["privacy"].items() if isinstance(value, str)}
        prior_priv = {str(key): value for key, value in old["privacy"].items() if isinstance(value, str)}
        result["privacyAdded"] = sorted(current_priv.keys() - prior_priv.keys())
        result["privacyRemoved"] = sorted(prior_priv.keys() - current_priv.keys())
        result["privacyChanged"] = sorted(
            key for key in current_priv.keys() & prior_priv.keys() if current_priv[key] != prior_priv[key]
        )
    return result or None
