import unittest
from unittest.mock import patch

from omnisource.issue_ops import analyze, fields, github_repo


class IssueOpsTests(unittest.TestCase):
    def test_untrusted_fields_are_never_executed_or_rendered_as_mentions(self):
        body = """### App name

```\n@maintainer $(touch /tmp/bad)\n```

### Bundle identifier

com.example.app

### Official upstream

https://github.com/example/project
"""
        issue = {"labels": [{"name": "app-request"}], "body": body}
        catalog = {"apps": [{"slug": "other", "name": "Other", "bundleIdentifier": "com.example.app"}]}
        with patch("omnisource.issue_ops.probe_github", return_value="API responded HTTP 200") as probe:
            report = analyze(issue, catalog, {}, network=True)
        probe.assert_called_once_with("example/project")
        self.assertIn("Existing shared bundle entries: 1", report)
        self.assertIn("not a complete or validated catalog entry", report)
        self.assertIn("\\u0060", report)
        self.assertNotIn("@maintainer", report)
        self.assertIn("does not run a sync", report)

    def test_github_url_allowlist_and_duplicate_field(self):
        self.assertEqual(github_repo("https://github.com/owner/repo"), "owner/repo")
        for value in (
            "https://github.com.evil.test/owner/repo",
            "https://127.0.0.1/owner/repo",
            "owner/../../etc",
            "https://github.com/owner/repo?x=1",
        ):
            self.assertEqual(github_repo(value), "")
        self.assertEqual(fields("### App name\nOne\n### App name\nTwo")["app name"], "")

    def test_broken_report_checks_exact_current_url_without_marking_unmaintained(self):
        issue = {
            "labels": [{"name": "broken-link"}],
            "body": "### App\nDemo\n### URL that fails\nhttps://x.test/old.ipa",
        }
        catalog = {"apps": [{"slug": "demo", "name": "Demo"}]}
        state = {"demo": {"versions": [{"downloadURL": "https://x.test/new.ipa"}]}}
        report = analyze(issue, catalog, state)
        self.assertIn("no or unknown", report)
        self.assertIn("does not establish", report)


if __name__ == "__main__":
    unittest.main()
