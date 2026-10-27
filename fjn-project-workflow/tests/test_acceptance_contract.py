from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance_contract import acceptance_evidence_specifications, has_time_limit, validate_acceptance_report, validate_timing_measurement
from workflow_core import acceptance_snapshot_errors, parse_evidence


class TimingAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("rgb.jpg", "weights.pt", "scene.pt", "final.ply", "run.sh", "provenance.json"):
            (self.root / name).write_text("fixture", encoding="utf-8")
        self.requirement = {"scope": "end_to_end", "input_boundary": "first_rgb_read", "output_boundary": "ply_write_complete", "max_seconds": 600}
        self.raw = {**self.requirement, "run_id": "run-1", "outputs": ["final.ply"], "start": 1000.0, "end": 1427.3456}
        self.save_timer()
        self.measurement = {**self.requirement, "run_id": "run-1", "seconds": 427.3456,
            "timer": {"reference": "timer.json", "start_field": "start", "end_field": "end"},
            "boundary_evidence": ["run.sh::timer surrounds RGB processing and completed PLY write"],
            "inputs": [{"reference": "rgb.jpg", "kind": "raw_input", "generated_in_timed_run": False,
                        "provenance_evidence": ["provenance.json::raw RGB input"]}],
            "outputs": ["final.ply"]}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def save_timer(self) -> None:
        (self.root / "timer.json").write_text(json.dumps(self.raw), encoding="utf-8")

    def validate(self) -> list[str]:
        return validate_timing_measurement(self.measurement, self.requirement, self.root, {"run-1"})

    def test_cold_measurement_with_raw_input_passes(self) -> None:
        for text in ("10min内", "600秒", "within 600 seconds", "600s以内"):
            self.assertTrue(has_time_limit(text), text)
        self.assertFalse(has_time_limit("PSNR >=29 dB"))
        self.assertEqual([], self.validate())

    def test_reused_scene_payload_cannot_pass_cold_limit(self) -> None:
        self.measurement["inputs"].append({"reference": "scene.pt", "kind": "scene_state", "generated_in_timed_run": False,
            "provenance_evidence": ["provenance.json::prior scene-specific optimization"]})
        self.assertTrue(any("reused scene_state" in error for error in self.validate()))

    def test_reused_scene_is_valid_only_for_explicit_incremental_goal(self) -> None:
        self.measurement["inputs"] = [{"reference": "scene.pt", "kind": "scene_state", "generated_in_timed_run": False,
            "provenance_evidence": ["provenance.json::prior scene-specific optimization"]}]
        for item in (self.requirement, self.measurement, self.raw):
            item["scope"] = "cached_incremental"
            item["input_boundary"] = "load_cached_scene"
        self.save_timer()
        self.assertEqual([], self.validate())

    def test_scene_state_generated_inside_timer_is_allowed(self) -> None:
        self.measurement["inputs"].append({"reference": "scene.pt", "kind": "scene_state", "generated_in_timed_run": True,
            "provenance_evidence": ["provenance.json::same timed run generated scene"]})
        self.assertEqual([], self.validate())

    def test_fixed_generic_pretrained_weights_are_allowed(self) -> None:
        self.measurement["inputs"].append({"reference": "weights.pt", "kind": "generic_pretrained", "generated_in_timed_run": False,
            "provenance_evidence": ["provenance.json::generic pretrained model"]})
        self.assertEqual([], self.validate())

    def test_historical_unscoped_timer_cannot_be_relabelled_cold(self) -> None:
        self.raw = {"start": 1000.0, "end": 1427.3456, "online_wall_seconds": 427.3456}
        self.save_timer()
        self.assertTrue(any("raw timer scope" in error for error in self.validate()))

    def test_stage_scope_mismatch_and_history_sum_are_rejected(self) -> None:
        self.measurement["scope"] = "stage"
        self.assertTrue(any("does not match" in error for error in self.validate()))
        self.measurement["scope"] = "end_to_end"
        self.measurement["seconds"] = 500
        self.assertTrue(any("raw start/end" in error for error in self.validate()))

    def test_raw_timer_cannot_be_borrowed_from_another_run_or_delivery(self) -> None:
        self.raw["run_id"] = "run-other"
        self.save_timer()
        self.assertTrue(any("raw timer run_id" in error for error in self.validate()))
        self.raw["run_id"] = "run-1"
        self.raw["outputs"] = ["different.ply"]
        self.save_timer()
        self.assertTrue(any("raw timer outputs" in error for error in self.validate()))

    def test_budget_and_run_binding_and_missing_delivery_are_checked(self) -> None:
        self.requirement["max_seconds"] = 400
        self.assertTrue(any("exceeds" in error for error in self.validate()))
        self.requirement["max_seconds"] = 600
        self.measurement["run_id"] = "unrelated-run"
        self.assertTrue(any("executed run" in error for error in self.validate()))
        self.measurement["run_id"] = "run-1"
        self.measurement["outputs"] = ["missing.ply"]
        self.assertTrue(any("output missing" in error for error in self.validate()))

    def test_nans_booleans_and_negative_raw_duration_are_rejected(self) -> None:
        for value in (float("nan"), float("inf"), True, -1):
            self.measurement["seconds"] = value
            self.assertTrue(self.validate())
        self.measurement["seconds"] = 427.3456
        self.raw["end"] = 0
        self.save_timer()
        self.assertTrue(any("ordered start/end" in error for error in self.validate()))

    def test_report_cannot_pass_from_just_a_durable_metrics_path(self) -> None:
        report = {"schema_version": 1, "subject_id": "P-v1-a", "checks": [{"id": "time",
            "criterion": "RGB to PLY within 600 seconds", "passed": True,
            "run_id": "run-1",
            "evidence": ["provenance.json::metrics exist"]}]}
        self.assertTrue(validate_acceptance_report(report, self.root, "P-v1-a", {"run-1"}))
        report["checks"][0].update(timing_requirement=self.requirement, timing_measurement=self.measurement)
        self.assertEqual([], validate_acceptance_report(report, self.root, "P-v1-a", {"run-1"}))
        bad = copy.deepcopy(report)
        bad["subject_id"] = "other"
        self.assertTrue(validate_acceptance_report(bad, self.root, "P-v1-a", {"run-1"}))

    def test_quality_only_report_cannot_drop_pre_registered_time_goal(self) -> None:
        contract = {"schema_version": 1, "criteria": [{"id": "time", "criterion": "RGB to PLY within 600 seconds", "timing_requirement": self.requirement}]}
        report = {"schema_version": 1, "subject_id": "P-v1-a", "checks": [{"id": "quality", "criterion": "score improves", "passed": True, "evidence": ["run.sh::quality improves"]}]}
        errors = validate_acceptance_report(report, self.root, "P-v1-a", {"run-1"}, contract)
        self.assertTrue(any("pre-registered" in error for error in errors), errors)

    def test_quality_and_timing_cannot_come_from_different_runs(self) -> None:
        report = {"schema_version": 1, "subject_id": "P-v1-a", "checks": [
            {"id": "time", "criterion": "within 600 seconds", "passed": True, "run_id": "run-1", "evidence": ["run.sh::time"], "timing_requirement": self.requirement, "timing_measurement": self.measurement},
            {"id": "quality", "criterion": "score improves", "passed": True, "run_id": "run-2", "evidence": ["run.sh::quality"]}]}
        errors = validate_acceptance_report(report, self.root, "P-v1-a", {"run-1", "run-2"})
        self.assertTrue(any("from another" in error for error in errors), errors)

    def test_timer_boundary_and_provenance_files_are_all_snapshot_bound(self) -> None:
        report = {"checks": [{"evidence": ["provenance.json::quality"], "timing_measurement": self.measurement}]}
        sources = acceptance_evidence_specifications(report, self.root)
        snapshot = {"evidence_snapshots": parse_evidence(self.root, sources)}
        self.assertEqual([], acceptance_snapshot_errors(self.root, snapshot))
        for name in ("timer.json", "run.sh", "provenance.json", "rgb.jpg", "final.ply"):
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b"changed")
            self.assertTrue(any(name in error for error in acceptance_snapshot_errors(self.root, snapshot)))
            path.write_bytes(original)
        self.assertEqual([], acceptance_snapshot_errors(self.root, snapshot))

    def test_malformed_scope_and_input_kind_return_validation_errors(self) -> None:
        self.requirement["scope"] = []
        self.measurement["inputs"][0]["kind"] = {}
        self.assertTrue(self.validate())
