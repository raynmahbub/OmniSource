"""Source attribution and digest evidence must describe the actual asset."""

from __future__ import annotations

import unittest

from omnisource.domain import App, Catalog
from omnisource.integrity import build_integrity_doc, digest_evidence
from omnisource.security import download_integrity, provenance_audit
from omnisource.verification import build_verification_doc, provenance_for

DIGEST = "a" * 64
URL = "https://example.com/app.ipa"
NEWEST = {"version": "1.0", "date": "2026-10-01", "downloadURL": URL, "size": 100, "sha256": DIGEST}


def app(slug: str, verification: dict) -> App:
    return App(
        slug=slug,
        raw={
            "slug": slug,
            "name": slug,
            "bundleIdentifier": f"com.example.{slug}",
            "developerName": "Example",
            "upstreamURL": "https://github.com/example/project",
            "verification": verification,
        },
    )


class ProvenanceTests(unittest.TestCase):
    def test_shared_classifier_keeps_community_and_unknown_out_of_official_counts(self) -> None:
        official = app("official", {"method": "github-release", "publisher": "example/project"})
        vault = app("vault", {"method": "altstore", "publisher": "927tx/IPA-Vault"})
        unknown = app("unknown", {"method": "", "publisher": ""})
        self.assertEqual(provenance_for(vault, "altstore", "927tx/IPA-Vault"), "community")
        self.assertEqual(provenance_for(unknown, "", ""), "unknown")
        audit = provenance_audit([official.raw, vault.raw, unknown.raw])
        self.assertEqual((audit["official"], audit["community"], audit["unknown"]), (1, 1, ["unknown"]))

    def test_explicit_unknown_and_forked_source_are_not_assumed_official(self) -> None:
        unknown = app("unknown", {"method": "github-release", "publisher": "example/project", "provenance": "unknown"})
        fork = app("fork", {"method": "github-release", "publisher": "other/packaging"})
        self.assertEqual(provenance_for(unknown, "github-release", "example/project"), "unknown")
        self.assertEqual(provenance_for(fork, "github-release", "other/packaging"), "community")

    def test_verification_level_follows_source_attribution_and_evidence(self) -> None:
        official = app("official", {"method": "github-release", "publisher": "example/project"})
        community = app("community", {"method": "altstore", "publisher": "927tx/IPA-Vault"})
        unknown = app("unknown", {"method": "github-release", "publisher": "example/project", "provenance": "unknown"})
        apps = [official, community, unknown]
        state = {entry.slug: {"versions": [dict(NEWEST)]} for entry in apps}
        health = {"apps": [{"slug": entry.slug, "downloadReachable": True} for entry in apps]}
        doc = build_verification_doc(Catalog(source={}, clients=[], apps=apps), state, health)
        by_slug = {entry["app"]: entry for entry in doc["apps"]}
        self.assertEqual(by_slug["community"]["status"], "COMMUNITY VERIFIED")
        self.assertEqual(by_slug["official"]["status"], "VERIFIED")
        self.assertEqual(by_slug["unknown"]["status"], "UNVERIFIED")
        self.assertFalse(by_slug["official"]["checks"]["hashVerified"])
        self.assertEqual(by_slug["official"]["digestEvidence"]["status"], "recorded")
        self.assertGreaterEqual(doc["totals"]["hashRecorded"], 1)

    def test_health_rollup_understands_feed_slugs_and_probe_booleans(self) -> None:
        apps = [{"name": "A", "omnisource": {"slug": "a"}, "downloadURL": URL}]
        health = {"apps": [{"slug": "a", "status": "stable", "downloadReachable": False}]}
        self.assertEqual(download_integrity(apps, health)["failing"], ["a"])
        old_probe = {"downloads": [{"id": "A", "url": "https://example.com/old.ipa", "ok": False}]}
        self.assertEqual(download_integrity(apps, old_probe)["unknown"], ["a"])


