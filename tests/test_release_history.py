"""Tests for release tracking (ledger, comparison, rollback)."""

from __future__ import annotations

from unittest import TestCase

from omnisource.release_history import (
    build_history,
    compare_entries,
    detect_removed,
    merge_app_history,
    rollback_plan,
)


def _entry(version: str, date: str = "2026-01-01") -> dict:
    return {
        "version": version,
        "date": date,
        "downloadURL": f"https://example.com/app-{version}.ipa",
        "size": 10,
        "localizedDescription": "notes",
    }


class MergeHistoryTests(TestCase):
    def test_never_deletes_old_releases(self) -> None:
        old = [{**_entry("1.0"), "status": "current"}]
        merged = merge_app_history(old, [_entry("2.0", "2026-02-01")])
        versions = {entry["version"]: entry["status"] for entry in merged}
        self.assertEqual(versions, {"2.0": "current", "1.0": "superseded"})

    def test_removed_flagged(self) -> None:
        old = [{**_entry("9.9"), "status": "current"}]
        merged = merge_app_history(old, [_entry("1.0")])
        by_version = {entry["version"]: entry["status"] for entry in merged}
        self.assertEqual(by_version["9.9"], "removed")

    def test_build_history_shape(self) -> None:
        doc = build_history({"demo": {"versions": [_entry("1.0")]}})
        self.assertEqual(doc["appCount"], 1)
        self.assertEqual(doc["releases"], 1)
        self.assertIn("demo", doc["apps"])

    def test_quarantined_identity_mismatch_is_retained_not_reactivated(self) -> None:
        quarantined = {**_entry("1.0"), "status": "quarantined", "quarantineReason": "different app"}
        merged = merge_app_history([quarantined], [_entry("2.0", "2026-02-01"), _entry("1.0")])
        bad = next(entry for entry in merged if entry["version"] == "1.0")
        self.assertEqual(bad, quarantined)
        self.assertEqual(detect_removed([quarantined], []), [])


class CompareRollbackTests(TestCase):
    def test_compare_entries(self) -> None:
        self.assertLess(compare_entries(_entry("1.0"), _entry("2.0")), 0)
        self.assertGreater(compare_entries(_entry("2.0"), _entry("1.0")), 0)
        self.assertEqual(compare_entries(_entry("1.0"), _entry("1.0")), 0)

    def test_rollback_plan(self) -> None:
        history = [{**_entry("2.0", "2026-02-01"), "status": "current"}, {**_entry("1.0"), "status": "superseded"}]
        plan = rollback_plan(history, "1.0")
        self.assertTrue(plan["ok"])
        self.assertTrue(plan["downgrade"])
        self.assertEqual(plan["target"], "1.0")

    def test_rollback_unknown_version(self) -> None:
        plan = rollback_plan([{**_entry("1.0"), "status": "current"}], "0.1")
        self.assertFalse(plan["ok"])

    def test_rollback_excludes_quarantined_releases(self) -> None:
        current = {**_entry("2.0"), "status": "current"}
        wrong_app = {**_entry("1.0"), "status": "quarantined"}
        self.assertFalse(rollback_plan([wrong_app, current], "1.0")["ok"])
        self.assertFalse(rollback_plan([wrong_app], "1.0")["ok"])
        valid = {**_entry("1.0", "2025-12-01"), "status": "superseded", "downloadURL": "https://example.com/good.ipa"}
        self.assertEqual(rollback_plan([wrong_app, valid, current], "1.0")["downloadURL"], valid["downloadURL"])

    def test_detect_removed(self) -> None:
        gone = detect_removed([_entry("1.0"), _entry("0.9")], [_entry("1.0")])
        self.assertEqual([entry["version"] for entry in gone], ["0.9"])


if __name__ == "__main__":
    import unittest

    unittest.main()
