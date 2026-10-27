"""Monitoring snapshots, primary/mirror probes and safe repair planning."""

from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from omnisource import probes, selfheal
from omnisource.domain import App, Catalog
from omnisource.feeds.altstore import render_altstore_app
from omnisource.monitor import build_status_doc
from omnisource.monitor_import import import_snapshot

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProbeReliabilityTests(unittest.TestCase):
    def test_transient_failure_is_retried(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.status = 200
        with (
            mock.patch.object(
                probes.urllib.request, "urlopen", side_effect=[TimeoutError("timed out"), response]
            ) as open_url,
            mock.patch.object(probes.time, "sleep"),
        ):
            result = probes.probe_url("https://example.com/app.ipa")
        self.assertTrue(result["ok"])
        self.assertEqual(open_url.call_count, 2)
        self.assertEqual(result["error"], "")

    def test_head_rejection_uses_a_one_byte_range_get(self) -> None:
        error = urllib.error.HTTPError("https://example.com/app.ipa", 405, "not allowed", None, None)
        response = mock.MagicMock()
        response.__enter__.return_value.status = 206
        with mock.patch.object(probes.urllib.request, "urlopen", side_effect=[error, response]) as open_url:
            result = probes.probe_url("https://example.com/app.ipa")
        self.assertTrue(result["ok"])
        request = open_url.call_args_list[1].args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Range"), "bytes=0-0")
        response.__enter__.return_value.read.assert_called_once_with(1)

    def test_only_failed_primary_probes_declared_fallbacks(self) -> None:
        apps = [
            {
                "name": "One",
                "omnisource": {"slug": "one"},
                "downloadURL": "https://x.test/one.ipa",
                "fallbackDownloadURLs": ["https://m.test/one.ipa", "https://m.test/one.ipa", "http://bad.test/one.ipa"],
            },
            {
                "name": "Two",
                "omnisource": {"slug": "two"},
                "downloadURL": "https://x.test/two.ipa",
                "fallbackDownloadURLs": ["https://m.test/two.ipa"],
            },
        ]
        calls = []

        def run(urls, **_kwargs):
            calls.append(urls)
            return [{"url": url, "ok": url != "https://x.test/one.ipa", "status": 200, "error": ""} for url in urls]

        with mock.patch.object(probes, "_run", side_effect=run):
            records = probes.check_downloads(apps)
        self.assertEqual(calls[1], ["https://m.test/one.ipa"])
        by_id = {item["id"]: item for item in records}
        self.assertFalse(by_id["one"]["ok"], "a live mirror must not hide a broken primary")
        self.assertTrue(by_id["one"]["fallbacks"][0]["ok"])
        self.assertNotIn("fallbacks", by_id["two"])

    def test_offline_status_preserves_real_probe_timestamp_and_bytes(self) -> None:
        script = load_script("monitoring_status_for_test", "scripts/monitoring/report_status.py")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "status.json"
            original = '{"generatedAt":"2026-10-20T09:00:00Z","overall":"degraded"}\n'
            path.write_text(original)
            with (
                mock.patch("sys.stdout", new_callable=io.StringIO),
                mock.patch.object(script, "check_downloads") as check,
            ):
                self.assertEqual(script.main(["--offline", "--out", str(path)]), 0)
            self.assertEqual(path.read_text(), original)
            check.assert_not_called()

    def test_monitor_uses_probe_time_not_status_change_time(self) -> None:
        app = App(
            slug="demo",
            raw={"slug": "demo", "name": "Demo", "bundleIdentifier": "com.example.demo", "developerName": "Example"},
        )
        catalog = Catalog(source={}, clients=[], apps=[app])
        state = {
            "demo": {
                "versions": [
                    {
                        "version": "1",
                        "date": "2026-01-01",
                        "downloadURL": "https://x.test/new.ipa",
                        "localizedDescription": "",
                        "size": 1,
                    }
                ],
                "health": {
                    "reachable": True,
                    "since": "2026-01-01",
                    "measuredAt": "2026-10-01",
                    "checkedURL": "https://x.test/old.ipa",
                },
            }
        }
        result = build_status_doc(catalog, state)["sources"][0]
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["checkedAt"], "")
        state["demo"]["health"].pop("checkedURL")
        self.assertEqual(build_status_doc(catalog, state)["sources"][0]["status"], "unknown")
        self.assertIsNone(
            render_altstore_app(catalog, app, state["demo"]["versions"], state["demo"]["health"])["omnisource"][
                "health"
            ]["downloadReachable"]
        )
        state["demo"]["health"]["checkedURL"] = "https://x.test/new.ipa"
        result = build_status_doc(catalog, state)["sources"][0]
        self.assertEqual(result["checkedAt"], "2026-10-01")
        feed = render_altstore_app(catalog, app, state["demo"]["versions"], state["demo"]["health"])
        self.assertEqual(feed["omnisource"]["health"]["lastCheckedAt"], "2026-10-01")

    def test_import_uses_newer_same_day_timestamp_but_not_ambiguous_date(self) -> None:
        app = App(
            slug="demo",
            raw={"slug": "demo", "name": "Demo", "bundleIdentifier": "com.example.demo", "developerName": "Dev"},
        )
        catalog = Catalog(source={}, clients=[], apps=[app])
        url = "https://x.test/demo.ipa"
        state = {
            "demo": {
                "versions": [{"downloadURL": url}],
                "health": {"checkedURL": url, "measuredAt": "2026-10-27T08:00:00Z", "reachable": True},
            }
        }
        snapshot = {
            "generatedAt": "2026-10-27T14:00:00Z",
            "downloads": [{"id": "demo", "url": url, "ok": False, "status": 404}],
        }
        self.assertEqual(import_snapshot(catalog, state, snapshot)["imported"], 1)
        self.assertFalse(state["demo"]["health"]["reachable"])
        self.assertEqual(state["demo"]["health"]["measuredAt"], snapshot["generatedAt"])
        self.assertEqual(import_snapshot(catalog, state, snapshot)["imported"], 0)
        state["demo"]["health"]["measuredAt"] = "2026-10-27"
        self.assertEqual(import_snapshot(catalog, state, snapshot)["imported"], 0)
        state["demo"]["health"]["measuredAt"] = "2026-10-27T08:00:00Z"
        snapshot["generatedAt"] = "2026-10-27"
        self.assertEqual(import_snapshot(catalog, state, snapshot)["imported"], 0)

    def test_import_snapshot_preserves_time_and_rejects_wrong_url(self) -> None:
        apps = [
            App(
                slug="one",
                raw={"slug": "one", "name": "One", "bundleIdentifier": "com.example.one", "developerName": "Dev"},
            ),
            App(
                slug="two",
                raw={"slug": "two", "name": "Two", "bundleIdentifier": "com.example.two", "developerName": "Dev"},
            ),
        ]
        catalog = Catalog(source={}, clients=[], apps=apps)
        state = {
            "one": {"versions": [{"downloadURL": "https://x.test/one.ipa"}]},
            "two": {"versions": [{"downloadURL": "https://x.test/new.ipa"}], "health": {"reachable": True}},
        }
        snapshot = {
            "generatedAt": "2026-10-20T08:00:00Z",
            "downloads": [
                {"id": "One", "url": "https://x.test/one.ipa", "ok": False, "status": 404, "latency_ms": 15},
                {"id": "two", "url": "https://x.test/old.ipa", "ok": True},
            ],
        }
        self.assertEqual(import_snapshot(catalog, state, snapshot), {"imported": 1, "skipped": 1})
        self.assertFalse(state["one"]["health"]["reachable"])
        self.assertEqual(state["one"]["health"]["measuredAt"], snapshot["generatedAt"])
        self.assertEqual(state["one"]["health"]["checkedURL"], "https://x.test/one.ipa")
        self.assertEqual(state["two"]["health"], {"reachable": True})
        self.assertEqual(import_snapshot(catalog, state, snapshot), {"imported": 0, "skipped": 2})
        with self.assertRaises(ValueError):
            import_snapshot(catalog, state, {"generatedAt": "not a date", "downloads": []})


