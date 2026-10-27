"""Artifact marks are deferred plans, never deletion operations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from artifact_review import CHECKS, render_artifact_reviews, validate_artifact_review


class ArtifactReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "run").mkdir()
        self.payload = self.root / "run/payload.pt"
        self.payload.write_bytes(b"rebuildable payload")
        (self.root / "report.md").write_text("failed, inputs and command preserved")
        self.state = {
            "runs": {"r1": {"status": "failed", "candidate_id": "c1", "directory_id": "d1",
                            "updated_at": "2026-01-01T00:00:00Z", "artifact_review_required": True}},
            "candidates": {"c1": {"status": "failed"}},
            "directories": {"d1": {"path": "run"}}, "versions": {},
        }
        assessed = datetime.now(timezone.utc)
        stat = self.payload.stat()
        self.review = {
            "schema_version": 1, "run_id": "r1", "decision": "delete_candidate",
            "reason": "已被受控反例否定，输出无后续用途，保留复现材料",
            "assessed_at": assessed.isoformat(),
            "review_after": (assessed + timedelta(days=7)).isoformat(),
            "checks": {key: {"value": True, "evidence": ["report.md::逐项核实依据"]} for key in CHECKS},
            "preserve": ["report.md"],
            "files": [{"path": "run/payload.pt", "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                       "reason": "无后续用途的中间状态", "rebuild": "按保留报告的配置与入口重建"}],
        }

    def tearDown(self):
        self.temp.cleanup()

    def errors(self):
        return validate_artifact_review(self.root, self.state, "r1", self.review)

    def test_candidate_only_marks_existing_files_and_renders_size(self):
        self.assertEqual(self.errors(), [])
        self.state["runs"]["r1"]["artifact_review"] = {"reference": "review.json", "review": self.review}
        output = render_artifact_reviews(self.state)
        self.assertIn("delete_candidate", output)
        self.assertIn(str(self.payload.stat().st_size), output)
        self.assertEqual(self.payload.read_bytes(), b"rebuildable payload")

    def test_unknown_is_not_deletion_eligible(self):
        self.review["checks"]["no_protected_dependents"]["value"] = "unknown"
        self.assertTrue(any("every value check true" in x for x in self.errors()))
        self.review["decision"] = "needs_review"
        self.assertEqual(self.errors(), [])

    def test_keep_and_unreviewed_runs_are_explicit(self):
        self.assertIn("待评估", render_artifact_reviews(self.state))
        self.review.update(decision="keep", files=[])
        self.assertEqual(self.errors(), [])
        self.review["files"] = [{"path": "run/payload.pt"}]
        self.assertTrue(any("keep must not" in x for x in self.errors()))

    def test_minimum_seven_day_delay(self):
        self.review["review_after"] = self.review["assessed_at"]
        self.assertTrue(any("at least seven days" in x for x in self.errors()))

    def test_review_cannot_predate_termination(self):
        self.state["runs"]["r1"]["updated_at"] = "2099-01-01T00:00:00Z"
        self.assertTrue(any("after run termination" in x for x in self.errors()))

    def test_passed_and_historical_candidates_stay_protected(self):
        for status in ("passed", "promoted"):
            self.state["candidates"]["c1"]["status"] = status
            self.assertTrue(any("historical candidate" in x for x in self.errors()))
        self.state["candidates"]["c1"]["status"] = "failed"
        self.state["versions"]["v2"] = {"promoted_from_candidate_id": "c1"}
        self.assertTrue(any("historical candidate" in x for x in self.errors()))

    def test_preserved_and_registered_evidence_cannot_be_marked(self):
        self.review["preserve"].append("run/payload.pt")
        self.assertTrue(any("overlaps preserve" in x for x in self.errors()))
        self.review["preserve"].pop()
        self.state["runs"]["r1"]["evidence"] = [{"reference": "run/payload.pt"}]
        self.assertTrue(any("registered evidence" in x for x in self.errors()))

    def test_file_identity_and_exact_run_ownership(self):
        original = deepcopy(self.review)
        self.review["files"][0]["size_bytes"] += 1
        self.assertTrue(any("current file size" in x for x in self.errors()))
        self.review = deepcopy(original)
        self.review["files"][0]["mtime_ns"] += 1
        self.assertTrue(any("current file identity" in x for x in self.errors()))
        for invalid in ("../payload.pt", "run/*.pt", "run", "report.md"):
            self.review = deepcopy(original)
            self.review["files"][0]["path"] = invalid
            self.assertTrue(self.errors(), invalid)
        (self.root / "run/link.pt").symlink_to(self.payload)
        self.review["files"][0]["path"] = "run/link.pt"
        self.assertTrue(any("no symlink" in x for x in self.errors()))


if __name__ == "__main__":
    unittest.main()
