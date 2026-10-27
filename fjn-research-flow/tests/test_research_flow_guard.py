from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "research_flow_guard.py"
SPEC = importlib.util.spec_from_file_location("research_flow_guard", MODULE_PATH)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


def manifest(dispositions: list[dict[str, str]], candidates: list[dict[str, str]]) -> dict:
    return {
        "schema_version": 2,
        "scouting_evidence": {
            "candidate_leads": [
                {
                    "name": "ViShadow",
                    "source": "arXiv 2211.12827",
                    "relevance": "video object-shadow association",
                    "discovery_query": "video instance shadow detection",
                }
            ]
        },
        "candidate_admission": {
            "official_source_matrix": [{"name": "ViShadow"}],
            "scouting_dispositions": dispositions,
            "candidates": candidates,
        },
    }


class CandidateLeadReconciliationTest(unittest.TestCase):
    def validate(self, payload: dict) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            scouting_path = run_root / ".research_flow" / "stage_manifests" / "scouting_evidence.json"
            scouting_path.parent.mkdir(parents=True)
            scouting_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "stage": "scouting_evidence",
                        "scouting_evidence": payload["scouting_evidence"],
                    }
                )
            )
            report = GUARD.GuardReport()
            GUARD.validate_candidate_admission(run_root, payload, report)
            return report.errors

    def test_missing_disposition_is_rejected(self) -> None:
        errors = self.validate(manifest([], []))
        self.assertTrue(any("ViShadow" in error and "missing admission dispositions" in error for error in errors))

    def test_admit_requires_candidate_record(self) -> None:
        errors = self.validate(
            manifest(
                [{"name": "ViShadow", "disposition": "admit", "reason": "official code and weights"}],
                [],
            )
        )
        self.assertTrue(any("Admitted scouting lead" in error for error in errors))

    def test_admit_with_candidate_passes(self) -> None:
        payload = manifest(
            [{"name": "ViShadow", "disposition": "admit", "reason": "official code and weights"}],
            [
                {
                    "name": "ViShadow",
                    "classification": "method",
                    "admission_decision": "immediate_trial",
                    "evidence_strength": "E2",
                }
            ],
        )
        self.assertEqual(self.validate(payload), [])

    def test_merge_requires_existing_target(self) -> None:
        errors = self.validate(
            manifest(
                [
                    {
                        "name": "ViShadow",
                        "disposition": "merge",
                        "merge_into": "Video shadow family",
                        "reason": "same deliverable identity",
                    }
                ],
                [],
            )
        )
        self.assertTrue(any("target is missing" in error for error in errors))


if __name__ == "__main__":
    unittest.main()