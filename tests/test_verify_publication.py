"""Exercise completed-mismatch and interrupted-run publication gates."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from omnisource.cli import main
from omnisource.errors import SyncError
from omnisource.transparency import append_observations, empty_log

ROOT = Path(__file__).resolve().parents[1]


class VerificationPublicationTests(unittest.TestCase):
    def test_completed_failure_is_valid_evidence_but_crash_and_tampering_are_not(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            receipt, state_file, report_file, ledger_file = (
                tmp / name for name in ("receipt", "state", "report", "ledger")
            )
            url = "https://example.com/demo.ipa"
            state = {"demo": {"versions": [{"version": "1", "downloadURL": url, "size": 4}]}}
            ledger = empty_log()
            append_observations(
                ledger,
                state,
                [
                    {
                        "slug": "demo",
                        "url": url,
                        "size": 4,
                        "at": "2026-10-27",
                        "sha256": "b" * 64,
                        "expectedSha256": "a" * 64,
                        "ok": False,
                    }
                ],
            )
            state_file.write_text(json.dumps(state))
            report_file.write_text(json.dumps({"totals": {"apps": 1}, "apps": [{"slug": "demo"}]}))
            ledger_file.write_text(json.dumps(ledger))
            args = [
                sys.executable,
                str(ROOT / "scripts/security/check_verification_evidence.py"),
                "--receipt",
                str(receipt),
                "--state",
                str(state_file),
                "--report",
                str(report_file),
                "--ledger",
                str(ledger_file),
            ]
            with mock.patch("omnisource.cli.run", return_value=(1, object())):
                self.assertEqual(main(["--verify-downloads", "--verification-receipt", str(receipt)]), 1)
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 0)
            self.assertFalse(ledger["entries"][0]["matchesRecorded"])
            ledger["entries"][0]["sha256"] = "c" * 64
            ledger_file.write_text(json.dumps(ledger))
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)
            with mock.patch("omnisource.cli.run", side_effect=SyncError("crashed")):
                self.assertEqual(main(["--verify-downloads", "--verification-receipt", str(receipt)]), 1)
            self.assertFalse(receipt.exists())
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)

    def test_workflow_gates_all_projections_and_keeps_failed_evidence(self):
        workflow = (ROOT / ".github/workflows/verify.yml").read_text()
        self.assertIn("--verification-receipt", workflow)
        self.assertIn("check_verification_evidence.py", workflow)
        self.assertIn("steps.evidence.outcome == 'success' && steps.validation.outcome == 'success'", workflow)
        self.assertIn("actions/upload-artifact@", workflow)
        self.assertIn("'feeds/**' 'api/**' 'apps/**'", workflow)
        self.assertIn('"$VERIFY_OUTCOME" != success', workflow)


if __name__ == "__main__":
    unittest.main()