class SafeFallbackTests(unittest.TestCase):
    def test_reachable_fallback_requires_digest_comparison_before_applying(self) -> None:
        digest = "ab" * 32
        mirror = "https://m.test/app.ipa"
        app = {
            "name": "Demo",
            "omnisource": {"slug": "demo"},
            "downloadURL": "https://x.test/app.ipa",
            "fallbackDownloadURLs": [mirror],
            "versions": [{"downloadURL": "https://x.test/app.ipa", "sha256": digest}],
        }
        health = {
            "downloads": [
                {
                    "id": "demo",
                    "url": app["downloadURL"],
                    "ok": False,
                    "error": "HTTP 404",
                    "fallbacks": [{"url": mirror, "ok": True}],
                }
            ]
        }
        issues = selfheal.detect_issues(apps=[app], health=health)
        plans = selfheal.plan_repairs(issues)
        repair = next(item for item in plans if item["type"] == "broken_download")
        self.assertFalse(repair["autoFixable"])
        self.assertTrue(selfheal.suggested_patches(plans)[0]["reviewRequired"])
        fixed, applied = selfheal.apply_safe_fixes([app], plans)
        self.assertEqual(applied, 0)
        self.assertEqual(fixed[0]["downloadURL"], app["downloadURL"])
        repair["fallbackProbes"][0].update(digestVerified=True, sha256=digest)
        fixed, applied = selfheal.apply_safe_fixes([app], plans)
        self.assertEqual(applied, 1)
        self.assertEqual(fixed[0]["versions"][0]["downloadURL"], mirror)
        self.assertEqual(app["versions"][0]["downloadURL"], "https://x.test/app.ipa")

    def test_stale_probe_is_not_used_to_repair_a_new_download(self) -> None:
        app = {"name": "Demo", "omnisource": {"slug": "demo"}, "downloadURL": "https://x.test/new.ipa"}
        health = {"downloads": [{"id": "demo", "url": "https://x.test/old.ipa", "ok": False}]}
        self.assertNotIn(
            "broken_download", [item["type"] for item in selfheal.detect_issues(apps=[app], health=health)]
        )

    def test_optional_mirror_verification_requires_matching_bytes(self) -> None:
        script = load_script("selfheal_script_for_test", "scripts/selfheal.py")
        digest = "cd" * 32
        mirror = "https://m.test/app.ipa"
        issue = {"expectedSha256": digest, "fallbacks": [mirror], "fallbackProbes": [{"url": mirror, "ok": True}]}
        with mock.patch.object(script, "verify_url", return_value={"ok": True, "sha256": digest, "detail": "ok"}):
            script.verify_reachable_fallbacks([issue], max_bytes=1000, timeout=10)
        self.assertTrue(issue["fallbackProbes"][0]["digestVerified"])
        with mock.patch.object(
            script, "verify_url", return_value={"ok": False, "sha256": "ef" * 32, "detail": "mismatch"}
        ):
            script.verify_reachable_fallbacks([issue], max_bytes=1000, timeout=10)
        self.assertFalse(issue["fallbackProbes"][0]["digestVerified"])


if __name__ == "__main__":
    unittest.main()