class DigestEvidenceTests(unittest.TestCase):
    def record(self, **updates: object) -> dict:
        return {
            "url": URL,
            "at": "2026-10-10",
            "ok": True,
            "expectedSha256": DIGEST,
            "sha256": DIGEST,
            "expectedSize": 100,
            **updates,
        }

    def test_recorded_is_not_matched_until_bytes_are_compared(self) -> None:
        self.assertEqual(digest_evidence(NEWEST, {})["status"], "recorded")
        matched = digest_evidence(NEWEST, {"lastFullVerification": self.record()})
        self.assertEqual(matched["status"], "matched")
        self.assertEqual(matched["origin"], "unconfirmed")
        self.assertEqual(matched["checkedAt"], "2026-10-10")

    def test_digest_mismatch_is_not_advertised_as_verified(self) -> None:
        failed = self.record(ok=False, sha256="b" * 64, detail="sha256 mismatch")
        state = {"demo": {"versions": [dict(NEWEST)], "lastFullVerification": failed}}
        evidence = digest_evidence(NEWEST, state["demo"])
        self.assertEqual(evidence["status"], "mismatch")
        self.assertEqual(evidence["checkedAt"], "2026-10-10")
        catalog = Catalog(
            source={}, clients=[], apps=[app("demo", {"method": "github-release", "publisher": "example/project"})]
        )
        doc = build_verification_doc(catalog, state, {"apps": [{"slug": "demo", "downloadReachable": True}]})
        self.assertEqual(doc["apps"][0]["status"], "UNVERIFIED")
        self.assertIn("mismatch", doc["apps"][0]["integrityFailure"]["detail"])

    def test_failed_check_only_marks_actual_mismatches_unverified(self) -> None:
        catalog = Catalog(
            source={}, clients=[], apps=[app("demo", {"method": "github-release", "publisher": "example/project"})]
        )
        for detail, expected_status, has_failure in (
            ("size mismatch", "UNVERIFIED", True),
            ("bundle id mismatch: expected a, got b", "UNVERIFIED", True),
            ("unavailable: timeout", "VERIFIED", False),
        ):
            with self.subTest(detail=detail):
                state = {
                    "demo": {"versions": [dict(NEWEST)], "lastFullVerification": self.record(ok=False, detail=detail)}
                }
                doc = build_verification_doc(catalog, state, {"apps": [{"slug": "demo", "downloadReachable": True}]})
                self.assertEqual(doc["apps"][0]["status"], expected_status)
                self.assertEqual(bool(doc["apps"][0]["integrityFailure"]), has_failure)
                self.assertEqual(doc["apps"][0]["digestEvidence"]["status"], "recorded")

    def test_legacy_verification_without_url_is_not_current_evidence(self) -> None:
        state = {"lastFullVerification": self.record()}
        state["lastFullVerification"].pop("url")
        self.assertEqual(digest_evidence(NEWEST, state)["status"], "recorded")

    def test_previous_asset_verdict_does_not_apply_to_a_new_release(self) -> None:
        state = {"lastFullVerification": self.record(url="https://example.com/old.ipa")}
        self.assertEqual(digest_evidence(NEWEST, state)["status"], "recorded")
        legacy = self.record()
        legacy.pop("url")
        self.assertEqual(digest_evidence(NEWEST, {"lastFullVerification": legacy})["status"], "recorded")
        legacy["expectedSha256"] = "b" * 64
        self.assertEqual(digest_evidence(NEWEST, {"lastFullVerification": legacy})["status"], "recorded")

    def test_transient_failure_does_not_claim_corruption_but_mismatch_does(self) -> None:
        catalog = Catalog(
            source={}, clients=[], apps=[app("demo", {"method": "github-release", "publisher": "example/project"})]
        )

        def status(detail: str) -> str:
            state = {"demo": {"versions": [dict(NEWEST)], "lastFullVerification": self.record(ok=False, detail=detail)}}
            return build_integrity_doc(catalog, state)["apps"][0]["status"]

        self.assertEqual(status("timed out"), "warn")
        self.assertEqual(status("sha256 mismatch"), "fail")


if __name__ == "__main__":
    unittest.main()
