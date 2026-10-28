"""Regression coverage for the existing YouTube Plus catalog entry."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from omnisource.constants import Paths
from omnisource.di import Container
from omnisource.domain import App, Catalog, RemoteAsset, RemoteRelease, SourceType, SyncReport
from omnisource.pipeline import stage_sync
from omnisource.providers.registry import ProviderRegistry
from omnisource.tracking import select_versions


def release(tag: str, version: str, *, filename: str | None = None, tweak: str = "6.0b2") -> RemoteRelease:
    name = filename or f"YouTubePlus_{version}_{tweak}.ipa"
    return RemoteRelease(
        tag=tag,
        name=tag,
        body="Release notes",
        published_at="2026-10-27T12:00:00Z",
        assets=(
            RemoteAsset(
                name=name,
                download_url=f"https://github.com/mrdrvt99/YouProEXTRA/releases/download/{tag}/{name}",
                size=123,
            ),
        ),
    )


class YouTubePlusCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        entries = [item for item in catalog["apps"] if item["slug"] == "ytlite"]
        if len(entries) != 1:
            raise AssertionError("YouTube Plus must retain exactly one ytlite entry")
        cls.app = App(slug="ytlite", raw=entries[0])

    def test_name_and_existing_source_identity(self) -> None:
        app = self.app
        self.assertEqual(app.name, "YouTube Plus")
        self.assertEqual(app.bundle_id, "com.google.ios.youtube")
        self.assertEqual(app.status, "beta")
        self.assertEqual(app.raw["compatibility"]["minOSVersion"], "17.0")
        self.assertIsNotNone(app.upstream)
        assert app.upstream is not None
        self.assertEqual(app.upstream.repo, "mrdrvt99/YouProEXTRA")
        self.assertEqual(app.upstream.tag_prefix, "ytl-ipa")
        self.assertFalse(app.upstream.sort_by_tag_number)

    def test_published_feeds_and_api_match_the_synced_entry(self) -> None:
        state = json.loads((ROOT / "feeds" / "state.json").read_text(encoding="utf-8"))["ytlite"]
        newest = state["versions"][0]
        for path in ("apps.json", "feeds/ytlite.json", "feeds/single/ytlite.json", "feeds/clients/altstore.json"):
            with self.subTest(path=path):
                doc = json.loads((ROOT / path).read_text(encoding="utf-8"))
                entries = [entry for entry in doc["apps"] if entry.get("omnisource", {}).get("slug") == "ytlite"]
                self.assertEqual(len(entries), 1)
                app = entries[0]
                self.assertEqual(app["name"], self.app.name)
                self.assertEqual(app["version"], newest["version"])
                self.assertEqual(app["downloadURL"], newest["downloadURL"])
                self.assertEqual(app["minOSVersion"], newest["minOSVersion"])
                self.assertEqual(
                    [(version["version"], version["minOSVersion"]) for version in app["versions"]],
                    [(version["version"], version["minOSVersion"]) for version in state["versions"]],
                )
        api = json.loads((ROOT / "api" / "v2" / "apps" / "ytlite.json").read_text(encoding="utf-8"))
        self.assertEqual(api["app"]["name"], self.app.name)
        self.assertEqual(api["app"]["minOSVersion"], newest["minOSVersion"])
        self.assertEqual(api["newest"]["downloadURL"], newest["downloadURL"])

    def test_incremental_sync_refreshes_retagged_older_versions(self) -> None:
        newest = release("ytl-ipa6", "21.43.5")
        older = release("ytl-ipa4", "21.33.6")

        class FakeProvider:
            name = "github"
            source_type = SourceType.GITHUB_RELEASES

            def __init__(self) -> None:
                self.incremental: bool | None = None

            def fetch_releases(self, source, *, previous_latest_url=None, incremental=False):
                self.incremental = incremental
                return [] if incremental else [newest, older]

        ref = self.app.upstream
        assert ref is not None
        previous = select_versions(app_name=self.app.name, ref=ref, releases=[newest, release("ytl-ipa5", "21.33.6")])
        state = {"ytlite": {"versions": previous}}
        provider = FakeProvider()
        registry = ProviderRegistry()
        registry.register(provider)
        report = SyncReport()
        with tempfile.TemporaryDirectory() as tmp:
            container = Container(paths=Paths.from_root(Path(tmp)), http=MagicMock(), providers=registry)
            stage_sync(
                container,
                Catalog(source={}, clients=[], apps=[self.app]),
                state,
                only={"ytlite"},
                incremental=True,
                report=report,
                workers=1,
            )
        self.assertFalse(provider.incremental, "complete version histories must not use the latest-only fast path")
        self.assertEqual(state["ytlite"]["versions"][0]["downloadURL"], previous[0]["downloadURL"])
        self.assertIn("ytl-ipa4/", state["ytlite"]["versions"][1]["downloadURL"])
        self.assertEqual(report.apps_incremental_hit, 0)

    def test_search_finds_renamed_app_and_legacy_aliases(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "js" / "youtube_plus_search.cjs")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_release_selection_and_compatibility_survive_renumbered_tags(self) -> None:
        ref = self.app.upstream
        assert ref is not None
        # Tags are deliberately out of version order; another app's asset in
        # the same repository must never become the YouTube Plus download.
        releases = [
            release("ytl-ipa9", "21.33.6"),
            release("ytl-ipa2", "21.43.5"),
            release("ytl-ipa8", "20.21.6", tweak="5.2.2"),
            release("ytl-ipa7", "19.20.2", tweak="5.2.2"),
            release("ytl-ipa6", "21.24.3", tweak="5.2.2"),
            release("ytl-ipa99", "99.1.0", filename="YouPro_99.1.0.ipa"),
            release("youpro-ipa99", "99.1.0"),
        ]
        versions = select_versions(
            app_name=self.app.name,
            ref=ref,
            releases=releases,
            pattern=re.compile(ref.asset_name_pattern),
        )
        self.assertEqual([v["version"] for v in versions], ["21.43.5", "21.33.6", "21.24.3", "20.21.6", "19.20.2"])
        self.assertEqual([v["minOSVersion"] for v in versions], ["17.0", "16.0", "17.0", "15.0", "14.0"])
        self.assertIn("ytl-ipa2/YouTubePlus_21.43.5", versions[0]["downloadURL"])


if __name__ == "__main__":
    unittest.main()
