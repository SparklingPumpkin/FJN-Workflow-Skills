#!/usr/bin/env python3
"""Initialize and advance the project improvement loop, including artifact review."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from improvement_loop_policy import (
    STAGES,
    STOP_STATUSES,
    ValidationError,
    artifact_digest,
    load_json,
    write_json,
)

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent / "templates"
CONTROL_RELATIVE = Path("docs/improvement-loop")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def control_dir(project_root: Path) -> Path:
    return project_root.resolve() / CONTROL_RELATIVE


def state_path(project_root: Path) -> Path:
    return control_dir(project_root) / "loop_state.json"


def round_id(number: int) -> str:
    return f"round-{number:03d}"


def round_dir(project_root: Path, number: int) -> Path:
    return control_dir(project_root) / "rounds" / round_id(number)


def create_round(project_root: Path, number: int) -> None:
    target = round_dir(project_root, number)
    target.mkdir(parents=True, exist_ok=False)
    for filename in ["design.json", "execution.json", "evaluation.json", "evolution.json", "artifact_review.json"]:
        payload = load_json(TEMPLATE_DIR / filename)
        payload["round_id"] = round_id(number)
        if filename == "design.json":
            payload["base_tree_digest"] = artifact_digest(
                load_json(control_dir(project_root) / "solution_tree.json")
            )
        write_json(target / filename, payload)
    for filename, target_kind in [
        ("design_review.json", "design"),
        ("evolution_review.json", "evolution"),
    ]:
        review = load_json(TEMPLATE_DIR / "review.json")
        review["round_id"] = round_id(number)
        review["target_kind"] = target_kind
        write_json(target / filename, review)
    shutil.copy2(control_dir(project_root) / "solution_tree.json", target / "proposed_tree.json")


def init_project(project_root: Path, dry_run: bool) -> dict[str, Any]:
    project_root = project_root.resolve()
    if not project_root.is_dir():
        raise ValidationError(f"project root is not a directory: {project_root}")
    target = control_dir(project_root)
    if target.exists():
        raise ValidationError(f"improvement loop already exists: {target}")
    if dry_run:
        return {"dry_run": True, "control_dir": str(target), "stage": STAGES[0]}
    timestamp = now_iso()
    target.mkdir(parents=True)
    goal = load_json(TEMPLATE_DIR / "goal.json")
    goal["project_root"] = str(project_root)
    goal["updated_at"] = timestamp
    write_json(target / "goal.json", goal)
    tree = load_json(TEMPLATE_DIR / "solution_tree.json")
    tree["updated_at"] = timestamp
    write_json(target / "solution_tree.json", tree)
    state = {
        "schema_version": 2,
        "skill": "fjn-project-improvement-loop",
        "project_root": str(project_root),
        "stage": STAGES[0],
        "round": 1,
        "status": "active",
        "stop_decision": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "history": [],
        "last_guard": None,
    }
    write_json(state_path(project_root), state)
    create_round(project_root, 1)
    return {"initialized": True, "control_dir": str(target), "stage": STAGES[0]}


def migrate_v1(project_root: Path, dry_run: bool) -> dict[str, Any]:
    project_root = project_root.resolve()
    target = control_dir(project_root)
    if (target / "loop_state.json").exists():
        raise ValidationError("current control plane already exists")
    legacy_state = target / "run_state.json"
    if not legacy_state.is_file():
        raise ValidationError(f"legacy run_state.json does not exist: {legacy_state}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = target.parent / f"improvement-loop-v1-{stamp}"
    if archive.exists():
        raise ValidationError(f"migration archive already exists: {archive}")
    if dry_run:
        return {
            "dry_run": True,
            "legacy_control_dir": str(target),
            "archive": str(archive),
            "new_control_dir": str(target),
        }
    shutil.move(str(target), str(archive))
    init_project(project_root, dry_run=False)
    new_target = control_dir(project_root)
    goal = load_json(new_target / "goal.json")
    archive_ref = str(archive.relative_to(project_root))
    goal["current_state"]["summary"] = (
        "Migrated from the legacy improvement loop; reassess current project state before advancing."
    )
    goal["current_state"]["evidence"] = [
        f"{archive_ref}/run_state.json::preserves the legacy loop state without translating its conclusions"
    ]
    write_json(new_target / "goal.json", goal)
    state = load_json(new_target / "loop_state.json")
    state["migration"] = {
        "source_schema": 1,
        "archive": archive_ref,
        "migrated_at": now_iso(),
        "requires_reassessment": True,
    }
    write_json(new_target / "loop_state.json", state)
    return {"migrated": True, "archive": str(archive), "stage": STAGES[0]}


def expected_next(project_root: Path, state: dict[str, Any]) -> str:
    stage = state.get("stage")
    if stage == "assess_target":
        return "design_solutions"
    if stage == "design_solutions":
        return "execute_via_workflow"
    if stage == "execute_via_workflow":
        return "evaluate_results"
    if stage == "evaluate_results":
        return "evolve_tree"
    if stage == "evolve_tree":
        return "review_artifacts"
    if stage == "review_artifacts":
        evaluation = load_json(round_dir(project_root, state["round"]) / "evaluation.json")
        if evaluation.get("goal_met") is True:
            return "completed"
        evolution = load_json(round_dir(project_root, state["round"]) / "evolution.json")
        return str(evolution.get("next_stage"))
    raise ValidationError(f"invalid active stage: {stage}")


def advance(project_root: Path) -> dict[str, Any]:
    state = load_json(state_path(project_root))
    if state.get("status") != "active":
        raise ValidationError("only an active loop can advance")
    guard = state.get("last_guard")
    if (
        not isinstance(guard, dict)
        or guard.get("stage") != state.get("stage")
        or guard.get("round") != state.get("round")
        or guard.get("passed") is not True
    ):
        raise ValidationError("current stage and round must pass guard before advance")
    from improvement_loop_guard import validate_stage

    errors, _ = validate_stage(project_root.resolve(), str(state["stage"]))
    if errors:
        raise ValidationError("current stage changed after guard: " + "; ".join(errors))
    next_stage = expected_next(project_root, state)
    timestamp = now_iso()
    previous = state["stage"]
    state["history"].append(
        {"stage": previous, "round": state["round"], "completed_at": timestamp}
    )
    if next_stage == "completed":
        state["status"] = "completed"
        state["stop_decision"] = {
            "status": "fulfilled",
            "reason": "all acceptance criteria passed",
        }
    else:
        if previous == "review_artifacts":
            state["round"] += 1
            create_round(project_root, state["round"])
        state["stage"] = next_stage
    state["last_guard"] = None
    state["updated_at"] = timestamp
    write_json(state_path(project_root), state)
    return {
        "from": previous,
        "to": next_stage,
        "round": state["round"],
        "status": state["status"],
    }


def stop(project_root: Path, status: str, reason: str) -> dict[str, Any]:
    state = load_json(state_path(project_root))
    if state.get("status") != "active":
        raise ValidationError("loop is already terminal")
    # A stop must not silently skip marks for completed experiments. Running work
    # and empty/unexecuted rounds do not require invented terminal-run records.
    execution = load_json(round_dir(project_root, state["round"]) / "execution.json")
    if execution.get("bindings"):
        from improvement_loop_guard import validate_artifact_marks
        errors = validate_artifact_marks(project_root, state["round"])
        if errors:
            raise ValidationError("review completed run artifacts before stopping: " + "; ".join(errors))
    timestamp = now_iso()
    state["status"] = "stopped"
    state["stop_decision"] = {"status": status, "reason": reason}
    state["updated_at"] = timestamp
    write_json(state_path(project_root), state)
    return {"stopped": True, "status": status, "reason": reason}


def revise(project_root: Path) -> dict[str, Any]:
    state = load_json(state_path(project_root))
    if state.get("status") not in {"completed", "stopped"}:
        raise ValidationError("only a terminal loop can be revised")
    target = control_dir(project_root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = target / "revisions" / stamp
    archive.mkdir(parents=True)
    for name in ["loop_state.json", "goal.json", "solution_tree.json", "CURRENT.md", "final_report.md"]:
        source = target / name
        if source.exists():
            shutil.copy2(source, archive / name)
    shutil.copytree(target / "rounds", archive / "rounds")
    timestamp = now_iso()
    state.update(
        {
            "stage": STAGES[0],
            "round": state["round"] + 1,
            "status": "active",
            "stop_decision": None,
            "last_guard": None,
            "updated_at": timestamp,
            "previous_revision_archive": str(archive.relative_to(project_root)),
        }
    )
    write_json(state_path(project_root), state)
    create_round(project_root, state["round"])
    return {"revised": True, "archive": str(archive), "round": state["round"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init")
    init.add_argument("--project-root", required=True, type=Path)
    init.add_argument("--dry-run", action="store_true")
    migrate = subparsers.add_parser("migrate-v1")
    migrate.add_argument("--project-root", required=True, type=Path)
    migrate.add_argument("--dry-run", action="store_true")
    for name in ["status", "advance", "revise"]:
        command = subparsers.add_parser(name)
        command.add_argument("--project-root", required=True, type=Path)
    halt = subparsers.add_parser("stop")
    halt.add_argument("--project-root", required=True, type=Path)
    halt.add_argument("--status", required=True, choices=sorted(STOP_STATUSES - {"fulfilled"}))
    halt.add_argument("--reason", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = init_project(args.project_root, args.dry_run)
        elif args.command == "migrate-v1":
            result = migrate_v1(args.project_root, args.dry_run)
        elif args.command == "status":
            result = load_json(state_path(args.project_root))
        elif args.command == "advance":
            result = advance(args.project_root)
        elif args.command == "revise":
            result = revise(args.project_root)
        else:
            result = stop(args.project_root, args.status, args.reason)
    except ValidationError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
