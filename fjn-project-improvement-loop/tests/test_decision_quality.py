"""Decision regressions from the wall-transparency investigation, without GPU work."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from decision_quality import (  # noqa: E402
    validate_decision_design, validate_decision_progress, validate_stagnation,
)
from improvement_loop_policy import (  # noqa: E402
    DESIGN_REVIEW_CHECKS, design_review_checks, write_json,
)


def design_fixture():
    return {
        "decision_contract": {
            "schema_version": 1,
            "coverage": {
                "required_slices": ["front", "side"],
                "cases": [
                    {"slice": "front", "role": "control", "evidence": ["front.json::baseline facade"]},
                    {"slice": "side", "role": "failure", "evidence": ["side.json::opaque wall T=47.8355%"]},
                ],
                "scope_limits": "Current scene/source views only, no cross-scene generalization claimed",
            },
            "strongest_counterexample": {
                "observation": "Restoring means barely changes side-wall transmission",
                "evidence": ["side.json::47.8355% before and after"],
            },
            "selection": {
                "cheapest_alternative": "Inspect foreground alpha before fitting colors",
                "why_selected": "Alpha inspection is already complete; test opacity next",
                "parallel_basis": "Serial controlled probe before scale variants",
            },
        },
        "solutions": [{
            "id": "WALL", "kind": "optimize", "status": "selected",
            "acceptance_ids": ["ACC-T"],
            "next_if_supported": "Develop coverage-aware opacity",
            "next_if_refuted": "Stop opacity tuning and inspect point coverage",
            "mechanism_check": {
                "affected_acceptance_ids": ["ACC-T"], "invariant_acceptance_ids": [],
                "explanation": "Opacity affects pre-sky alpha",
                "evidence": ["renderer.py::foreground compositing equation"],
            },
        }],
    }


def evaluation_fixture(kind="none", verdict="failed"):
    return {"solution_results": [{
        "solution_id": "WALL", "verdict": verdict,
        "decision_progress": {
            "kind": kind,
            "before": "Compression may explain wall leakage; tune compression next",
            "after": "Unchanged wall alpha rejects that route; inspect coverage instead"
                     if kind != "none" else "No explanation distinguished; no route changed",
            "evidence": ["side.json::controlled pre-sky float alpha comparison"],
        },
    }]}


class DecisionQualityTests(unittest.TestCase):
    def test_baseline_and_side_failure_are_valid_coverage(self):
        self.assertEqual(validate_decision_design(design_fixture()), [])

    def test_front_only_improvement_does_not_cover_declared_side_walls(self):
        design = design_fixture()
        design["decision_contract"]["coverage"]["cases"].pop()
        errors = validate_decision_design(design)
        self.assertTrue(any("missing required slices" in x and "side" in x for x in errors))

    def test_missing_observations_allow_an_explicit_bootstrap_probe(self):
        design = design_fixture()
        contract = design["decision_contract"]
        contract["coverage"]["cases"] = []
        contract["coverage"]["evidence_gap"] = {
            "reason": "No saved pre-sky alpha; first record side/front controls",
            "probe_ids": ["WALL"],
        }
        contract["strongest_counterexample"] = {
            "observation": "No measured counterexample yet; the probe must inspect both groups",
            "evidence": [],
        }
        solution = design["solutions"][0]
        solution["kind"] = "probe"
        solution["mechanism_check"] = {
            "affected_acceptance_ids": [], "invariant_acceptance_ids": [],
            "explanation": "Collect the missing observations before deciding a repair", "evidence": [],
        }
        self.assertEqual(validate_decision_design(design), [])
        solution["kind"] = "optimize"
        self.assertTrue(validate_decision_design(design))

    def test_malformed_new_fields_return_errors_instead_of_crashing(self):
        design = design_fixture()
        design["decision_contract"]["coverage"]["cases"][0]["role"] = []
        design["solutions"][0]["acceptance_ids"] = [{}]
        self.assertTrue(validate_decision_design(design))
        evaluation = evaluation_fixture()
        evaluation["solution_results"][0]["decision_progress"]["kind"] = {}
        self.assertTrue(validate_decision_progress(evaluation, design_fixture()))

    def test_rgb_only_with_fixed_alpha_cannot_optimize_transmission(self):
        design = design_fixture()
        design["solutions"][0]["mechanism_check"].update({
            "affected_acceptance_ids": [], "invariant_acceptance_ids": ["ACC-T"],
            "explanation": "Only RGB changes, foreground alpha remains identical",
        })
        self.assertTrue(any("optimize must affect" in x for x in validate_decision_design(design)))
        design["solutions"][0]["kind"] = "probe"
        self.assertEqual(validate_decision_design(design), [])

    def test_same_target_cannot_be_affected_and_invariant(self):
        design = design_fixture()
        design["solutions"][0]["mechanism_check"]["invariant_acceptance_ids"] = ["ACC-T"]
        self.assertTrue(any("affected and invariant" in x for x in validate_decision_design(design)))

    def test_same_next_step_for_both_results_is_not_a_decision_test(self):
        design = design_fixture()
        design["solutions"][0]["next_if_refuted"] = design["solutions"][0]["next_if_supported"]
        self.assertTrue(any("must change the decision" in x for x in validate_decision_design(design)))

    def test_more_figures_without_changed_judgment_are_not_progress(self):
        evaluation = evaluation_fixture("hypothesis_resolved")
        progress = evaluation["solution_results"][0]["decision_progress"]
        progress["after"] = progress["before"]
        self.assertTrue(any("progress must change" in x for x in validate_decision_progress(evaluation, design_fixture())))

    def test_effective_negative_result_is_progress(self):
        evaluation = evaluation_fixture("hypothesis_resolved", "failed")
        self.assertEqual(validate_decision_progress(evaluation, design_fixture()), [])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(validate_stagnation(Path(tmp), 2, design_fixture(), evaluation, {}), [])

    def test_invalid_run_cannot_claim_scientific_progress(self):
        errors = validate_decision_progress(evaluation_fixture("hypothesis_resolved", "invalid_run"), design_fixture())
        self.assertTrue(any("invalid_run" in x for x in errors))

    def test_new_observability_is_useful_without_metric_gain(self):
        evaluation = evaluation_fixture("observability_unblocked", "partial")
        evaluation["solution_results"][0]["decision_progress"].update({
            "before": "Cannot trace the actual Gaussian source frame/pixel",
            "after": "Actual sampled origins are recorded and verified; depth causes can be tested",
        })
        self.assertEqual(validate_decision_progress(evaluation, design_fixture()), [])

    def test_legacy_design_keeps_original_review_contract(self):
        legacy = {"solutions": []}
        self.assertEqual(validate_decision_design(legacy), [])
        self.assertEqual(validate_decision_progress({}, legacy), [])
        self.assertEqual(design_review_checks(legacy), DESIGN_REVIEW_CHECKS)
        self.assertIn("experiment_worth_cost", design_review_checks(design_fixture()))

    def setup_previous(self, control, *, legacy=False, progress="none", reroot=False):
        previous = control / "rounds/round-001"
        write_json(previous / "design.json", {} if legacy else design_fixture())
        write_json(previous / "evaluation.json", evaluation_fixture(progress))
        write_json(previous / "evolution.json", {"actions": [{"action": "reroot" if reroot else "refine"}]})

    def test_two_uninformative_rounds_block_another_refinement(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = Path(tmp)
            self.setup_previous(control)
            errors = validate_stagnation(control, 2, design_fixture(), evaluation_fixture(), {"actions": [{"action": "refine"}]})
            self.assertTrue(any("two rounds" in x for x in errors))
            self.assertTrue(any("search_reassessment" in x for x in errors))

    def test_stagnation_allows_reassessment_and_reroot(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = Path(tmp)
            self.setup_previous(control)
            evolution = {
                "actions": [{"action": "reroot"}],
                "search_reassessment": {
                    "why_stalled": "Both variants lack actual birth/refresh history",
                    "changed_approach": "Instrument source provenance before more fitting",
                    "evidence": ["source.json::current archives cannot discriminate wrong-depth causes"],
                },
            }
            self.assertEqual(validate_stagnation(control, 2, design_fixture(), evaluation_fixture(), evolution), [])

    def test_progress_or_prior_reroot_resets_stagnation(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = Path(tmp)
            for options in ({"progress": "hypothesis_resolved"}, {"reroot": True}, {"legacy": True}):
                with self.subTest(options=options):
                    self.setup_previous(control, **options)
                    self.assertEqual(validate_stagnation(control, 2, design_fixture(), evaluation_fixture(), {}), [])

    def test_new_revision_does_not_inherit_old_target_stagnation(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = Path(tmp)
            self.setup_previous(control)
            self.assertEqual(validate_stagnation(
                control, 2, design_fixture(), evaluation_fixture(), {}, search_start_round=2,
            ), [])

    def test_malformed_contract_is_not_treated_as_legacy(self):
        self.assertTrue(validate_decision_design({"decision_contract": None}))


if __name__ == "__main__":
    unittest.main()
