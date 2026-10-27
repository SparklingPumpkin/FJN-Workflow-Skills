#!/usr/bin/env python3
"""Apply an independently approved proposed solution tree."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from improvement_loop_guard import validate_tree, validate_workflow_bindings
from improvement_loop_policy import (
    DESIGN_REVIEW_CHECKS,
    EVOLUTION_REVIEW_CHECKS,
    ValidationError,
    artifact_digest,
    load_json,
    validate_design,
    validate_evaluation,
    validate_evolution,
    validate_execution,
    validate_goal,
    validate_review,
    write_json,
)

CONTROL_RELATIVE = Path("docs/improvement-loop")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def current_round(project_root: Path) -> tuple[Path, dict]:
    control = project_root.resolve() / CONTROL_RELATIVE
    state = load_json(control / "loop_state.json")
    if state.get("status") != "active" or state.get("stage") != "evolve_tree":
        raise ValidationError("tree can only be prepared or applied during active evolve_tree")
    number = state.get("round")
    if not isinstance(number, int) or number < 1:
        raise ValidationError("loop_state.round must be a positive integer")
    return control / "rounds" / f"round-{number:03d}", state


def build_proposed_tree(
    tree: dict,
    design: dict,
    execution: dict,
    evaluation: dict,
    evolution: dict,
    *,
    updated_at: str,
) -> dict:
    result_by_id = {
        str(item["solution_id"]): item
        for item in evaluation["solution_results"]
        if isinstance(item, dict)
    }
    action_by_id = {
        str(item["source_solution_id"]): item
        for item in evolution["actions"]
        if isinstance(item, dict)
    }
    binding_by_id = {
        str(item["solution_id"]): item
        for item in execution.get("bindings", [])
        if isinstance(item, dict)
    }
    proposed = deepcopy(tree)
    existing_ids = {
        str(item.get("id")) for item in proposed.get("nodes", []) if isinstance(item, dict)
    }
    selected = [
        item
        for item in design["solutions"]
        if isinstance(item, dict) and item.get("status") == "selected"
    ]
    for solution in selected:
        solution_id = str(solution["id"])
        if solution_id in existing_ids:
            raise ValidationError(f"solution tree already contains {solution_id}")
        result = result_by_id[solution_id]
        action = action_by_id[solution_id]
        relation = solution["tree_relation"]
        proposed["nodes"].append(
            {
                "id": solution_id,
                "parent_id": relation.get("parent_id"),
                "round_id": design["round_id"],
                "kind": solution["kind"],
                "status": result["verdict"],
                "claim": solution["claim"],
                "last_action": action["action"],
                "relation_type": relation["type"],
                "relation_rationale": relation["rationale"],
                "relation_evidence": relation["evidence"],
                "evidence": result["evidence"],
            }
        )
        if action["action"] == "prune":
            proposed["failed_memory"].append(
                {
                    "solution_id": solution_id,
                    "reason": action["reason"],
                    "evidence": action["evidence"],
                    "reopen_when": action["reopen_when"],
                }
            )

    root_claim = design["problem_analysis"]["root_cause"]["claim"]
    reroot_actions = [item for item in evolution["actions"] if item.get("action") == "reroot"]
    if reroot_actions:
        if proposed.get("root_problem"):
            proposed["root_history"].append(
                {
                    "round_id": design["round_id"],
                    "root_problem": proposed["root_problem"],
                    "reason": reroot_actions[0]["reason"],
                    "evidence": reroot_actions[0]["evidence"],
                }
            )
        proposed["root_problem"] = ""
    else:
        proposed["root_problem"] = root_claim

    incumbent_update = evaluation["incumbent_update"]
    if incumbent_update["action"] in {"replace", "augment"}:
        solution_id = str(incumbent_update["solution_id"])
        result = result_by_id[solution_id]
        binding = binding_by_id.get(solution_id, {})
        proposed["incumbent"] = {
            "solution_id": solution_id,
            "project_workflow_ref": (
                f"{binding.get('candidate_id', '')}/{binding.get('run_id', '')}"
            ).strip("/"),
            "summary": result["effect_on_goal"],
            "evidence": result["evidence"],
        }
    proposed["updated_at"] = updated_at
    return proposed


def load_tree_inputs(
    project_root: Path,
) -> tuple[Path, dict, dict, dict, dict, dict, dict, dict]:
    control = project_root.resolve() / CONTROL_RELATIVE
    current, state = current_round(project_root)
    return (
        current,
        state,
        load_json(control / "goal.json"),
        load_json(control / "solution_tree.json"),
        load_json(current / "design.json"),
        load_json(current / "execution.json"),
        load_json(current / "evaluation.json"),
        load_json(current / "evolution.json"),
    )


def validate_tree_inputs(
    project_root: Path,
    goal: dict,
    tree: dict,
    design: dict,
    execution: dict,
    evaluation: dict,
    evolution: dict,
    *,
    expected_round_id: str,
) -> list[str]:
    errors = validate_goal(goal)
    errors.extend(validate_tree(tree, project_root))
    if design.get("base_tree_digest") != artifact_digest(tree):
        errors.append("design.base_tree_digest does not match the current formal tree")
    for label, payload in [
        ("design", design),
        ("execution", execution),
        ("evaluation", evaluation),
        ("evolution", evolution),
    ]:
        if payload.get("round_id") != expected_round_id:
            errors.append(f"{label}.round_id must be {expected_round_id}")
    errors.extend(validate_design(design, goal, tree))
    errors.extend(validate_execution(execution, design))
    errors.extend(validate_evaluation(evaluation, design, goal))
    errors.extend(validate_evolution(evolution, design, evaluation))
    return errors


def prepare_tree(project_root: Path) -> dict[str, str | int | bool]:
    control = project_root.resolve() / CONTROL_RELATIVE
    current, state, goal, tree, design, execution, evaluation, evolution = load_tree_inputs(
        project_root
    )
    expected_round_id = f"round-{state['round']:03d}"
    errors = validate_tree_inputs(
        project_root,
        goal,
        tree,
        design,
        execution,
        evaluation,
        evolution,
        expected_round_id=expected_round_id,
    )
    errors.extend(
        validate_review(
            load_json(current / "design_review.json"),
            target_kind="design",
            expected_digest=artifact_digest(goal, design),
            required_checks=DESIGN_REVIEW_CHECKS,
            expected_round_id=expected_round_id,
        )
    )
    errors.extend(validate_workflow_bindings(execution))
    if errors:
        raise ValidationError("; ".join(errors))
    proposed = build_proposed_tree(
        tree,
        design,
        execution,
        evaluation,
        evolution,
        updated_at=now_iso(),
    )
    write_json(current / "proposed_tree.json", proposed)
    return {
        "prepared": True,
        "round": state["round"],
        "nodes_added": sum(
            1
            for item in design["solutions"]
            if isinstance(item, dict) and item.get("status") == "selected"
        ),
        "tree_digest": artifact_digest(proposed),
    }


def apply_tree(project_root: Path) -> dict[str, str | bool]:
    control = project_root.resolve() / CONTROL_RELATIVE
    current, state, goal, tree, design, execution, evaluation, evolution = load_tree_inputs(
        project_root
    )
    number = state["round"]
    expected_round_id = f"round-{number:03d}"
    proposed_tree = load_json(current / "proposed_tree.json")
    errors = validate_tree_inputs(
        project_root,
        goal,
        tree,
        design,
        execution,
        evaluation,
        evolution,
        expected_round_id=expected_round_id,
    )
    errors.extend(
        validate_review(
            load_json(current / "design_review.json"),
            target_kind="design",
            expected_digest=artifact_digest(goal, design),
            required_checks=DESIGN_REVIEW_CHECKS,
            expected_round_id=expected_round_id,
        )
    )
    errors.extend(validate_workflow_bindings(execution))
    errors.extend(validate_tree(proposed_tree, project_root))
    expected_tree = build_proposed_tree(
        tree,
        design,
        execution,
        evaluation,
        evolution,
        updated_at=str(proposed_tree.get("updated_at", "")),
    )
    if artifact_digest(expected_tree) != artifact_digest(proposed_tree):
        errors.append("proposed_tree does not match deterministic reconstruction")
    errors.extend(
        validate_review(
            load_json(current / "evolution_review.json"),
            target_kind="evolution",
            expected_digest=artifact_digest(
                goal, design, execution, evaluation, evolution, proposed_tree
            ),
            required_checks=EVOLUTION_REVIEW_CHECKS,
            expected_round_id=expected_round_id,
        )
    )
    if errors:
        raise ValidationError("; ".join(errors))
    write_json(control / "solution_tree.json", proposed_tree)
    return {
        "applied": True,
        "round_id": f"round-{number:03d}",
        "tree_digest": artifact_digest(proposed_tree),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "apply"])
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = prepare_tree(args.project_root) if args.command == "prepare" else apply_tree(args.project_root)
    except ValidationError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())