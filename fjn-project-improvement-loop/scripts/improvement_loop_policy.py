#!/usr/bin/env python3
"""Shared contracts for the six-stage project improvement loop."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

STAGES = [
    "assess_target",
    "design_solutions",
    "execute_via_workflow",
    "evaluate_results",
    "evolve_tree",
    "review_artifacts",
]
SOLUTION_KINDS = {"optimize", "probe"}
SOLUTION_STATUSES = {
    "proposed",
    "selected",
    "running",
    "successful",
    "failed",
    "partial",
    "inconclusive",
    "invalid_run",
    "pruned",
}
RESULT_VERDICTS = {"successful", "failed", "partial", "inconclusive", "invalid_run"}
TREE_ACTIONS = {"prune", "refine", "split", "keep", "reroot"}
TREE_RELATIONS = {"new_root", "refine", "split"}
DESIGN_REVIEW_CHECKS = {
    "evidence_grounded",
    "alternatives_considered",
    "root_cause_plausible",
    "solution_targets_root",
    "falsifiable",
    "confounds_controlled",
    "goal_aligned",
    "tree_relation_justified",
}
EVOLUTION_REVIEW_CHECKS = {
    "verdicts_evidence_grounded",
    "actions_match_results",
    "failed_memory_complete",
    "tree_relations_justified",
    "incumbent_consistent",
    "reroot_decision_justified",
}
STOP_STATUSES = {
    "fulfilled",
    "budget_exhausted",
    "no_high_value_branch",
    "blocked",
    "needs_user_decision",
}


class ValidationError(ValueError):
    """Raised when an artifact violates the six-stage contract."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError(f"JSON root must be an object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def artifact_digest(*artifacts: dict[str, Any]) -> str:
    payload: Any = artifacts[0] if len(artifacts) == 1 else list(artifacts)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None


def require(payload: dict[str, Any], field: str, errors: list[str], prefix: str = "") -> Any:
    value = payload.get(field)
    if not nonempty(value):
        errors.append(f"{prefix}{field} must be non-empty")
    return value


def require_list(
    payload: dict[str, Any], field: str, errors: list[str], prefix: str = ""
) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list):
        errors.append(f"{prefix}{field} must be a list")
        return []
    return value


