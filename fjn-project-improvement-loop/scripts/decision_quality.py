"""Deterministic decision checks; scientific truth still requires evidence review.

Only designs containing decision_contract use this policy. Historical designs,
reviews and signatures are not rewritten or retroactively invalidated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from improvement_loop_policy import load_json, require, validate_evidence

PROGRESS_KINDS = {"goal_improved", "hypothesis_resolved", "observability_unblocked", "none"}


def active(design: dict[str, Any]) -> bool:
    return "decision_contract" in design


def evidence(items: Any, prefix: str, errors: list[str]) -> None:
    validate_evidence(items, prefix, errors)
    if not items:
        errors.append(f"{prefix} must contain evidence")


def string_set(value: Any, prefix: str, errors: list[str]) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        errors.append(f"{prefix} must be a list of non-empty strings")
        return set()
    if len(set(value)) != len(value):
        errors.append(f"{prefix} must not contain duplicates")
    return set(value)


def validate_decision_design(design: dict[str, Any]) -> list[str]:
    if not active(design):
        return []
    errors: list[str] = []
    contract = design.get("decision_contract")
    if (not isinstance(contract, dict) or type(contract.get("schema_version")) is not int
            or contract.get("schema_version") != 1):
        return ["decision_contract.schema_version must be 1"]
    selected = [s for s in design.get("solutions", [])
                if isinstance(s, dict) and s.get("status") == "selected"]
    probe_only = bool(selected) and all(s.get("kind") == "probe" for s in selected)
    evidence_gap_allowed = False
    coverage = contract.get("coverage")
    if not isinstance(coverage, dict):
        errors.append("decision_contract.coverage must be an object")
    else:
        slices = string_set(coverage.get("required_slices"), "coverage.required_slices", errors)
        if not slices:
            errors.append("coverage.required_slices must describe the claimed problem scope")
        cases = coverage.get("cases")
        if not isinstance(cases, list):
            errors.append("coverage.cases must be a list")
            cases = []
        covered: set[str] = set()
        roles: set[str] = set()
        for i, case in enumerate(cases):
            prefix = f"coverage.cases[{i}]"
            if not isinstance(case, dict):
                errors.append(f"{prefix} must be an object")
                continue
            group = case.get("slice")
            if not isinstance(group, str) or group not in slices:
                errors.append(f"{prefix}.slice must reference required_slices")
            else:
                covered.add(group)
            role = case.get("role")
            if not isinstance(role, str) or role not in {"failure", "control"}:
                errors.append(f"{prefix}.role must be failure or control")
            else:
                roles.add(role)
            evidence(case.get("evidence"), f"{prefix}.evidence", errors)
        if covered != slices or roles != {"failure", "control"}:
            gap = coverage.get("evidence_gap")
            if probe_only and isinstance(gap, dict):
                require(gap, "reason", errors, "coverage.evidence_gap.")
                probe_ids = string_set(gap.get("probe_ids"), "coverage.evidence_gap.probe_ids", errors)
                selected_ids = {s.get("id") for s in selected if isinstance(s.get("id"), str)}
                if not probe_ids or not probe_ids <= selected_ids:
                    errors.append("coverage.evidence_gap.probe_ids must identify selected evidence-gathering probes")
                else:
                    evidence_gap_allowed = True
            else:
                if covered != slices:
                    errors.append(f"coverage missing required slices: {sorted(slices - covered)}")
                if roles != {"failure", "control"}:
                    errors.append("coverage needs both failure evidence and a control/baseline; missing evidence permits only an explicit evidence-gathering probe")
        require(coverage, "scope_limits", errors, "coverage.")
    counterexample = contract.get("strongest_counterexample")
    if not isinstance(counterexample, dict):
        errors.append("decision_contract.strongest_counterexample must be an object")
    else:
        require(counterexample, "observation", errors, "strongest_counterexample.")
        if evidence_gap_allowed:
            validate_evidence(counterexample.get("evidence"), "strongest_counterexample.evidence", errors)
        else:
            evidence(counterexample.get("evidence"), "strongest_counterexample.evidence", errors)
    selection = contract.get("selection")
    if not isinstance(selection, dict):
        errors.append("decision_contract.selection must be an object")
    else:
        for field in ("cheapest_alternative", "why_selected", "parallel_basis"):
            require(selection, field, errors, "selection.")
    for i, solution in enumerate(design.get("solutions", [])):
        if not isinstance(solution, dict) or solution.get("status") != "selected":
            continue
        prefix = f"solutions[{i}].mechanism_check"
        mechanism = solution.get("mechanism_check")
        if not isinstance(mechanism, dict):
            errors.append(f"{prefix} must be an object")
            continue
        affected = string_set(mechanism.get("affected_acceptance_ids"), f"{prefix}.affected_acceptance_ids", errors)
        invariant = string_set(mechanism.get("invariant_acceptance_ids"), f"{prefix}.invariant_acceptance_ids", errors)
        acceptance = string_set(solution.get("acceptance_ids"), f"solutions[{i}].acceptance_ids", errors)
        if (affected | invariant) - acceptance:
            errors.append(f"{prefix} references criteria outside this solution's acceptance_ids")
        if affected & invariant:
            errors.append(f"{prefix} cannot declare the same criterion affected and invariant")
        if solution.get("kind") == "optimize" and not affected:
            errors.append(f"{prefix}: optimize must affect at least one claimed acceptance criterion; otherwise use a probe or another target")
        require(mechanism, "explanation", errors, f"{prefix}.")
        if evidence_gap_allowed:
            validate_evidence(mechanism.get("evidence"), f"{prefix}.evidence", errors)
        else:
            evidence(mechanism.get("evidence"), f"{prefix}.evidence", errors)
        if solution.get("next_if_supported") == solution.get("next_if_refuted"):
            errors.append(f"solutions[{i}]: supported/refuted outcomes must change the decision")
    return errors


def validate_decision_progress(evaluation: dict[str, Any], design: dict[str, Any]) -> list[str]:
    if not active(design):
        return []
    errors: list[str] = []
    for i, result in enumerate(evaluation.get("solution_results", [])):
        if not isinstance(result, dict):
            continue
        prefix = f"solution_results[{i}].decision_progress"
        progress = result.get("decision_progress")
        if not isinstance(progress, dict):
            errors.append(f"{prefix} must be an object")
            continue
        kind = progress.get("kind")
        if not isinstance(kind, str) or kind not in PROGRESS_KINDS:
            errors.append(f"{prefix}.kind is invalid")
        for field in ("before", "after"):
            require(progress, field, errors, f"{prefix}.")
        if kind != "none":
            evidence(progress.get("evidence"), f"{prefix}.evidence", errors)
            if progress.get("before") == progress.get("after"):
                errors.append(f"{prefix}: progress must change a decision or verified capability")
            if result.get("verdict") == "invalid_run":
                errors.append(f"{prefix}: invalid_run cannot establish scientific progress")
    return errors


def has_progress(evaluation: dict[str, Any]) -> bool:
    return any(
        isinstance(result, dict)
        and result.get("verdict") != "invalid_run"
        and isinstance(result.get("decision_progress"), dict)
        and isinstance(result["decision_progress"].get("kind"), str)
        and result["decision_progress"].get("kind") in PROGRESS_KINDS - {"none"}
        for result in evaluation.get("solution_results", [])
    )


def validate_stagnation(
    control: Path, number: int, design: dict[str, Any],
    evaluation: dict[str, Any], evolution: dict[str, Any],
    *, search_start_round: int = 1,
) -> list[str]:
    """Reassess after two consecutive rounds without progress, not after two failures.

    A valid negative result that resolves a hypothesis is progress. Legacy rounds
    are not assigned invented progress. A prior reroot starts a new search period.
    """
    if not active(design) or number <= search_start_round or has_progress(evaluation):
        return []
    previous = control / "rounds" / f"round-{number - 1:03d}"
    previous_design = load_json(previous / "design.json")
    if not active(previous_design):
        return []
    previous_evaluation = load_json(previous / "evaluation.json")
    previous_evolution = load_json(previous / "evolution.json")
    if has_progress(previous_evaluation) or any(
        isinstance(item, dict) and item.get("action") == "reroot"
        for item in previous_evolution.get("actions", [])
    ):
        return []
    errors: list[str] = []
    if not any(isinstance(item, dict) and item.get("action") == "reroot"
               for item in evolution.get("actions", [])):
        errors.append("two rounds without decision progress require reroot/reassessment before further refinement (or stop the loop)")
    review = evolution.get("search_reassessment")
    if not isinstance(review, dict):
        errors.append("stagnation requires search_reassessment, not another parameter variant")
    else:
        for field in ("why_stalled", "changed_approach"):
            require(review, field, errors, "search_reassessment.")
        evidence(review.get("evidence"), "search_reassessment.evidence", errors)
    return errors
