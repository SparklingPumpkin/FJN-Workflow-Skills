#!/usr/bin/env python3
"""Shared evidence checks for measured acceptance; never infer truth from a path alone."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

SCOPES = {"end_to_end", "cached_incremental", "stage"}
# A hint for missing structure, not a parser of the user's entire contract.
TIME_LIMIT = re.compile(r"\d+(?:\.\d+)?\s*(?:秒|分钟|毫秒|seconds?(?![a-z])|minutes?(?![a-z])|ms(?![a-z])|min(?![a-z])|s(?![a-z]))", re.I)


def has_time_limit(text: str) -> bool:
    return bool(TIME_LIMIT.search(text))


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def read_object(root: Path, reference: str) -> dict[str, Any]:
    path = Path(reference)
    if not path.is_absolute():
        path = root / path
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON object required: {reference}")
    return data


def evidence_errors(items: Any, root: Path | None, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(items, list) or not items:
        return [f"{label}: nonempty reference::claim evidence required"]
    for item in items:
        if not isinstance(item, str) or "::" not in item:
            errors.append(f"{label}: evidence must use reference::claim")
            continue
        reference, claim = item.split("::", 1)
        if not reference.strip() or not claim.strip():
            errors.append(f"{label}: evidence needs reference and claim")
        elif root is not None:
            path = Path(reference.strip())
            if not path.is_absolute():
                path = root / path
            if not path.is_file():
                errors.append(f"{label}: local evidence file missing: {reference}")
    return errors


def validate_timing_requirement(requirement: Any) -> list[str]:
    if not isinstance(requirement, dict):
        return ["timing_requirement object required for a timed criterion"]
    errors: list[str] = []
    if not isinstance(requirement.get("scope"), str) or requirement["scope"] not in SCOPES:
        errors.append("timing_requirement.scope must be end_to_end, cached_incremental or stage")
    for field in ("input_boundary", "output_boundary"):
        if not isinstance(requirement.get(field), str) or not requirement[field].strip():
            errors.append(f"timing_requirement.{field} required")
    maximum = requirement.get("max_seconds")
    if not finite_number(maximum) or maximum <= 0:
        errors.append("timing_requirement.max_seconds must be positive and finite")
    return errors


def validate_timing_measurement(
    measurement: Any, requirement: dict[str, Any], root: Path | None,
    expected_run_ids: set[str] | None = None,
    *, enforce_budget: bool = True,
) -> list[str]:
    errors = validate_timing_requirement(requirement)
    if not isinstance(measurement, dict):
        return errors + ["timing_measurement required; unmeasured time cannot pass"]
    for field in ("scope", "input_boundary", "output_boundary"):
        if measurement.get(field) != requirement.get(field):
            errors.append(f"timing_measurement.{field} does not match the required scope/boundary")
    run_id = measurement.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append("timing_measurement.run_id required")
    elif expected_run_ids is not None and run_id not in expected_run_ids:
        errors.append("timing_measurement.run_id is not an executed run of this candidate/round")
    seconds = measurement.get("seconds")
    if not finite_number(seconds) or seconds < 0:
        errors.append("timing_measurement.seconds must be nonnegative and finite")
    elif enforce_budget and finite_number(requirement.get("max_seconds")) and seconds > requirement["max_seconds"]:
        errors.append("timing_measurement exceeds max_seconds")
    errors.extend(evidence_errors(measurement.get("boundary_evidence"), root, "timer boundaries"))
    inputs = measurement.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        errors.append("timing_measurement.inputs must enumerate raw/pretrained/scene-specific inputs")
    else:
        for index, item in enumerate(inputs):
            label = f"timing inputs[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label}: object required")
                continue
            if not isinstance(item.get("kind"), str) or item["kind"] not in {"raw_input", "generic_pretrained", "scene_state"}:
                errors.append(f"{label}: invalid input kind")
            if not isinstance(item.get("generated_in_timed_run"), bool):
                errors.append(f"{label}: generated_in_timed_run must be a boolean")
            if requirement.get("scope") == "end_to_end" and item.get("kind") == "scene_state" and item.get("generated_in_timed_run") is not True:
                errors.append(f"{label}: reused scene_state is excluded from end_to_end timing")
            reference = item.get("reference")
            if not isinstance(reference, str) or not reference.strip():
                errors.append(f"{label}: reference required")
            elif root is not None:
                path = Path(reference)
                if not path.is_absolute():
                    path = root / path
                if not path.exists():
                    errors.append(f"{label}: input missing: {reference}")
            errors.extend(evidence_errors(item.get("provenance_evidence"), root, label))
    outputs = measurement.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        errors.append("timing_measurement.outputs must identify delivered artifacts")
    else:
        for reference in outputs:
            if not isinstance(reference, str) or not reference.strip():
                errors.append("timing output reference required")
            elif root is not None:
                path = Path(reference)
                if not path.is_absolute():
                    path = root / path
                if not path.is_file():
                    errors.append(f"timing output missing: {reference}")
    timer = measurement.get("timer")
    if root is None:
        errors.append("timing acceptance needs project_root to reread raw timer evidence")
    elif not isinstance(timer, dict):
        errors.append("timing_measurement.timer required; sums/estimates are not wall-time evidence")
    else:
        try:
            raw = read_object(root, timer["reference"])
            if raw.get("run_id") != run_id:
                errors.append("raw timer run_id missing or differs from the measured run")
            if raw.get("outputs") != measurement.get("outputs"):
                errors.append("raw timer outputs missing or differ from delivered artifacts")
            start, end = raw[timer["start_field"]], raw[timer["end_field"]]
            if not finite_number(start) or not finite_number(end) or end < start:
                errors.append("raw timer must have finite ordered start/end values")
            elif finite_number(seconds) and not math.isclose(end - start, seconds, rel_tol=1e-6, abs_tol=0.01):
                errors.append("claimed seconds do not match the raw start/end timer")
            # Require the scope to be recorded at measurement time, not retrofitted in prose.
            for field in ("scope", "input_boundary", "output_boundary"):
                if raw.get(field) != measurement.get(field):
                    errors.append(f"raw timer {field} missing or differs from timing_measurement")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"cannot verify raw timer: {exc}")
    return errors


def acceptance_evidence_specifications(report: dict[str, Any], root: Path | None = None) -> list[str]:
    """Collect reviewed files so promotion cannot silently reuse changed evidence."""
    specifications: dict[str, str] = {}

    def add(items: list[str]) -> None:
        for item in items:
            reference = item.split("::", 1)[0].strip()
            specifications.setdefault(reference, item)

    for check in report["checks"]:
        add(check["evidence"])
        measurement = check.get("timing_measurement")
        if not isinstance(measurement, dict):
            continue
        add(measurement["boundary_evidence"])
        add([measurement["timer"]["reference"] + "::raw timing used for acceptance"])
        add([reference + "::delivered artifact used for timing acceptance" for reference in measurement["outputs"]])
        for item in measurement["inputs"]:
            add(item["provenance_evidence"])
            if root is not None:
                path = Path(item["reference"])
                if not path.is_absolute():
                    path = root / path
                if path.is_file():
                    add([item["reference"] + "::file input used for timing acceptance"])
    return list(specifications.values())


def validate_contract(contract: Any) -> list[str]:
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        return ["acceptance contract schema_version must be 1"]
    criteria = contract.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return ["acceptance contract criteria required"]
    errors: list[str] = []
    ids: set[str] = set()
    for item in criteria:
        if not isinstance(item, dict):
            errors.append("contract criterion must be an object")
            continue
        identity, text = item.get("id"), item.get("criterion")
        if not isinstance(identity, str) or not identity or identity in ids:
            errors.append("contract criterion id must be unique and nonempty")
        ids.add(str(identity))
        if not isinstance(text, str) or not text.strip():
            errors.append("contract criterion text required")
        if item.get("timing_requirement") is not None or has_time_limit(str(text)):
            errors.extend(validate_timing_requirement(item.get("timing_requirement")))
    return errors


def validate_acceptance_report(report: Any, root: Path, subject_id: str, run_ids: set[str], contract: dict[str, Any] | None = None) -> list[str]:
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        return ["acceptance report schema_version must be 1"]
    errors: list[str] = []
    if report.get("subject_id") != subject_id:
        errors.append("acceptance report subject_id differs from the candidate")
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        return errors + ["acceptance report needs criterion-by-criterion checks"]
    if contract is not None:
        errors.extend(validate_contract(contract))
        expected = {item.get("id"): item for item in contract.get("criteria", []) if isinstance(item, dict) and isinstance(item.get("id"), str)}
        actual_ids = {item.get("id") for item in checks if isinstance(item, dict) and isinstance(item.get("id"), str)}
        if actual_ids != set(expected):
            errors.append("acceptance report must cover exactly the pre-registered criteria")
        for check in checks:
            if not isinstance(check, dict):
                continue
            source = expected.get(str(check.get("id")), {})
            if check.get("criterion") != source.get("criterion") or check.get("timing_requirement") != source.get("timing_requirement"):
                errors.append("acceptance report changed a pre-registered criterion or timing requirement")
    ids: set[str] = set()
    measured_runs: set[str] = set()
    timed_report = any(isinstance(check, dict) and (check.get("timing_requirement") is not None or has_time_limit(str(check.get("criterion", "")))) for check in checks)
    for check in checks:
        if not isinstance(check, dict):
            errors.append("acceptance check must be an object")
            continue
        identity = check.get("id")
        if not isinstance(identity, str) or not identity.strip() or identity in ids:
            errors.append("acceptance check id must be nonempty and unique")
        ids.add(str(identity))
        criterion = check.get("criterion")
        if not isinstance(criterion, str) or not criterion.strip():
            errors.append("acceptance check criterion required")
        if check.get("passed") is not True:
            errors.append(f"acceptance check {identity} is not verified passed")
        errors.extend(evidence_errors(check.get("evidence"), root, f"acceptance check {identity}"))
        if timed_report:
            run_id = check.get("run_id")
            if not isinstance(run_id, str) or run_id not in run_ids:
                errors.append("all checks in a timed acceptance must identify an executed run")
            else:
                measured_runs.add(run_id)
        requirement = check.get("timing_requirement")
        if requirement is not None or has_time_limit(str(criterion)):
            errors.extend(validate_timing_requirement(requirement))
            if isinstance(requirement, dict):
                errors.extend(validate_timing_measurement(check.get("timing_measurement"), requirement, root, run_ids))
                if isinstance(check.get("timing_measurement"), dict) and check["timing_measurement"].get("run_id") != check.get("run_id"):
                    errors.append("timing and quality checks must describe the same run")
    if len(measured_runs) > 1:
        errors.append("cannot combine quality from one run with time from another")
    return errors