def validate_evidence(items: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append(f"{prefix} must be a list")
        return
    for index, item in enumerate(items):
        if not isinstance(item, str) or "::" not in item:
            errors.append(f"{prefix}[{index}] must use 'reference::what-it-proves'")
            continue
        reference, claim = item.split("::", 1)
        if not reference.strip() or not claim.strip():
            errors.append(f"{prefix}[{index}] needs both reference and claim")


def validate_goal(goal: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if goal.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    require(goal, "goal", errors)
    current = goal.get("current_state")
    if not isinstance(current, dict):
        errors.append("current_state must be an object")
    else:
        require(current, "summary", errors, "current_state.")
        validate_evidence(current.get("evidence"), "current_state.evidence", errors)
    criteria = require_list(goal, "acceptance_criteria", errors)
    if not criteria:
        errors.append("acceptance_criteria must contain at least one criterion")
    for index, criterion in enumerate(criteria):
        prefix = f"acceptance_criteria[{index}]"
        if not isinstance(criterion, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require(criterion, "id", errors, f"{prefix}.")
        require(criterion, "criterion", errors, f"{prefix}.")
        require(criterion, "evaluation", errors, f"{prefix}.")
        if not isinstance(criterion.get("hard"), bool):
            errors.append(f"{prefix}.hard must be a boolean")
    require_list(goal, "constraints", errors)
    budget = goal.get("budget")
    if not isinstance(budget, dict):
        errors.append("budget must be an object")
    elif not any(
        isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        for value in budget.values()
        if value is not None
    ):
        errors.append("budget must contain at least one positive finite limit")
    return errors


def validate_solution(
    solution: dict[str, Any], prefix: str, errors: list[str], tree: dict[str, Any] | None
) -> None:
    for field in [
        "id",
        "claim",
        "rationale",
        "change_or_test",
        "confounds_and_controls",
        "expected_observation",
        "falsification_condition",
        "next_if_supported",
        "next_if_refuted",
    ]:
        require(solution, field, errors, f"{prefix}.")
    if solution.get("kind") not in SOLUTION_KINDS:
        errors.append(f"{prefix}.kind must be optimize or probe")
    if solution.get("status") not in SOLUTION_STATUSES:
        errors.append(f"{prefix}.status is invalid")
    if not require_list(solution, "acceptance_ids", errors, f"{prefix}."):
        errors.append(f"{prefix}.acceptance_ids must not be empty")
    relation = solution.get("tree_relation")
    if not isinstance(relation, dict):
        errors.append(f"{prefix}.tree_relation must be an object")
        return
    relation_type = relation.get("type")
    if relation_type not in TREE_RELATIONS:
        errors.append(f"{prefix}.tree_relation.type is invalid")
    require(relation, "rationale", errors, f"{prefix}.tree_relation.")
    evidence = require_list(relation, "evidence", errors, f"{prefix}.tree_relation.")
    validate_evidence(evidence, f"{prefix}.tree_relation.evidence", errors)
    parent_id = relation.get("parent_id")
    if relation_type == "new_root":
        if parent_id is not None:
            errors.append(f"{prefix}.tree_relation new_root must have parent_id=null")
    else:
        if not nonempty(parent_id):
            errors.append(f"{prefix}.tree_relation {relation_type} requires parent_id")
        if not evidence:
            errors.append(f"{prefix}.tree_relation {relation_type} requires evidence")
        if tree is not None:
            tree_ids = {
                str(item.get("id"))
                for item in tree.get("nodes", [])
                if isinstance(item, dict)
            }
            if str(parent_id) not in tree_ids:
                errors.append(f"{prefix}.tree_relation references unknown parent {parent_id}")


def validate_design(
    design: dict[str, Any],
    goal: dict[str, Any] | None = None,
    tree: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    require(design, "round_id", errors)
    require(design, "base_tree_digest", errors)
    analysis = design.get("problem_analysis")
    if not isinstance(analysis, dict):
        errors.append("problem_analysis must be an object")
    else:
        observations = require_list(analysis, "observations", errors, "problem_analysis.")
        if not observations:
            errors.append("problem_analysis.observations must not be empty")
        for index, observation in enumerate(observations):
            prefix = f"problem_analysis.observations[{index}]"
            if not isinstance(observation, dict):
                errors.append(f"{prefix} must be an object")
                continue
            require(observation, "statement", errors, f"{prefix}.")
            evidence = require_list(observation, "evidence", errors, f"{prefix}.")
            if not evidence:
                errors.append(f"{prefix}.evidence must not be empty")
            validate_evidence(evidence, f"{prefix}.evidence", errors)
        root_cause = analysis.get("root_cause")
        if not isinstance(root_cause, dict):
            errors.append("problem_analysis.root_cause must be an object")
        else:
            for field in ["claim", "mechanism", "falsification_condition"]:
                require(root_cause, field, errors, "problem_analysis.root_cause.")
            evidence = require_list(
                root_cause, "supporting_evidence", errors, "problem_analysis.root_cause."
            )
            if not evidence:
                errors.append("problem_analysis.root_cause.supporting_evidence must not be empty")
            validate_evidence(evidence, "problem_analysis.root_cause.supporting_evidence", errors)
        alternatives = require_list(
            analysis, "alternative_explanations", errors, "problem_analysis."
        )
        if not alternatives:
            errors.append("problem_analysis.alternative_explanations must not be empty")
        for index, alternative in enumerate(alternatives):
            prefix = f"problem_analysis.alternative_explanations[{index}]"
            if not isinstance(alternative, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for field in ["id", "claim", "distinct_prediction", "discriminating_observation"]:
                require(alternative, field, errors, f"{prefix}.")
        unknown = analysis.get("decisive_unknown")
        if not isinstance(unknown, dict):
            errors.append("problem_analysis.decisive_unknown must be an object")
        else:
            for field in ["question", "why_decisive", "cheapest_probe"]:
                require(unknown, field, errors, "problem_analysis.decisive_unknown.")
    require(design, "selection_reason", errors)
    solutions = require_list(design, "solutions", errors)
    if not solutions:
        errors.append("solutions must contain at least one candidate")
    selected = 0
    identifiers: set[str] = set()
    for index, solution in enumerate(solutions):
        if not isinstance(solution, dict):
            errors.append(f"solutions[{index}] must be an object")
            continue
        validate_solution(solution, f"solutions[{index}]", errors, tree)
        identifier = str(solution.get("id"))
        if identifier in identifiers:
            errors.append(f"duplicate solution id: {identifier}")
        identifiers.add(identifier)
        if solution.get("status") == "selected":
            selected += 1
    if selected == 0:
        errors.append("at least one solution must be selected")
    if goal is not None:
        acceptance_ids = {
            str(item.get("id"))
            for item in goal.get("acceptance_criteria", [])
            if isinstance(item, dict)
        }
        for index, solution in enumerate(solutions):
            if not isinstance(solution, dict):
                continue
            unknown = sorted(set(map(str, solution.get("acceptance_ids", []))) - acceptance_ids)
            if unknown:
                errors.append(f"solutions[{index}].acceptance_ids contains unknown IDs: {unknown}")
    return errors


def validate_review(
    review: dict[str, Any],
    *,
    target_kind: str,
    expected_digest: str,
    required_checks: set[str],
    expected_round_id: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if review.get("schema_version") != 1:
        errors.append("review.schema_version must be 1")
    review_round_id = require(review, "round_id", errors, "review.")
    if expected_round_id is not None and review_round_id != expected_round_id:
        errors.append(f"review.round_id must be {expected_round_id}")
    if review.get("target_kind") != target_kind:
        errors.append(f"review.target_kind must be {target_kind}")
    cycles = require_list(review, "cycles", errors, "review.")
    if not cycles:
        errors.append("review.cycles must not be empty")
        return errors
    previous_objections: set[str] = set()
    cycle_numbers: set[int] = set()
    for index, cycle in enumerate(cycles):
        prefix = f"review.cycles[{index}]"
        if not isinstance(cycle, dict):
            errors.append(f"{prefix} must be an object")
            continue
        number = cycle.get("cycle")
        if not isinstance(number, int) or number < 1 or number in cycle_numbers:
            errors.append(f"{prefix}.cycle must be a unique positive integer")
        cycle_numbers.add(number)
        require(cycle, "target_digest", errors, f"{prefix}.")
        proposer = cycle.get("proposer")
        critic = cycle.get("critic")
        if not isinstance(proposer, dict):
            errors.append(f"{prefix}.proposer must be an object")
            proposer = {}
        if not isinstance(critic, dict):
            errors.append(f"{prefix}.critic must be an object")
            critic = {}
        if proposer.get("role") != "proposer":
            errors.append(f"{prefix}.proposer.role must be proposer")
        if proposer.get("decision") not in {"approve", "revise"}:
            errors.append(f"{prefix}.proposer.decision must be approve or revise")
        require(proposer, "summary", errors, f"{prefix}.proposer.")
        responses = require_list(proposer, "responses", errors, f"{prefix}.proposer.")
        response_ids = {
            str(item.get("objection_id"))
            for item in responses
            if isinstance(item, dict) and nonempty(item.get("resolution"))
        }
        missing_responses = sorted(previous_objections - response_ids)
        if missing_responses:
            errors.append(f"{prefix}.proposer.responses misses prior objections: {missing_responses}")
        if critic.get("role") != "critic":
            errors.append(f"{prefix}.critic.role must be critic")
        if critic.get("agent") != "FJN Project Improvement Critic":
            errors.append(f"{prefix}.critic.agent must identify the independent critic")
        if critic.get("independent_context") is not True:
            errors.append(f"{prefix}.critic.independent_context must be true")
        if critic.get("decision") not in {"approve", "reject"}:
            errors.append(f"{prefix}.critic.decision must be approve or reject")
        require(critic, "summary", errors, f"{prefix}.critic.")
        checks = critic.get("checks")
        if not isinstance(checks, dict):
            errors.append(f"{prefix}.critic.checks must be an object")
            checks = {}
        missing_checks = sorted(required_checks - set(checks))
        if missing_checks:
            errors.append(f"{prefix}.critic.checks misses: {missing_checks}")
        unexpected_checks = sorted(set(checks) - required_checks)
        if unexpected_checks:
            errors.append(f"{prefix}.critic.checks has unexpected keys: {unexpected_checks}")
        non_boolean_checks = sorted(
            key for key in required_checks if key in checks and not isinstance(checks[key], bool)
        )
        if non_boolean_checks:
            errors.append(f"{prefix}.critic.checks must be boolean: {non_boolean_checks}")
        objections = require_list(critic, "objections", errors, f"{prefix}.critic.")
        objection_ids: set[str] = set()
        objection_checks: set[str] = set()
        for objection_index, objection in enumerate(objections):
            objection_prefix = f"{prefix}.critic.objections[{objection_index}]"
            if not isinstance(objection, dict):
                errors.append(f"{objection_prefix} must be an object")
                continue
            for field in ["id", "check", "statement", "required_change"]:
                require(objection, field, errors, f"{objection_prefix}.")
            objection_id = str(objection.get("id"))
            if objection_id in objection_ids:
                errors.append(f"{objection_prefix}.id must be unique within the cycle")
            objection_ids.add(objection_id)
            check = str(objection.get("check"))
            objection_checks.add(check)
            if check not in required_checks:
                errors.append(f"{objection_prefix}.check is not a required check: {check}")
            elif checks.get(check) is not False:
                errors.append(f"{objection_prefix}.check must reference a false check: {check}")
        false_checks = {key for key in required_checks if checks.get(key) is False}
        if critic.get("decision") == "reject":
            if not false_checks:
                errors.append(f"{prefix} rejected review must contain at least one false check")
            if not objections:
                errors.append(f"{prefix} rejected review must contain objections")
            if objection_checks != false_checks:
                errors.append(
                    f"{prefix} rejected review objections must cover exactly false checks: "
                    f"false={sorted(false_checks)}, objections={sorted(objection_checks)}"
                )
        if critic.get("decision") == "approve":
            if objections:
                errors.append(f"{prefix} approved review cannot contain unresolved objections")
            failed_checks = sorted(key for key in required_checks if checks.get(key) is not True)
            if failed_checks:
                errors.append(f"{prefix} approved review has failed checks: {failed_checks}")
        previous_objections = objection_ids
    final = cycles[-1]
    if isinstance(final, dict):
        if final.get("target_digest") != expected_digest:
            errors.append("final review digest does not match current target")
        if final.get("proposer", {}).get("decision") != "approve":
            errors.append("final proposer decision must be approve")
        if final.get("critic", {}).get("decision") != "approve":
            errors.append("final critic decision must be approve")
    return errors


def selected_solution_ids(design: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id"))
        for item in design.get("solutions", [])
        if isinstance(item, dict) and item.get("status") == "selected"
    }


def validate_execution(execution: dict[str, Any], design: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(execution, "round_id", errors)
    workflow = execution.get("project_workflow")
    if not isinstance(workflow, dict):
        errors.append("project_workflow must be an object")
    else:
        if workflow.get("guard_status") != "pass":
            errors.append("project_workflow.guard_status must be pass")
        require(workflow, "project_root", errors, "project_workflow.")
        validate_evidence(workflow.get("evidence"), "project_workflow.evidence", errors)
    bindings = require_list(execution, "bindings", errors)
    bound_ids: set[str] = set()
    candidate_ids: set[str] = set()
    run_ids: set[str] = set()
    for index, binding in enumerate(bindings):
        prefix = f"bindings[{index}]"
        if not isinstance(binding, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ["solution_id", "candidate_id", "run_id", "status"]:
            require(binding, field, errors, f"{prefix}.")
        bound_ids.add(str(binding.get("solution_id")))
        candidate_id = str(binding.get("candidate_id"))
        run_id = str(binding.get("run_id"))
        if candidate_id in candidate_ids:
            errors.append(f"candidate_id reused across solutions: {candidate_id}")
        if run_id in run_ids:
            errors.append(f"run_id reused across solutions: {run_id}")
        candidate_ids.add(candidate_id)
        run_ids.add(run_id)
        validate_evidence(binding.get("evidence"), f"{prefix}.evidence", errors)
    if bound_ids != selected_solution_ids(design):
        errors.append("bindings must cover exactly the selected solutions")
    return errors


def validate_evaluation(
    evaluation: dict[str, Any], design: dict[str, Any], goal: dict[str, Any] | None = None
) -> list[str]:
    errors: list[str] = []
    require(evaluation, "round_id", errors)
    results = require_list(evaluation, "solution_results", errors)
    result_ids: set[str] = set()
    for index, result in enumerate(results):
        prefix = f"solution_results[{index}]"
        if not isinstance(result, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require(result, "solution_id", errors, f"{prefix}.")
        if result.get("verdict") not in RESULT_VERDICTS:
            errors.append(f"{prefix}.verdict is invalid")
        for field in ["effect_on_goal", "claim_update", "next_implication"]:
            require(result, field, errors, f"{prefix}.")
        validate_evidence(result.get("evidence"), f"{prefix}.evidence", errors)
        result_ids.add(str(result.get("solution_id")))
    if result_ids != selected_solution_ids(design):
        errors.append("solution_results must cover exactly the selected solutions")
    criteria = require_list(evaluation, "acceptance_results", errors)
    if not criteria:
        errors.append("acceptance_results must not be empty")
    result_acceptance_ids: set[str] = set()
    for index, result in enumerate(criteria):
        prefix = f"acceptance_results[{index}]"
        if not isinstance(result, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require(result, "acceptance_id", errors, f"{prefix}.")
        if not isinstance(result.get("passed"), bool):
            errors.append(f"{prefix}.passed must be a boolean")
        require(result, "observation", errors, f"{prefix}.")
        validate_evidence(result.get("evidence"), f"{prefix}.evidence", errors)
        result_acceptance_ids.add(str(result.get("acceptance_id")))
    if goal is not None:
        goal_acceptance_ids = {
            str(item.get("id"))
            for item in goal.get("acceptance_criteria", [])
            if isinstance(item, dict)
        }
        if result_acceptance_ids != goal_acceptance_ids:
            errors.append("acceptance_results must cover exactly the goal acceptance criteria")
    if not isinstance(evaluation.get("goal_met"), bool):
        errors.append("goal_met must be a boolean")
    if evaluation.get("goal_met") is True:
        failed = [
            item for item in criteria if not isinstance(item, dict) or item.get("passed") is not True
        ]
        if failed:
            errors.append("goal_met=true requires every acceptance result to pass")
    incumbent = evaluation.get("incumbent_update")
    if not isinstance(incumbent, dict):
        errors.append("incumbent_update must be an object")
    else:
        action = incumbent.get("action")
        if action not in {"unchanged", "replace", "augment"}:
            errors.append("incumbent_update.action must be unchanged, replace, or augment")
        require(incumbent, "reason", errors, "incumbent_update.")
        solution_id = incumbent.get("solution_id")
        if action in {"replace", "augment"} and str(solution_id) not in selected_solution_ids(design):
            errors.append("incumbent_update.solution_id must reference a selected solution")
        if evaluation.get("goal_met") is True and action not in {"replace", "augment"}:
            errors.append("goal_met=true requires replacing or augmenting the incumbent")
    return errors


def validate_evolution(
    evolution: dict[str, Any],
    design: dict[str, Any],
    evaluation: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    require(evolution, "round_id", errors)
    require(evolution, "round_learning", errors)
    actions = require_list(evolution, "actions", errors)
    if not actions:
        errors.append("actions must not be empty")
    known_ids = {
        str(item.get("id")) for item in design.get("solutions", []) if isinstance(item, dict)
    }
    selected_ids = selected_solution_ids(design)
    action_ids: set[str] = set()
    verdicts = {
        str(item.get("solution_id")): item.get("verdict")
        for item in (evaluation or {}).get("solution_results", [])
        if isinstance(item, dict)
    }
    reroot = False
    for index, action in enumerate(actions):
        prefix = f"actions[{index}]"
        if not isinstance(action, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if action.get("action") not in TREE_ACTIONS:
            errors.append(f"{prefix}.action is invalid")
        source_id = str(action.get("source_solution_id"))
        action_ids.add(source_id)
        if source_id not in known_ids:
            errors.append(f"{prefix}.source_solution_id must reference this round")
        require(action, "reason", errors, f"{prefix}.")
        evidence = require_list(action, "evidence", errors, f"{prefix}.")
        if not evidence:
            errors.append(f"{prefix}.evidence must not be empty")
        validate_evidence(evidence, f"{prefix}.evidence", errors)
        if action.get("action") == "prune":
            require(action, "reopen_when", errors, f"{prefix}.")
            if verdicts.get(source_id) in {"invalid_run", "inconclusive"}:
                errors.append(f"{prefix} cannot prune an invalid or inconclusive experiment")
        if action.get("action") in {"refine", "split"}:
            require(action, "next_branch", errors, f"{prefix}.")
        if action.get("action") == "reroot":
            reroot = True
    if action_ids != selected_ids:
        errors.append("evolution actions must cover exactly the selected solutions")
    goal_met = isinstance(evaluation, dict) and evaluation.get("goal_met") is True
    expected = "completed" if goal_met else ("assess_target" if reroot else "design_solutions")
    if evolution.get("next_stage") != expected:
        errors.append(f"next_stage must be {expected} for the declared actions")
    require(evolution, "next_focus", errors)
    return errors
