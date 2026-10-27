from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SKILL_DIR.parent / "fjn-project-workflow/scripts"))

from improvement_loop_guard import validate_stage  # noqa: E402
from improvement_loop_next import advance, init_project, migrate_v1, stop  # noqa: E402
from improvement_loop_policy import (  # noqa: E402
    DESIGN_REVIEW_CHECKS,
    EVOLUTION_REVIEW_CHECKS,
    ValidationError,
    artifact_digest,
    load_json,
    validate_review,
    write_json,
)
from improvement_loop_tree import apply_tree, prepare_tree  # noqa: E402


class SixStageLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        init_project(self.project, dry_run=False)
        self.control = self.project / "docs/improvement-loop"
        (self.project / "baseline.json").write_text("{}\n", encoding="utf-8")
        (self.project / "result.json").write_text("{}\n", encoding="utf-8")
        self.workflow_guard = patch(
            "improvement_loop_guard.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        )
        self.workflow_guard.start()

    def tearDown(self) -> None:
        self.workflow_guard.stop()
        self.temp.cleanup()

    def state(self) -> dict:
        return load_json(self.control / "loop_state.json")

    def write_state(self, state: dict) -> None:
        write_json(self.control / "loop_state.json", state)

    def pass_guard(self) -> None:
        state = self.state()
        errors, _ = validate_stage(self.project, state["stage"])
        self.assertEqual(errors, [])
        state["last_guard"] = {
            "stage": state["stage"],
            "round": state["round"],
            "passed": True,
        }
        self.write_state(state)

    def prepare_goal(self) -> None:
        goal = load_json(self.control / "goal.json")
        goal["goal"] = "达到验收目标"
        goal["current_state"]["summary"] = "基线尚未达到目标"
        goal["current_state"]["evidence"] = ["baseline.json::记录当前基线"]
        goal["acceptance_criteria"][0]["criterion"] = "score >= 1"
        goal["acceptance_criteria"][0]["evaluation"] = "运行固定评估"
        write_json(self.control / "goal.json", goal)

    def prepare_design(self) -> None:
        design_path = self.control / "rounds/round-001/design.json"
        design = load_json(design_path)
        design["problem_analysis"] = {
            "observations": [
                {
                    "statement": "失败集中于缺少目标信息的区域",
                    "evidence": ["baseline.json::记录失败案例分布"],
                }
            ],
            "root_cause": {
                "claim": "当前表示缺少目标信息",
                "mechanism": "输入缺失导致目标状态不可辨识",
                "supporting_evidence": ["baseline.json::证明缺失区域系统性失败"],
                "falsification_condition": "补充信息后受控结果仍不改善",
            },
            "alternative_explanations": [
                {
                    "id": "ALT-001",
                    "claim": "模型容量不足",
                    "distinct_prediction": "等量增加容量也会改善",
                    "discriminating_observation": "控制训练量比较信息与容量改动",
                }
            ],
            "decisive_unknown": {
                "question": "收益来自信息还是容量",
                "why_decisive": "决定继续信息融合还是扩大模型",
                "cheapest_probe": "等参数小规模受控对照",
            },
        }
        solution = design["solutions"][0]
        solution.update(
            {
                "status": "selected",
                "claim": "补充信息会改善目标",
                "rationale": "失败案例集中于信息缺失区域",
                "change_or_test": "增加目标信息输入",
                "confounds_and_controls": "固定容量、训练量、数据和评估协议",
                "expected_observation": "固定评估分数提高",
                "falsification_condition": "分数未超过基线波动",
                "next_if_supported": "精进该信息融合方式",
                "next_if_refuted": "剪枝并检查其他根因",
                "tree_relation": {
                    "type": "new_root",
                    "parent_id": None,
                    "rationale": "当前没有证据支持它承接已有分支",
                    "evidence": [],
                },
            }
        )
        design["selection_reason"] = "直接命中当前根问题"
        write_json(design_path, design)
        goal = load_json(self.control / "goal.json")
        self.prepare_review(
            "design_review.json",
            "design",
            artifact_digest(goal, design),
            DESIGN_REVIEW_CHECKS,
        )

    def prepare_review(
        self,
        filename: str,
        target_kind: str,
        target_digest: str,
        checks: set[str],
        *,
        critic_decision: str = "approve",
    ) -> None:
        path = self.control / f"rounds/round-{self.state()['round']:03d}/{filename}"
        review = load_json(path)
        failed_check = sorted(checks)[0]
        check_results = {key: True for key in checks}
        if critic_decision == "reject":
            check_results[failed_check] = False
        review["cycles"] = [
            {
                "cycle": 1,
                "target_digest": target_digest,
                "proposer": {
                    "role": "proposer",
                    "decision": "approve",
                    "summary": "主角色确认当前草案可进入下一步",
                    "responses": [],
                },
                "critic": {
                    "role": "critic",
                    "agent": "FJN Project Improvement Critic",
                    "independent_context": True,
                    "decision": critic_decision,
                    "summary": "未发现实质缺陷" if critic_decision == "approve" else "存在实质缺陷",
                    "checks": check_results,
                    "objections": []
                    if critic_decision == "approve"
                    else [
                        {
                            "id": "OBJ-001",
                            "check": failed_check,
                            "statement": "根因缺少充分证据",
                            "required_change": "补充区分竞争解释的证据",
                        }
                    ],
                },
            }
        ]
        write_json(path, review)

    def prepare_workflow_execution(self) -> None:
        workflow = self.project / "docs/project-control"
        workflow.mkdir(parents=True)
        write_json(
            workflow / "state.json",
            {
                "candidates": {"P-v1-a": {"run_ids": ["run-1"]}},
                "runs": {
                    "run-1": {
                        "candidate_id": "P-v1-a",
                        "status": "completed",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "evidence": ["result.json::证明运行完成"],
                    }
                },
            },
        )
        execution_path = self.control / "rounds/round-001/execution.json"
        execution = load_json(execution_path)
        execution["project_workflow"] = {
            "project_root": str(self.project),
            "guard_status": "pass",
            "evidence": ["docs/project-control/state.json::证明控制面 guard 通过"],
        }
        execution["bindings"] = [
            {
                "solution_id": "SOL-001",
                "candidate_id": "P-v1-a",
                "run_id": "run-1",
                "status": "completed",
                "evidence": ["result.json::记录该方案运行结果"],
            }
        ]
        write_json(execution_path, execution)

    def prepare_artifact_review(self) -> None:
        from artifact_review import CHECKS

        state_path = self.project / "docs/project-control/state.json"
        state = load_json(state_path)
        assessed = datetime.now(timezone.utc)
        review = {
            "schema_version": 1, "run_id": "run-1", "decision": "keep",
            "reason": "保留本轮结果用于后续研究",
            "assessed_at": assessed.isoformat(),
            "review_after": (assessed + timedelta(days=7)).isoformat(),
            "checks": {key: {"value": "unknown", "evidence": ["result.json::保留待核实"]} for key in CHECKS},
            "preserve": ["result.json"], "files": [],
        }
        write_json(self.project / "review-run-1.json", review)
        state["runs"]["run-1"]["artifact_review"] = {"reference": "review-run-1.json", "review": review}
        write_json(state_path, state)
        write_json(self.control / "rounds/round-001/artifact_review.json", {
            "schema_version": 1, "round_id": "round-001", "run_ids": ["run-1"],
        })

    def prepare_evaluation(self, goal_met: bool) -> None:
        path = self.control / "rounds/round-001/evaluation.json"
        evaluation = load_json(path)
        evaluation["solution_results"] = [
            {
                "solution_id": "SOL-001",
                "verdict": "successful" if goal_met else "partial",
                "effect_on_goal": "达到目标" if goal_met else "有改善但未达标",
                "claim_update": "观点得到支持",
                "next_implication": "结束" if goal_met else "继续精进",
                "evidence": ["result.json::证明方案效果"],
            }
        ]
        evaluation["acceptance_results"][0].update(
            {
                "passed": goal_met,
                "observation": "score=1" if goal_met else "score=0.8",
                "evidence": ["result.json::记录固定协议验收结果"],
            }
        )
        evaluation["goal_met"] = goal_met
        evaluation["incumbent_update"].update(
            {
                "action": "replace" if goal_met else "unchanged",
                "solution_id": "SOL-001" if goal_met else None,
                "reason": "根据固定验收协议判断",
            }
        )
        write_json(path, evaluation)

    def prepare_evolution(self, action: str, *, goal_met: bool = False) -> None:
        current = self.control / f"rounds/round-{self.state()['round']:03d}"
        evolution = load_json(current / "evolution.json")
        item = {
            "source_solution_id": "SOL-001",
            "action": action,
            "reason": "根据固定验收协议和方案证据更新分支",
            "evidence": ["result.json::证明该树动作与实验结果一致"],
        }
        if action in {"refine", "split"}:
            item["next_branch"] = "在下一轮隔离验证有效机制"
        if action == "prune":
            item["reopen_when"] = "出现能推翻本次失败归因的新证据"
        evolution.update(
            {
                "round_learning": "本轮证据已改变方案判断",
                "actions": [item],
                "next_stage": "completed" if goal_met else (
                    "assess_target" if action == "reroot" else "design_solutions"
                ),
                "next_focus": "结束" if goal_met else "依据本轮证据继续",
            }
        )
        write_json(current / "evolution.json", evolution)
        prepare_tree(self.project)
        evaluation = load_json(current / "evaluation.json")
        proposed = load_json(current / "proposed_tree.json")
        goal = load_json(self.control / "goal.json")
        design = load_json(current / "design.json")
        execution = load_json(current / "execution.json")
        self.prepare_review(
            "evolution_review.json",
            "evolution",
            artifact_digest(goal, design, execution, evaluation, evolution, proposed),
            EVOLUTION_REVIEW_CHECKS,
        )
        apply_tree(self.project)

    def advance_to_evaluation(self) -> None:
        self.prepare_goal()
        self.pass_guard()
        advance(self.project)
        self.prepare_design()
        self.pass_guard()
        advance(self.project)
        self.prepare_workflow_execution()
        self.pass_guard()
        advance(self.project)

    def test_init_starts_at_assess_target(self) -> None:
        self.assertEqual(self.state()["stage"], "assess_target")
        self.assertTrue((self.control / "rounds/round-001/design.json").is_file())

    def test_project_workflow_guard_path_exists(self) -> None:
        from improvement_loop_guard import PROJECT_WORKFLOW_GUARD

        self.assertTrue(PROJECT_WORKFLOW_GUARD.is_file())

    def test_migrate_v1_archives_legacy_control_plane(self) -> None:
        other = self.project / "legacy-project"
        legacy = other / "docs/improvement-loop"
        legacy.mkdir(parents=True)
        write_json(legacy / "run_state.json", {"schema_version": 1})
        result = migrate_v1(other, dry_run=False)
        self.assertTrue(Path(result["archive"]).is_dir())
        self.assertEqual(load_json(legacy / "loop_state.json")["stage"], "assess_target")
        self.assertTrue(load_json(legacy / "loop_state.json")["migration"]["requires_reassessment"])

    def test_advance_requires_current_guard(self) -> None:
        with self.assertRaisesRegex(ValueError, "must pass guard"):
            advance(self.project)

    def test_first_three_stages_advance_in_order(self) -> None:
        self.advance_to_evaluation()
        self.assertEqual(self.state()["stage"], "evaluate_results")

    def test_design_requires_independent_critic_approval(self) -> None:
        self.prepare_goal()
        self.pass_guard()
        advance(self.project)
        self.prepare_design()
        design = load_json(self.control / "rounds/round-001/design.json")
        goal = load_json(self.control / "goal.json")
        self.prepare_review(
            "design_review.json",
            "design",
            artifact_digest(goal, design),
            DESIGN_REVIEW_CHECKS,
            critic_decision="reject",
        )
        errors, _ = validate_stage(self.project, "design_solutions")
        self.assertTrue(any("final critic decision must be approve" in error for error in errors))

    def test_design_change_invalidates_both_approvals(self) -> None:
        self.prepare_goal()
        self.pass_guard()
        advance(self.project)
        self.prepare_design()
        path = self.control / "rounds/round-001/design.json"
        design = load_json(path)
        design["solutions"][0]["change_or_test"] = "批准后偷改方案"
        write_json(path, design)
        errors, _ = validate_stage(self.project, "design_solutions")
        self.assertTrue(any("digest does not match" in error for error in errors))

    def test_goal_change_invalidates_design_approval(self) -> None:
        self.prepare_goal()
        self.pass_guard()
        advance(self.project)
        self.prepare_design()
        goal_path = self.control / "goal.json"
        goal = load_json(goal_path)
        goal["acceptance_criteria"][0]["criterion"] = "score >= 2"
        write_json(goal_path, goal)
        errors, _ = validate_stage(self.project, "design_solutions")
        self.assertTrue(any("digest does not match" in error for error in errors))

    def test_advance_revalidates_after_guard(self) -> None:
        self.prepare_goal()
        self.pass_guard()
        goal_path = self.control / "goal.json"
        goal = load_json(goal_path)
        goal["goal"] = "guard 后修改目标"
        goal["current_state"]["summary"] = ""
        write_json(goal_path, goal)
        with self.assertRaisesRegex(ValueError, "changed after guard"):
            advance(self.project)

    def test_review_cannot_be_replayed_from_another_round(self) -> None:
        self.prepare_goal()
        self.pass_guard()
        advance(self.project)
        self.prepare_design()
        review_path = self.control / "rounds/round-001/design_review.json"
        review = load_json(review_path)
        review["round_id"] = "round-999"
        write_json(review_path, review)
        errors, _ = validate_stage(self.project, "design_solutions")
        self.assertTrue(any("review.round_id must be round-001" in error for error in errors))

    def test_new_review_cycle_must_answer_prior_objections(self) -> None:
        digest = "sha256:current"
        approved_critic = {
            "role": "critic",
            "agent": "FJN Project Improvement Critic",
            "independent_context": True,
            "decision": "approve",
            "summary": "修改后通过",
            "checks": {key: True for key in DESIGN_REVIEW_CHECKS},
            "objections": [],
        }
        failed_check = "alternatives_considered"
        rejected_checks = {key: True for key in DESIGN_REVIEW_CHECKS}
        rejected_checks[failed_check] = False
        review = {
            "schema_version": 1,
            "round_id": "round-001",
            "target_kind": "design",
            "cycles": [
                {
                    "cycle": 1,
                    "target_digest": "sha256:old",
                    "proposer": {
                        "role": "proposer",
                        "decision": "approve",
                        "summary": "提交初稿",
                        "responses": [],
                    },
                    "critic": {
                        **approved_critic,
                        "decision": "reject",
                        "summary": "根因证据不足",
                        "checks": rejected_checks,
                        "objections": [
                            {
                                "id": "OBJ-001",
                                "check": failed_check,
                                "statement": "缺少竞争解释",
                                "required_change": "增加区分观测",
                            }
                        ],
                    },
                },
                {
                    "cycle": 2,
                    "target_digest": digest,
                    "proposer": {
                        "role": "proposer",
                        "decision": "approve",
                        "summary": "声称已修改",
                        "responses": [],
                    },
                    "critic": approved_critic,
                },
            ],
        }
        errors = validate_review(
            review,
            target_kind="design",
            expected_digest=digest,
            required_checks=DESIGN_REVIEW_CHECKS,
        )
        self.assertTrue(any("misses prior objections" in error for error in errors))

    def test_rejected_review_requires_boolean_checks_and_matching_objections(self) -> None:
        checks = {key: True for key in DESIGN_REVIEW_CHECKS}
        checks["evidence_grounded"] = "false"
        review = {
            "schema_version": 1,
            "round_id": "round-001",
            "target_kind": "design",
            "cycles": [
                {
                    "cycle": 1,
                    "target_digest": "sha256:current",
                    "proposer": {
                        "role": "proposer",
                        "decision": "approve",
                        "summary": "提交评审",
                        "responses": [],
                    },
                    "critic": {
                        "role": "critic",
                        "agent": "FJN Project Improvement Critic",
                        "independent_context": True,
                        "decision": "reject",
                        "summary": "检查值和 objection 不一致",
                        "checks": checks,
                        "objections": [
                            {
                                "id": "OBJ-001",
                                "check": "falsifiable",
                                "statement": "不可证伪",
                                "required_change": "补充推翻条件",
                            }
                        ],
                    },
                }
            ],
        }
        errors = validate_review(
            review,
            target_kind="design",
            expected_digest="sha256:current",
            required_checks=DESIGN_REVIEW_CHECKS,
            expected_round_id="round-001",
        )
        self.assertTrue(any("checks must be boolean" in error for error in errors))
        self.assertTrue(any("must reference a false check" in error for error in errors))

    def test_refine_relation_requires_existing_parent_and_evidence(self) -> None:
        self.prepare_goal()
        self.pass_guard()
        advance(self.project)
        self.prepare_design()
        path = self.control / "rounds/round-001/design.json"
        design = load_json(path)
        design["solutions"][0]["tree_relation"] = {
            "type": "refine",
            "parent_id": "SOL-MISSING",
            "rationale": "声称承接历史分支",
            "evidence": [],
        }
        write_json(path, design)
        errors, _ = validate_stage(self.project, "design_solutions")
        self.assertTrue(any("requires evidence" in error for error in errors))
        self.assertTrue(any("unknown parent" in error for error in errors))

    def test_execution_rejects_nonexistent_workflow_run(self) -> None:
        self.prepare_goal()
        self.pass_guard()
        advance(self.project)
        self.prepare_design()
        self.pass_guard()
        advance(self.project)
        self.prepare_workflow_execution()
        execution_path = self.control / "rounds/round-001/execution.json"
        execution = load_json(execution_path)
        execution["bindings"][0]["run_id"] = "missing-run"
        write_json(execution_path, execution)
        errors, _ = validate_stage(self.project, "execute_via_workflow")
        self.assertTrue(any("does not exist" in error for error in errors))

    def test_goal_met_completes_loop(self) -> None:
        self.advance_to_evaluation()
        self.prepare_evaluation(goal_met=True)
        self.pass_guard()
        result = advance(self.project)
        self.assertEqual(result["to"], "evolve_tree")
        self.prepare_evolution("keep", goal_met=True)
        self.pass_guard()
        result = advance(self.project)
        self.assertEqual(result["to"], "review_artifacts")
        errors, _ = validate_stage(self.project, "review_artifacts")
        self.assertTrue(any("register a keep" in error for error in errors))
        self.prepare_artifact_review()
        self.pass_guard()
        result = advance(self.project)
        self.assertEqual(result["to"], "completed")
        self.assertEqual(self.state()["stop_decision"]["status"], "fulfilled")

    def test_unmet_goal_routes_to_tree_evolution(self) -> None:
        self.advance_to_evaluation()
        self.prepare_evaluation(goal_met=False)
        self.pass_guard()
        advance(self.project)
        self.assertEqual(self.state()["stage"], "evolve_tree")

    def test_tree_apply_requires_dual_approval(self) -> None:
        self.advance_to_evaluation()
        self.prepare_evaluation(goal_met=False)
        self.pass_guard()
        advance(self.project)
        current = self.control / "rounds/round-001"
        evolution = load_json(current / "evolution.json")
        evolution.update(
            {
                "round_learning": "方向部分有效",
                "actions": [
                    {
                        "source_solution_id": "SOL-001",
                        "action": "refine",
                        "reason": "已有改善但未达标",
                        "evidence": ["result.json::证明部分改善"],
                        "next_branch": "增强有效机制",
                    }
                ],
                "next_focus": "增强有效机制",
            }
        )
        write_json(current / "evolution.json", evolution)
        prepare_tree(self.project)
        with self.assertRaises(ValidationError):
            apply_tree(self.project)

    def test_tree_apply_rejects_tampered_approved_tree(self) -> None:
        self.advance_to_evaluation()
        self.prepare_evaluation(goal_met=False)
        self.pass_guard()
        advance(self.project)
        current = self.control / "rounds/round-001"
        evolution = load_json(current / "evolution.json")
        evolution.update(
            {
                "round_learning": "方向部分有效",
                "actions": [
                    {
                        "source_solution_id": "SOL-001",
                        "action": "refine",
                        "reason": "已有改善但未达标",
                        "evidence": ["result.json::证明部分改善"],
                        "next_branch": "增强有效机制",
                    }
                ],
                "next_focus": "增强有效机制",
            }
        )
        write_json(current / "evolution.json", evolution)
        prepare_tree(self.project)
        proposed = load_json(current / "proposed_tree.json")
        proposed["root_problem"] = "未经动作推导的篡改根问题"
        write_json(current / "proposed_tree.json", proposed)
        evaluation = load_json(current / "evaluation.json")
        goal = load_json(self.control / "goal.json")
        design = load_json(current / "design.json")
        execution = load_json(current / "execution.json")
        self.prepare_review(
            "evolution_review.json",
            "evolution",
            artifact_digest(goal, design, execution, evaluation, evolution, proposed),
            EVOLUTION_REVIEW_CHECKS,
        )
        with self.assertRaisesRegex(ValidationError, "deterministic reconstruction"):
            apply_tree(self.project)

    def test_tree_rejects_parent_cycle_and_invalid_edge_evidence(self) -> None:
        from improvement_loop_guard import validate_tree

        tree = {
            "schema_version": 2,
            "updated_at": "now",
            "root_problem": "root",
            "root_history": [],
            "incumbent": {},
            "failed_memory": [],
            "nodes": [
                {
                    "id": "SOL-A",
                    "parent_id": "SOL-B",
                    "round_id": "round-001",
                    "kind": "probe",
                    "status": "partial",
                    "claim": "A",
                    "last_action": "split",
                    "relation_type": "split",
                    "relation_rationale": "A from B",
                    "relation_evidence": ["not-a-valid-evidence-ref"],
                },
                {
                    "id": "SOL-B",
                    "parent_id": "SOL-A",
                    "round_id": "round-001",
                    "kind": "probe",
                    "status": "partial",
                    "claim": "B",
                    "last_action": "split",
                    "relation_type": "split",
                    "relation_rationale": "B from A",
                    "relation_evidence": ["result.json::支持该关系"],
                },
            ],
        }
        errors = validate_tree(tree)
        self.assertTrue(any("must use 'reference::what-it-proves'" in error for error in errors))
        self.assertTrue(any("parent cycle" in error for error in errors))

    def test_refine_starts_new_design_round(self) -> None:
        self.advance_to_evaluation()
        self.prepare_evaluation(goal_met=False)
        self.pass_guard()
        advance(self.project)
        self.prepare_evolution("refine")
        self.pass_guard()
        advance(self.project)
        self.assertEqual(self.state()["stage"], "review_artifacts")
        self.prepare_artifact_review()
        self.pass_guard()
        advance(self.project)
        state = self.state()
        self.assertEqual((state["stage"], state["round"]), ("design_solutions", 2))

    def test_reroot_returns_to_assessment(self) -> None:
        self.advance_to_evaluation()
        self.prepare_evaluation(goal_met=False)
        self.pass_guard()
        advance(self.project)
        self.prepare_evolution("reroot")
        self.pass_guard()
        advance(self.project)
        self.prepare_artifact_review()
        self.pass_guard()
        advance(self.project)
        state = self.state()
        self.assertEqual((state["stage"], state["round"]), ("assess_target", 2))

    def test_failed_retry_must_also_be_reviewed(self) -> None:
        from improvement_loop_guard import validate_artifact_marks

        self.advance_to_evaluation()
        self.prepare_artifact_review()
        path = self.project / "docs/project-control/state.json"
        state = load_json(path)
        state["candidates"]["P-v1-a"]["run_ids"].append("run-failed")
        state["runs"]["run-failed"] = {"candidate_id": "P-v1-a", "status": "failed"}
        write_json(path, state)
        errors = validate_artifact_marks(self.project, 1)
        self.assertTrue(any("including retries" in error for error in errors))
        self.assertTrue(any("run-failed: register" in error for error in errors))

    def test_stop_requires_marks_but_not_a_new_scientific_review(self) -> None:
        self.advance_to_evaluation()
        with self.assertRaisesRegex(ValidationError, "review completed run artifacts"):
            stop(self.project, "budget_exhausted", "预算耗尽")
        self.prepare_artifact_review()
        stop(self.project, "budget_exhausted", "预算耗尽")
        self.assertEqual(self.state()["status"], "stopped")

    def test_running_work_does_not_require_fabricated_terminal_review(self) -> None:
        self.advance_to_evaluation()
        path = self.project / "docs/project-control/state.json"
        state = load_json(path)
        state["runs"]["run-1"]["status"] = "running"
        write_json(path, state)
        (self.control / "rounds/round-001/artifact_review.json").unlink()
        stop(self.project, "blocked", "任务仍在执行，未评估终态产物")
        self.assertEqual(self.state()["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
