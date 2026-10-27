"""The transparency chain only records complete, real byte observations."""

import copy
import unittest

from omnisource.transparency import append_observations, changed_slugs, empty_log, validate_log


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
