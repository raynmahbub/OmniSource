import json
import tempfile
import unittest
from pathlib import Path

from omnisource.constants import Paths
from omnisource.transparency import empty_log
from omnisource.validation import validate_roadmap_docs
from omnisource.variants import build_variant_documents


class VariantTests(unittest.TestCase):
    def test_generated_evidence_and_variants_are_validated(self):
        apps = [
            {"name": "A", "bundleIdentifier": "com.example.same", "omnisource": {"slug": "alpha"}},
            {"name": "B", "bundleIdentifier": "com.example.same", "omnisource": {"slug": "beta"}},
        ]
        master = {"name": "Source", "apps": apps}
        with tempfile.TemporaryDirectory() as tmp:
            paths = Paths.from_root(Path(tmp))
            paths.feeds.mkdir()
            (paths.feeds / "apps.json").write_text(json.dumps(master))
            (paths.feeds / "transparency.json").write_text(json.dumps(empty_log()))
            (paths.feeds / "subscriptions.json").write_text(json.dumps({"subscriptions": [{"path": "updates.ics"}]}))
            (paths.feeds / "updates.ics").write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
            for rel, doc in build_variant_documents(master, "https://example.com").items():
                target = paths.feeds / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(doc))
            self.assertEqual(validate_roadmap_docs(paths).errors, [])
            variant = paths.feeds / "variants/alpha.json"
            broken = json.loads(variant.read_text())
            broken["apps"] = apps
            variant.write_text(json.dumps(broken))
            (paths.feeds / "updates.ics").unlink()
            self.assertTrue(any("variant differs" in e for e in validate_roadmap_docs(paths).errors))
            self.assertTrue(any("missing updates.ics" in e for e in validate_roadmap_docs(paths).errors))

    def test_other_collision_groups_remain_unchanged(self):
        apps = [
            {"name": "A", "bundleIdentifier": "com.example.a", "omnisource": {"slug": "alpha"}},
            {"name": "B", "bundleIdentifier": "com.example.a", "omnisource": {"slug": "beta"}},
            {"name": "C", "bundleIdentifier": "com.example.b", "omnisource": {"slug": "gamma"}},
            {"name": "D", "bundleIdentifier": "com.example.b", "omnisource": {"slug": "delta"}},
        ]
        docs = build_variant_documents({"apps": apps}, "https://example.com")
        self.assertEqual([a["name"] for a in docs["variants/alpha.json"]["apps"]], ["A", "C", "D"])
        self.assertEqual([a["name"] for a in docs["variants/delta.json"]["apps"]], ["A", "B", "D"])

    def test_only_selected_bundle_member_is_included_and_master_is_unchanged(self):
        apps = [
            {"name": "A", "bundleIdentifier": "com.example.same", "omnisource": {"slug": "alpha"}},
            {"name": "B", "bundleIdentifier": "com.example.same", "omnisource": {"slug": "beta"}},
            {"name": "C", "bundleIdentifier": "com.example.other", "omnisource": {"slug": "gamma"}},
        ]
        master = {"name": "OmniSource", "identifier": "com.example.source", "apps": apps}
        docs = build_variant_documents(master, "https://example.com/OmniSource")
        self.assertEqual([a["name"] for a in docs["variants/alpha.json"]["apps"]], ["A", "C"])
        self.assertEqual([a["name"] for a in docs["variants/beta.json"]["apps"]], ["B", "C"])
        self.assertEqual(master["apps"], apps)
        self.assertEqual(docs["variants/index.json"]["groups"][0]["bundleIdentifier"], "com.example.same")
        self.assertEqual(
            docs["variants/alpha.json"]["sourceURL"], "https://example.com/OmniSource/feeds/variants/alpha.json"
        )


if __name__ == "__main__":
    unittest.main()
