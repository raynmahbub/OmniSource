"""Focused checks for the static accessibility audit's accessible-name logic."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("omnisource_audit", ROOT / "scripts" / "audit.py")
assert SPEC and SPEC.loader, "cannot load scripts/audit.py"
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["omnisource_audit"] = MODULE
SPEC.loader.exec_module(MODULE)


class AccessibilityAuditTests(unittest.TestCase):
    def problems(self, body: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "page.html"
            page.write_text(f'<html lang="en"><body>{body}</body></html>', encoding="utf-8")
            return MODULE.audit_page(page)

    def test_visible_button_text_is_an_accessible_name(self) -> None:
        self.assertEqual(self.problems("<button>Save changes</button>"), [])

    def test_empty_icon_button_still_requires_a_label(self) -> None:
        problems = self.problems('<button class="close"><svg viewBox="0 0 10 10"></svg></button>')
        self.assertIn("1 button(s) without accessible text or a label", problems)
        self.assertEqual(self.problems('<button aria-label="Close"><svg></svg></button>'), [])

    def test_generated_reports_are_not_asset_usage_evidence(self) -> None:
        self.assertTrue(MODULE._is_generated_audit_report(Path("reports/dead-code.md")))
        self.assertTrue(MODULE._is_generated_audit_report(Path("reports/recommendations.md")))
        self.assertFalse(MODULE._is_generated_audit_report(Path("reports/final-audit.md")))
        self.assertFalse(MODULE._is_generated_audit_report(Path("docs/dead-code.md")))
        self.assertFalse(MODULE._is_generated_audit_report(Path("README.md")))


class DeadCodeAuditTests(unittest.TestCase):
    def test_python_invocations_count_as_uses_of_javascript_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests" / "js").mkdir(parents=True)
            (root / "tests" / "js" / "used.cjs").write_text("// harness\n", encoding="utf-8")
            (root / "tests" / "js" / "orphan.cjs").write_text("// unreferenced\n", encoding="utf-8")
            (root / "tests" / "test_runner.py").write_text('harness = "used.cjs"\n', encoding="utf-8")
            with patch.object(MODULE, "ROOT", root):
                unused, _, _, _ = MODULE.audit_files_and_globals()
        self.assertNotIn("tests/js/used.cjs", unused)
        self.assertIn("tests/js/orphan.cjs", unused)


if __name__ == "__main__":
    unittest.main()
