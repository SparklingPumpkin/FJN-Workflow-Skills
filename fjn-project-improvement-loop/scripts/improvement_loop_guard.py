#!/usr/bin/env python3
"""Validate the active stage of the project improvement loop."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from improvement_loop_policy import (
    DESIGN_REVIEW_CHECKS,
    EVOLUTION_REVIEW_CHECKS,
    STAGES,
    ValidationError,
    artifact_digest,
    load_json,
    validate_design,
    validate_evaluation,
    validate_evidence,
    validate_evolution,
    validate_execution,
    validate_goal,
    validate_review,
    write_json,
)

CONTROL_RELATIVE = Path("docs/improvement-loop")
PROJECT_WORKFLOW_GUARD = (
    Path(__file__).resolve().parents[2]
    / "fjn-project-workflow"
    / "scripts"
    / "project_workflow_guard.py"
)

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def control_dir(project_root: Path) -> Path:
    return project_root.resolve() / CONTROL_RELATIVE


def round_dir(project_root: Path, number: int) -> Path:
    return control_dir(project_root) / "rounds" / f"round-{number:03d}"


def validate_tree(tree: dict[str, Any], project_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    if tree.get("schema_version") != 2:
        errors.append("solution_tree.schema_version must be 2")
    nodes = tree.get("nodes")
    if not isinstance(nodes, list):
        errors.append("solution_tree.nodes must be a list")
        nodes = []
    node_ids: set[str] = set()
    parent_refs: list[tuple[str, str]] = []
    for index, node in enumerate(nodes):
        prefix = f"solution_tree.nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in [
            "id",
            "round_id",
            "kind",
            "status",
            "claim",
            "last_action",
            "relation_type",
            "relation_rationale",
        ]:
            if not str(node.get(field, "")).strip():
                errors.append(f"{prefix}.{field} must be non-empty")
        node_id = str(node.get("id"))
        if node_id in node_ids:
            errors.append(f"duplicate solution tree node: {node_id}")
        node_ids.add(node_id)
        parent_id = node.get("parent_id")
        if parent_id is not None:
            parent_refs.append((node_id, str(parent_id)))
            relation_evidence = node.get("relation_evidence")
            if not isinstance(relation_evidence, list) or not relation_evidence:
                errors.append(f"{prefix}.relation_evidence must support a parent edge")
            else:
                validate_evidence(
                    relation_evidence, f"{prefix}.relation_evidence", errors
                )
    for node_id, parent_id in parent_refs:
        if parent_id not in node_ids:
            errors.append(f"solution tree node {node_id} has unknown parent {parent_id}")
    parent_by_id = {node_id: parent_id for node_id, parent_id in parent_refs}
    for node_id in node_ids:
        seen: set[str] = set()
        current = node_id
        while current in parent_by_id:
            if current in seen:
                errors.append(f"solution tree contains a parent cycle at {current}")
                break
            seen.add(current)
            current = parent_by_id[current]
    failed_memory = tree.get("failed_memory")
    if not isinstance(failed_memory, list):
        errors.append("solution_tree.failed_memory must be a list")
    else:
        for index, item in enumerate(failed_memory):
            prefix = f"solution_tree.failed_memory[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for field in ["solution_id", "reason", "reopen_when"]:
                if not str(item.get(field, "")).strip():
                    errors.append(f"{prefix}.{field} must be non-empty")
            evidence = item.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"{prefix}.evidence must not be empty")
            else:
                validate_evidence(evidence, f"{prefix}.evidence", errors)
    if not isinstance(tree.get("root_history"), list):
        errors.append("solution_tree.root_history must be a list")
    incumbent = tree.get("incumbent")
    if not isinstance(incumbent, dict):
        errors.append("solution_tree.incumbent must be an object")
    if project_root is not None:
        evidence_groups: list[tuple[str, Any]] = []
        for index, node in enumerate(nodes):
            if isinstance(node, dict):
                evidence_groups.extend(
                    [
                        (f"solution_tree.nodes[{index}].relation_evidence", node.get("relation_evidence", [])),
                        (f"solution_tree.nodes[{index}].evidence", node.get("evidence", [])),
                    ]
                )
        if isinstance(failed_memory, list):
            evidence_groups.extend(
                (f"solution_tree.failed_memory[{index}].evidence", item.get("evidence", []))
                for index, item in enumerate(failed_memory)
                if isinstance(item, dict)
            )
        for label, items in evidence_groups:
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, str) or "::" not in item:
                    continue
                reference = item.split("::", 1)[0].strip()
                if reference.startswith(("http://", "https://")):
                    continue
                path = Path(reference)
                resolved = path if path.is_absolute() else project_root / path
                if not resolved.exists():
                    errors.append(f"{label}[{index}] references missing file: {reference}")
    return errors


def validate_tree_evolution(
    tree: dict[str, Any], design: dict[str, Any], evolution: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    nodes = {
        str(node.get("id")): node
        for node in tree.get("nodes", [])
        if isinstance(node, dict)
    }
    design_ids = {
        str(solution.get("id"))
        for solution in design.get("solutions", [])
        if isinstance(solution, dict) and solution.get("status") == "selected"
    }
    missing = sorted(design_ids - set(nodes))
    if missing:
        errors.append(f"solution_tree must persist every evaluated solution: {missing}")
    failed_ids = {
        str(item.get("solution_id"))
        for item in tree.get("failed_memory", [])
        if isinstance(item, dict)
    }
    for index, action in enumerate(evolution.get("actions", [])):
        if not isinstance(action, dict):
            continue
        source_id = str(action.get("source_solution_id"))
        node = nodes.get(source_id)
        if node is None:
            continue
        if node.get("last_action") != action.get("action"):
            errors.append(f"solution_tree node {source_id} must record its evolution action")
        if action.get("action") == "prune" and source_id not in failed_ids:
            errors.append(f"pruned solution {source_id} must be retained in failed_memory")
    return errors


def validate_workflow_bindings(execution: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    workflow = execution.get("project_workflow", {})
    workflow_root = Path(str(workflow.get("project_root", "")))
    if not PROJECT_WORKFLOW_GUARD.is_file():
        return [f"project workflow guard does not exist: {PROJECT_WORKFLOW_GUARD}"]
    completed = subprocess.run(
        [sys.executable, str(PROJECT_WORKFLOW_GUARD), "--project-root", str(workflow_root)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown guard failure"
        return [f"project workflow guard failed: {detail}"]
    workflow_state_path = workflow_root / "docs/project-control/state.json"
    try:
        workflow_state = load_json(workflow_state_path)
    except ValidationError as exc:
        return [str(exc)]
    candidates = workflow_state.get("candidates", {})
    runs = workflow_state.get("runs", {})
    if not isinstance(candidates, dict) or not isinstance(runs, dict):
        return ["project workflow state must contain candidate and run maps"]
    terminal_run_statuses = {"completed", "failed", "cancelled"}
    for index, binding in enumerate(execution.get("bindings", [])):
        if not isinstance(binding, dict):
            continue
        prefix = f"bindings[{index}]"
        candidate_id = binding.get("candidate_id")
        run_id = binding.get("run_id")
        candidate = candidates.get(candidate_id)
        run = runs.get(run_id)
        if not isinstance(candidate, dict):
            errors.append(f"{prefix}.candidate_id does not exist in project workflow")
            continue
        if not isinstance(run, dict):
            errors.append(f"{prefix}.run_id does not exist in project workflow")
            continue
        if run.get("candidate_id") != candidate_id:
            errors.append(f"{prefix} run does not belong to the declared candidate")
        if run_id not in candidate.get("run_ids", []):
            errors.append(f"{prefix} candidate does not reference the declared run")
        if run.get("status") not in terminal_run_statuses:
            errors.append(f"{prefix} run must be terminal before result evaluation")
        if binding.get("status") != run.get("status"):
            errors.append(f"{prefix}.status must match project workflow run status")
        if run.get("status") in terminal_run_statuses and not run.get("evidence"):
            errors.append(f"{prefix} terminal run needs durable project workflow evidence")
    return errors


def validate_artifact_marks(project_root: Path, number: int) -> list[str]:
    current = round_dir(project_root, number)
    try:
        execution = load_json(current / "execution.json")
        workflow_root = Path(execution["project_workflow"]["project_root"]).resolve()
        if workflow_root != project_root.resolve():
            return ["artifact review must use this project's workflow"]
        workflow = load_json(workflow_root / "docs/project-control/state.json")
    except (ValidationError, KeyError) as exc:
        return [str(exc)]
    sys.path.insert(0, str(PROJECT_WORKFLOW_GUARD.parent))
    from artifact_review import validate_artifact_review, TERMINAL
    errors = []
    expected = set()
    for binding in execution.get("bindings", []):
        candidate = workflow.get("candidates", {}).get(binding.get("candidate_id"), {})
        # Include failed retries, not just the successful binding in execution.
        for run_id in set(candidate.get("run_ids", [])) | {binding.get("run_id")}:
            run = workflow.get("runs", {}).get(run_id, {})
            if run.get("status") in TERMINAL:
                expected.add(run_id)
    if not expected:
        return []
    try:
        summary = load_json(current / "artifact_review.json")
    except ValidationError as exc:
        return [str(exc)]
    listed = summary.get("run_ids")
    if (summary.get("schema_version") != 1 or summary.get("round_id") != f"round-{number:03d}"
            or not isinstance(listed, list) or any(not isinstance(x, str) for x in listed)
            or len(set(listed)) != len(listed) or set(listed) != expected):
        errors.append("artifact_review must list exactly all terminal runs of the bound candidates, including retries")
    for run_id in sorted(expected):
        run = workflow["runs"][run_id]
        record = run.get("artifact_review")
        if not record:
            errors.append(f"{run_id}: register a keep/delete_candidate/needs_review mark via project workflow")
            continue
        errors.extend(f"{run_id}: {x}" for x in validate_artifact_review(workflow_root, workflow, run_id, record.get("review")))
        try:
            if load_json(workflow_root / record["reference"]) != record["review"]:
                errors.append(f"{run_id}: registered review file changed")
        except (ValidationError, KeyError) as exc:
            errors.append(str(exc))
    return errors


def validate_stage(project_root: Path, stage: str) -> tuple[list[str], dict[str, Any]]:
    target = control_dir(project_root)
    state = load_json(target / "loop_state.json")
    if state.get("status") != "active":
        return ["loop must be active"], state
    if state.get("stage") != stage:
        return [f"active stage is {state.get('stage')}, not {stage}"], state
    number = state.get("round")
    if not isinstance(number, int) or number < 1:
        return ["loop_state.round must be a positive integer"], state
    current_round = round_dir(project_root, number)
    design = load_json(current_round / "design.json")
    goal = load_json(target / "goal.json")
    expected_round_id = f"round-{number:03d}"
    errors: list[str] = []
    if design.get("round_id") != expected_round_id:
        errors.append(f"design.round_id must be {expected_round_id}")
    if stage == "assess_target":
        errors.extend(validate_goal(goal))
        errors.extend(validate_tree(load_json(target / "solution_tree.json"), project_root))
    elif stage == "design_solutions":
        errors.extend(validate_goal(goal))
        tree = load_json(target / "solution_tree.json")
        errors.extend(validate_tree(tree, project_root))
        if design.get("base_tree_digest") != artifact_digest(tree):
            errors.append("design.base_tree_digest must match the current formal tree")
        errors.extend(validate_design(design, goal, tree))
        errors.extend(
            validate_review(
                load_json(current_round / "design_review.json"),
                target_kind="design",
                expected_digest=artifact_digest(goal, design),
                required_checks=DESIGN_REVIEW_CHECKS,
                expected_round_id=expected_round_id,
            )
        )
    elif stage == "execute_via_workflow":
        tree = load_json(target / "solution_tree.json")
        if design.get("base_tree_digest") != artifact_digest(tree):
            errors.append("design.base_tree_digest must match the current formal tree")
        errors.extend(validate_design(design, goal, tree))
        errors.extend(
            validate_review(
                load_json(current_round / "design_review.json"),
                target_kind="design",
                expected_digest=artifact_digest(goal, design),
                required_checks=DESIGN_REVIEW_CHECKS,
                expected_round_id=expected_round_id,
            )
        )
        execution = load_json(current_round / "execution.json")
        if execution.get("round_id") != expected_round_id:
            errors.append(f"execution.round_id must be {expected_round_id}")
        errors.extend(validate_execution(execution, design))
        errors.extend(validate_workflow_bindings(execution))
    elif stage == "evaluate_results":
        tree = load_json(target / "solution_tree.json")
        if design.get("base_tree_digest") != artifact_digest(tree):
            errors.append("design.base_tree_digest must match the current formal tree")
        errors.extend(validate_design(design, goal, tree))
        errors.extend(
            validate_review(
                load_json(current_round / "design_review.json"),
                target_kind="design",
                expected_digest=artifact_digest(goal, design),
                required_checks=DESIGN_REVIEW_CHECKS,
                expected_round_id=expected_round_id,
            )
        )
        execution = load_json(current_round / "execution.json")
        if execution.get("round_id") != expected_round_id:
            errors.append(f"execution.round_id must be {expected_round_id}")
        errors.extend(validate_execution(execution, design))
        errors.extend(validate_workflow_bindings(execution))
        evaluation = load_json(current_round / "evaluation.json")
        if evaluation.get("round_id") != expected_round_id:
            errors.append(f"evaluation.round_id must be {expected_round_id}")
        errors.extend(validate_evaluation(evaluation, design, goal))
    elif stage in {"evolve_tree", "review_artifacts"}:
        tree = load_json(target / "solution_tree.json")
        proposed_tree = load_json(current_round / "proposed_tree.json")
        evolution = load_json(current_round / "evolution.json")
        evaluation = load_json(current_round / "evaluation.json")
        execution = load_json(current_round / "execution.json")
        if execution.get("round_id") != expected_round_id:
            errors.append(f"execution.round_id must be {expected_round_id}")
        if evaluation.get("round_id") != expected_round_id:
            errors.append(f"evaluation.round_id must be {expected_round_id}")
        if evolution.get("round_id") != expected_round_id:
            errors.append(f"evolution.round_id must be {expected_round_id}")
        errors.extend(validate_tree(tree, project_root))
        errors.extend(validate_tree(proposed_tree, project_root))
        errors.extend(validate_design(design, goal, tree))
        errors.extend(
            validate_review(
                load_json(current_round / "design_review.json"),
                target_kind="design",
                expected_digest=artifact_digest(goal, design),
                required_checks=DESIGN_REVIEW_CHECKS,
                expected_round_id=expected_round_id,
            )
        )
        errors.extend(validate_execution(execution, design))
        errors.extend(validate_workflow_bindings(execution))
        errors.extend(validate_evaluation(evaluation, design, goal))
        errors.extend(validate_evolution(evolution, design, evaluation))
        errors.extend(validate_tree_evolution(proposed_tree, design, evolution))
        errors.extend(
            validate_review(
                load_json(current_round / "evolution_review.json"),
                target_kind="evolution",
                expected_digest=artifact_digest(
                    goal, design, execution, evaluation, evolution, proposed_tree
                ),
                required_checks=EVOLUTION_REVIEW_CHECKS,
                expected_round_id=expected_round_id,
            )
        )
        if artifact_digest(tree) != artifact_digest(proposed_tree):
            errors.append("approved proposed_tree must be applied before leaving evolve_tree")
        if stage == "review_artifacts":
            errors.extend(validate_artifact_marks(project_root, number))
    return errors, state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--write-state", action="store_true")
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    try:
        state = load_json(control_dir(project_root) / "loop_state.json")
        stage = args.stage or state.get("stage")
        if stage not in STAGES:
            raise ValidationError(f"invalid active stage: {stage}")
        errors, state = validate_stage(project_root, stage)
    except ValidationError as exc:
        errors, state, stage = [str(exc)], {}, args.stage
    passed = not errors
    if args.write_state and state:
        state["last_guard"] = {
            "stage": stage,
            "round": state.get("round"),
            "passed": passed,
            "checked_at": now_iso(),
            "errors": errors,
        }
        state["updated_at"] = now_iso()
        write_json(control_dir(project_root) / "loop_state.json", state)
    print(json.dumps({"passed": passed, "stage": stage, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
