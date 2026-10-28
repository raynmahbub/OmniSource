"""Regression coverage for source attribution and repaired catalog links."""

from __future__ import annotations

import html
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from omnisource.app_pages import _escape_pre_text
from omnisource.domain import App, RemoteAsset, RemoteRelease
from omnisource.intelligence import build_package_intelligence, build_source_insights
from omnisource.tracking import select_versions


def github_release(tag: str, filename: str) -> RemoteRelease:
    return RemoteRelease(
        tag=tag,
        name=tag,
        body="",
        published_at="2026-10-27T12:00:00Z",
        assets=(
            RemoteAsset(
                name=filename,
                download_url=f"https://github.com/mrdrvt99/YouProEXTRA/releases/download/{tag}/{filename}",
                size=123,
            ),
        ),
    )


class CatalogLinkRepairsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        cls.apps = {item["slug"]: App(slug=item["slug"], raw=item) for item in catalog["apps"]}
        cls.state = json.loads((ROOT / "feeds" / "state.json").read_text(encoding="utf-8"))

    def test_mornye_keeps_the_existing_spotiflac_identity(self) -> None:
        app = self.apps["spotiflac"]
        self.assertEqual(app.name, "Mornye")
        self.assertEqual(app.bundle_id, "com.zarz.mornye")
        self.assertEqual(app.upstream.repo, "mornyeapp/Mornye")
        newest = self.state[app.slug]["versions"][0]
        self.assertTrue(newest["downloadURL"].startswith("https://github.com/mornyeapp/Mornye/releases/"))
        self.assertTrue(newest["downloadURL"].endswith(".ipa"))

    def test_youtube_build_selection_survives_rotated_tags(self) -> None:
        for slug, prefix, asset_prefix in (
            ("youpro", "youproextra-ipa", "YouProExtra"),
            ("youmod", "youmod-ipa", "YouMod"),
        ):
            with self.subTest(slug=slug):
                app = self.apps[slug]
                ref = app.upstream
                self.assertEqual(app.raw["verification"]["provenance"], "community")
                self.assertEqual(app.raw["compatibility"]["minOSVersion"], "17.0")
                self.assertEqual(ref.keep_versions, 0)
                self.assertFalse(ref.sort_by_tag_number)
                releases = [
                    github_release(prefix + "9", f"{asset_prefix}_21.24.3_1.0.0.ipa"),
                    github_release(prefix + "2", f"{asset_prefix}_21.43.5_1.0.0.ipa"),
                    github_release(prefix + "99", "OtherApp_99.0.0_1.0.0.ipa"),
                    github_release("ytl-ipa999", f"{asset_prefix}_99.0.0_1.0.0.ipa"),
                ]
                versions = select_versions(
                    app_name=app.name, ref=ref, releases=releases, pattern=re.compile(ref.asset_name_pattern)
                )
                self.assertEqual([version["version"] for version in versions], ["21.43.5", "21.24.3"])
                self.assertTrue(all(version["minOSVersion"] == "17.0" for version in versions))
                self.assertIn(prefix + "2/", versions[0]["downloadURL"])

    def test_selected_feeds_reflect_synced_versions_and_provenance(self) -> None:
        for slug in ("youpro", "youmod", "inkillerplus", "ttkillerplus", "infuseplus", "sparkle"):
            with self.subTest(slug=slug):
                document = json.loads((ROOT / "feeds" / f"{slug}.json").read_text(encoding="utf-8"))
                entry = document["apps"][0]
                newest = self.state[slug]["versions"][0]
                self.assertEqual(entry["downloadURL"], newest["downloadURL"])
                self.assertEqual(entry["version"], newest["version"])
                self.assertEqual(entry["minOSVersion"], newest["minOSVersion"])
                self.assertEqual(entry["omnisource"]["sourceURL"], self.apps[slug].source_url)

    def test_non_youtube_apps_do_not_claim_the_youtube_permission_template(self) -> None:
        template = "Used to record and upload videos to YouTube."
        for app in self.apps.values():
            if app.bundle_id == "com.google.ios.youtube":
                continue
            permissions = app.raw.get("appPermissions") or {}
            privacy = permissions.get("privacy") or {}
            with self.subTest(slug=app.slug):
                self.assertNotEqual(privacy.get("NSCameraUsageDescription"), template)

    def test_flow_links_to_the_real_tweak_project_and_community_publisher(self) -> None:
        app = self.apps["messenger-flow"]
        self.assertEqual(app.repository_url, "https://github.com/dayanch96/Flow")
        self.assertEqual(app.source_url, "https://github.com/927tx/IPA-Vault")
        self.assertEqual(app.raw["verification"]["provenance"], "community")

    def test_missing_catalog_permissions_are_not_fabricated_in_the_feed(self) -> None:
        for slug in ("glow", "ime", "messenger-flow", "sparkle", "swiftgram"):
            with self.subTest(slug=slug):
                document = json.loads((ROOT / "feeds" / f"{slug}.json").read_text(encoding="utf-8"))
                self.assertEqual(document["apps"][0].get("appPermissions"), self.apps[slug].raw.get("appPermissions"))

    def test_static_pages_warn_only_for_the_checked_current_url(self) -> None:
        for slug in ("glow", "ime", "messenger-flow", "infuseplus", "youpro"):
            with self.subTest(slug=slug):
                state = self.state[slug]
                health = state.get("health") or {}
                url = state["versions"][0]["downloadURL"]
                page = (ROOT / "apps" / slug / "index.html").read_text(encoding="utf-8")
                warning = "Last download check failed"
                if health.get("reachable") is False and health.get("checkedURL") == url:
                    self.assertIn(warning, page)
                else:
                    self.assertNotIn(warning, page)

    def test_release_notes_preserve_whitespace_without_dirty_html(self) -> None:
        notes = "Hard break  \nIndented\t\n<script>bad</script>"
        escaped = _escape_pre_text(notes)
        self.assertEqual(html.unescape(escaped), notes)
        self.assertNotIn("<script>", escaped)
        self.assertTrue(all(line == line.rstrip() for line in escaped.splitlines()))

    def test_package_intelligence_uses_the_altstore_slug_and_release_history(self) -> None:
        app = {
            "name": "Example",
            "bundleIdentifier": "com.example.app",
            "versionDate": "2026-10-27",
            "versions": [{"version": "2.0"}],
            "omnisource": {"slug": "example"},
        }
        history = {"apps": {"example": [{"date": "2025-03-01"}, {"date": "2026-10-27"}]}}
        record = build_package_intelligence([app], release_history=history)["apps"][0]
        self.assertEqual(record["app_id"], "example")
        self.assertEqual(record["first_seen"], "2025-03-01")
        self.assertEqual(record["last_updated"], "2026-10-27")
        self.assertEqual(record["release_count"], 2)

    def test_quarantined_history_is_excluded_from_intelligence_and_rollback(self) -> None:
        from omnisource.release_history import rollback_plan

        app = {"omnisource": {"slug": "example"}, "name": "Example", "versionDate": "2026-10-01"}
        history = {
            "apps": {
                "example": [
                    {"version": "2.0", "date": "2026-10-01", "status": "current"},
                    {"version": "1.0", "date": "2025-01-01", "status": "quarantined"},
                ]
            }
        }
        record = build_package_intelligence([app], release_history=history)["apps"][0]
        self.assertEqual(record["release_count"], 1)
        self.assertEqual(record["first_seen"], "2026-10-01")
        source = {"source_id": "source", "apps": [{"id": "example"}]}
        insight = build_source_insights({"sources": [source]}, release_history=history)["sources"][0]
        self.assertIsNone(insight["update_frequency_days"])
        self.assertFalse(rollback_plan(history["apps"]["example"], "1.0")["ok"])

    def test_glow_fallback_does_not_assert_an_unverified_tweak_version(self) -> None:
        descriptions = [
            self.apps["glow"].raw["manualRelease"]["localizedDescription"],
            self.state["glow"]["versions"][0]["localizedDescription"],
        ]
        self.assertTrue(all("unverified" in description for description in descriptions))
        self.assertTrue(all("v1.4.4" not in description for description in descriptions))

    def test_known_cross_app_history_is_quarantined_not_deleted(self) -> None:
        ledger = json.loads((ROOT / "data" / "release_history.json").read_text(encoding="utf-8"))["apps"]
        bad = []
        for slug in ("glow", "ime", "swiftgram", "telegram-mxgram", "turrit-mxgram"):
            for release in ledger[slug]:
                name = release.get("downloadURL", "").casefold()
                if (slug == "glow" and "redditfilter" in name) or (slug != "glow" and "iqtele" in name):
                    bad.append(release)
                    self.assertEqual(release["status"], "quarantined")
                    self.assertTrue(release.get("quarantineReason"))
        self.assertEqual(len(bad), 18)

    def test_source_growth_requires_a_saved_membership_baseline(self) -> None:
        source = {"source_id": "source", "apps": [{"id": "a"}, {"id": "b"}]}
        registry = {"sources": [source]}
        legacy = {"sources": [{"source_id": "source", "trend": "growing"}]}
        first = build_source_insights(registry, previous=legacy)
        row = first["sources"][0]
        self.assertEqual(row["trend"], "stable")
        self.assertEqual(row["apps_added"], [])
        self.assertEqual(row["app_ids"], ["a", "b"])
        changed = build_source_insights(
            {"sources": [{"source_id": "source", "apps": [{"id": "b"}, {"id": "c"}]}]}, previous=first
        )["sources"][0]
        self.assertEqual(changed["trend"], "changing")
        self.assertEqual(changed["apps_added"], ["c"])
        self.assertEqual(changed["apps_removed"], ["a"])

    def test_unknown_source_health_is_not_counted_as_downtime(self) -> None:
        source = {"source_id": "source", "history": [{"health": "unknown"}, {"health": "degraded"}]}
        row = build_source_insights({"sources": [source]})["sources"][0]
        self.assertEqual(row["health_samples"], 0)
        self.assertIsNone(row["observed_uptime_percent"])
        source["history"] += [{"health": "online"}, {"health": "offline"}]
        row = build_source_insights({"sources": [source]})["sources"][0]
        self.assertEqual(row["health_samples"], 2)
        self.assertEqual(row["observed_uptime_percent"], 50.0)

    def test_published_package_intelligence_has_stable_app_ids(self) -> None:
        package = json.loads((ROOT / "data" / "package_intelligence.json").read_text(encoding="utf-8"))
        self.assertEqual({record["app_id"] for record in package["apps"]}, set(self.apps))


if __name__ == "__main__":
    unittest.main()
