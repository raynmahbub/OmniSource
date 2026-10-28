"""The transparency chain only records complete, real byte observations."""

import copy
import unittest

from omnisource.transparency import append_observations, changed_slugs, empty_log, evidence_for_current, validate_log


class TransparencyTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://example.com/file.ipa"
        self.state = {
            "demo": {"versions": [{"version": "1.0", "downloadURL": self.url, "size": 4, "sha256": "a" * 64}]}
        }
        self.record = {
            "slug": "demo",
            "url": self.url,
            "size": 4,
            "sha256": "a" * 64,
            "expectedSha256": "a" * 64,
            "ok": True,
            "at": "2026-10-28",
        }

    def test_append_recheck_and_silent_reupload(self):
        doc = empty_log()
        self.assertEqual(append_observations(doc, self.state, [self.record]), 1)
        self.assertEqual(append_observations(doc, self.state, [self.record]), 0)
        self.assertEqual(changed_slugs(doc, self.state, {"demo"}), set())
        changed = {**self.record, "sha256": "b" * 64, "ok": False}
        self.assertEqual(append_observations(doc, self.state, [changed]), 1)
        self.assertTrue(doc["entries"][-1]["sameVersionDifferentDigest"])
        self.assertFalse(doc["entries"][-1]["matchesRecorded"])
        self.assertEqual(changed_slugs(doc, self.state, {"demo"}), {"demo"})
        validate_log(doc)

    def test_repeat_checks_and_url_bound_change_signal(self):
        doc = empty_log()
        append_observations(doc, self.state, [self.record])
        recheck = {**self.record, "at": "2026-11-01"}
        self.assertEqual(append_observations(doc, self.state, [recheck]), 1)
        self.assertEqual(append_observations(doc, self.state, [recheck]), 0)
        current = self.state["demo"]["versions"][0]
        evidence = evidence_for_current(doc, "demo", current)
        self.assertEqual(evidence["lastHashedAt"], "2026-11-01")
        self.assertFalse(evidence["sameURLDifferentDigest"])
        append_observations(doc, self.state, [{**recheck, "at": "2026-11-02", "sha256": "b" * 64, "ok": False}])
        evidence = evidence_for_current(doc, "demo", current)
        self.assertTrue(evidence["sameURLDifferentDigest"])
        self.assertFalse(evidence["matchesRecordedAtCheck"])
        self.assertIsNone(evidence_for_current(doc, "demo", {**current, "downloadURL": "https://example.com/new.ipa"}))
        self.assertIsNone(evidence_for_current(doc, "demo", {**current, "version": "2.0"}))
        validate_log(doc)

    def test_different_mirror_is_not_labeled_a_same_url_swap(self):
        doc = empty_log()
        append_observations(doc, self.state, [self.record])
        second_url = "https://example.com/mirror.ipa"
        self.state["demo"]["versions"][0]["downloadURL"] = second_url
        append_observations(doc, self.state, [{**self.record, "url": second_url, "sha256": "b" * 64}])
        evidence = evidence_for_current(doc, "demo", self.state["demo"]["versions"][0])
        self.assertTrue(evidence["sameVersionDifferentDigest"])
        self.assertFalse(evidence["sameURLDifferentDigest"])

    def test_failed_fetch_wrong_url_and_tampering(self):
        doc = empty_log()
        self.assertEqual(append_observations(doc, self.state, [{"slug": "demo", "ok": False}]), 0)
        self.assertEqual(
            append_observations(doc, self.state, [{**self.record, "url": "https://example.com/old.ipa"}]), 0
        )
        append_observations(doc, self.state, [self.record])
        broken = copy.deepcopy(doc)
        broken["entries"][0]["size"] = 8
        with self.assertRaises(ValueError):
            validate_log(broken)


if __name__ == "__main__":
    unittest.main()
