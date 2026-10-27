#!/usr/bin/env python3
"""Adaptive stage controller for metaskill-guided Copilot customization work."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from metaskill_policy import PROFILE_RANK, PROFILE_REQUIRED_STAGES, STAGE_ORDER, minimum_profile, recommended_stages

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def meta_dir(target_dir: Path) -> Path:
    return target_dir / ".metaskill"


def state_path(target_dir: Path) -> Path:
    return meta_dir(target_dir) / "run_state.json"


def manifest_dir(target_dir: Path) -> Path:
    return meta_dir(target_dir) / "stage_manifests"


def manifest_path(target_dir: Path, stage: str) -> Path:
    return manifest_dir(target_dir) / f"{stage}.json"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def default_state(target_dir: Path) -> dict:
    stamp = now_iso()
    return {
        "schema_version": 2,
        "skill": "metaskill",
        "target_customization_root": str(target_dir),
        "created_at": stamp,
        "updated_at": stamp,
        "active_stage": STAGE_ORDER[0],
        "stage_order": STAGE_ORDER,
        "workflow_profile": None,
        "selected_primitives": [],
        "selected_stages": ["solution_routing"],
        "stages": {
            stage: {"status": "not_started", "guard_status": "not_run"}
            for stage in STAGE_ORDER
        },
        "guard_history": [],
    }


def default_manifest(target_dir: Path, stage: str) -> dict:
    return {
        "schema_version": 2,
        "stage": stage,
        "status": "in_progress",
        "updated_at": now_iso(),
        "summary": "",
        "solution_routing": {
            "task_mode": "create-or-update",
            "desired_outcome": "",
            "trigger_phrases": [],
            "scope": "",
            "selected_primitives": [],
            "artifact_plan": [],
            "supporting_resources": [],
            "runtime_wiring": [],
            "risk_factors": [],
            "risk_assessment": {
                "bundled_resources_or_scripts": False,
                "requires_repository_exploration": False,
                "migrates_existing_customization": False,
                "changes_tools_or_trust": False,
                "handles_secrets_or_untrusted_input": False,
                "has_external_side_effects": False,
                "long_running_or_stateful": False,
                "omission_history": False,
                "requires_hard_gates": False,
                "executes_commands": False,
                "destructive_operations": False,
                "writes_outside_workspace": False,
                "network_access": False,
                "expands_permissions_or_approvals": False,
            },
            "workflow_profile": "",
            "workflow_profile_override_reason": "",
            "selected_stages": [],
            "routing_rationale": "",
        },
        "scope_intake": {
            "target_name": target_dir.name,
            "target_dir": str(target_dir),
            "purpose": "",
            "trigger_phrases": [],
            "expected_users": "",
            "selected_primitives": [],
            "scope": "",
            "composition_reason": "",
        },
        "upstream_baseline": {
            "selected_primitives_checked": [],
            "locations_checked": False,
            "discovery_and_invocation_checked": False,
            "schema_checked": False,
            "security_checked": False,
            "notes": "",
        },
        "local_contract": {
            "local_rules": [],
            "needs_stage_gating": False,
            "needs_guard_script": False,
            "needs_hooks": False,
            "needs_mcp": False,
            "state_location": "",
            "guard_policy": "",
            "approval_and_secret_policy": "",
        },
        "asset_plan": {
            "artifacts": [],
            "supporting_resources": [],
            "validation_commands": [],
        },
        "implementation": {
            "files_created": [],
            "files_updated": [],
            "artifacts_implemented": [],
            "runtime_wiring_implemented": [],
        },
        "validation": {
            "commands_run": [],
            "artifact_checks": [],
            "runtime_wiring_check": "",
            "security_check": "",
            "known_failures": [],
        },
        "handoff": {
            "usage": "",
            "selected_primitives": [],
            "workflow_profile": "",
            "stages_run": [],
            "changed_files": [],
            "validation_summary": "",
            "activation_or_approval_steps": [],
            "known_gaps": [],
            "next_maintenance_step": "",
        },
        "migration_audit": {
            "source_skill_or_workflow": "",
            "retained_rules": [],
            "removed_rules": [],
            "new_hard_gates": [],
            "compatibility_notes": "",
        },
    }


def ensure_stage(stage: str) -> None:
    if stage not in STAGE_ORDER:
        allowed = ", ".join(STAGE_ORDER)
        raise SystemExit(f"Unknown stage '{stage}'. Allowed stages: {allowed}")


def selected_stages(state: dict) -> list[str]:
    selected = state.get("selected_stages")
    if isinstance(selected, list) and selected:
        return [stage for stage in selected if stage in STAGE_ORDER]
    return ["solution_routing"]


def previous_selected_stage(state: dict, stage: str) -> str | None:
    selected = selected_stages(state)
    if stage not in selected:
        return None
    index = selected.index(stage)
    return selected[index - 1] if index > 0 else None


def ensure_manifest(target_dir: Path, stage: str, overwrite: bool = False) -> Path:
    path = manifest_path(target_dir, stage)
    if path.exists() and not overwrite:
        return path
    write_json(path, default_manifest(target_dir, stage))
    return path


def save_state(target_dir: Path, state: dict) -> None:
    state["updated_at"] = now_iso()
    write_json(state_path(target_dir), state)


def cmd_init(args: argparse.Namespace) -> None:
    target_dir = Path(args.target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(target_dir)
    if path.exists() and not args.force:
        print(f"Already initialized: {path}")
        return
    state = default_state(target_dir)
    state["stages"][STAGE_ORDER[0]]["status"] = "in_progress"
    write_json(path, state)
    ensure_manifest(target_dir, STAGE_ORDER[0], overwrite=args.force)
    print(f"Initialized metaskill state at {meta_dir(target_dir)}")


def cmd_route(args: argparse.Namespace) -> None:
    target_dir = Path(args.target_dir).resolve()
    state_file = state_path(target_dir)
    route_file = manifest_path(target_dir, "solution_routing")
    if not state_file.exists():
        raise SystemExit(f"Metaskill state is not initialized: {state_file}")
    if not route_file.exists():
        raise SystemExit(f"Missing solution routing manifest: {route_file}")
    state = load_json(state_file)
    if state.get("active_stage") != "solution_routing":
        raise SystemExit("Routing can only be recomputed while solution_routing is the active stage")
    manifest = load_json(route_file)
    route = manifest.get("solution_routing")
    if not isinstance(route, dict):
        raise SystemExit("solution_routing manifest section must be an object")
    task_mode = route.get("task_mode")
    if task_mode not in {"create-or-update", "review-only"}:
        raise SystemExit("Set task_mode to create-or-update or review-only before routing")

    minimum, reasons = minimum_profile(route)
    profile = args.profile or minimum
    if profile not in PROFILE_REQUIRED_STAGES:
        raise SystemExit(f"Unknown profile '{profile}'")
    if PROFILE_RANK[profile] < PROFILE_RANK[minimum]:
        raise SystemExit(
            f"Profile '{profile}' is below the computed minimum '{minimum}': " + "; ".join(reasons)
        )
    if PROFILE_RANK[profile] > PROFILE_RANK[minimum] and not args.override_reason:
        raise SystemExit("Selecting a heavier profile requires --override-reason")

    route["workflow_profile"] = profile
    route["workflow_profile_override_reason"] = args.override_reason or ""
    route["selected_stages"] = recommended_stages(route, profile)
    automatic_rationale = f"Minimum safe profile is {minimum}: " + "; ".join(reasons)
    route["routing_rationale"] = (
        f"{automatic_rationale}. Elevated to {profile}: {args.override_reason}"
        if profile != minimum
        else automatic_rationale
    )
    manifest["updated_at"] = now_iso()
    write_json(route_file, manifest)
    print(
        json.dumps(
            {
                "workflow_profile": profile,
                "minimum_profile": minimum,
                "selected_stages": route["selected_stages"],
                "reasons": reasons,
                "manifest": str(route_file),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_enter(args: argparse.Namespace) -> None:
    stage = args.stage
    ensure_stage(stage)
    target_dir = Path(args.target_dir).resolve()
    state_file = state_path(target_dir)
    if not state_file.exists():
        raise SystemExit(f"Metaskill state is not initialized: {state_file}")
    state = load_json(state_file)
    selected = selected_stages(state)
    if stage not in selected:
        raise SystemExit(
            f"Stage '{stage}' is not selected by the '{state.get('workflow_profile')}' routing profile. "
            "Revise and re-run the solution_routing guard before entering it."
        )
    previous = previous_selected_stage(state, stage)
    previous_guard = (
        state.get("stages", {}).get(previous, {}).get("guard_status") if previous else None
    )
    if previous and not args.force:
        previous_status = state.get("stages", {}).get(previous, {}).get("status")
        if previous_guard != "pass" or previous_status != "completed":
            raise SystemExit(
                f"Cannot enter '{stage}' because previous stage '{previous}' is "
                f"status='{previous_status}', guard='{previous_guard}'. Run metaskill_guard.py or use "
                "--force with --override-reason for a documented override."
            )
    if args.force and not args.override_reason:
        raise SystemExit("--force requires a non-empty --override-reason")
    if args.force:
        if previous and previous_guard != "pass":
            previous_state = state.setdefault("stages", {}).setdefault(previous, {})
            previous_state["status"] = "overridden"
            previous_state["guard_status"] = "overridden"
        state.setdefault("override_history", []).append(
            {
                "stage": stage,
                "previous_stage": previous,
                "previous_guard_status": previous_guard,
                "reason": args.override_reason,
                "recorded_at": now_iso(),
            }
        )
    state.setdefault("stages", {}).setdefault(stage, {"status": "not_started", "guard_status": "not_run"})
    current_index = selected.index(stage)
    for downstream in selected[current_index:]:
        downstream_state = state.setdefault("stages", {}).setdefault(downstream, {})
        downstream_state["status"] = "in_progress" if downstream == stage else "not_started"
        downstream_state["guard_status"] = "not_run"
        downstream_state.pop("last_guard_at", None)
        downstream_state.pop("manifest_sha256", None)
    state["active_stage"] = stage
    save_state(target_dir, state)
    path = ensure_manifest(target_dir, stage)
    print(f"Entered stage '{stage}'. Manifest: {path}")


def cmd_manifest(args: argparse.Namespace) -> None:
    stage = args.stage
    ensure_stage(stage)
    target_dir = Path(args.target_dir).resolve()
    if not state_path(target_dir).exists():
        raise SystemExit(f"Metaskill state is not initialized: {state_path(target_dir)}")
    print(ensure_manifest(target_dir, stage, overwrite=args.force))


def cmd_status(args: argparse.Namespace) -> None:
    target_dir = Path(args.target_dir).resolve()
    print(json.dumps(load_json(state_path(target_dir)), indent=2, ensure_ascii=False))


def add_target_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target-dir",
        "--skill-dir",
        dest="target_dir",
        required=True,
        help="Target customization root (legacy alias: --skill-dir)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize adaptive metaskill state")
    add_target_argument(init_parser)
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing state")
    init_parser.set_defaults(func=cmd_init)

    route_parser = subparsers.add_parser(
        "route", help="Compute the minimum safe profile and selected stages"
    )
    add_target_argument(route_parser)
    route_parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_REQUIRED_STAGES),
        help="Optionally select a profile at or above the computed minimum",
    )
    route_parser.add_argument(
        "--override-reason",
        help="Required reason when deliberately selecting a heavier profile",
    )
    route_parser.set_defaults(func=cmd_route)

    enter_parser = subparsers.add_parser("enter", help="Enter a metaskill stage")
    enter_parser.add_argument("stage", help="Stage name")
    add_target_argument(enter_parser)
    enter_parser.add_argument("--force", action="store_true", help="Allow documented override of previous guard")
    enter_parser.add_argument("--override-reason", help="Required audit reason when --force is used")
    enter_parser.set_defaults(func=cmd_enter)

    manifest_parser = subparsers.add_parser("manifest", help="Create or print a stage manifest path")
    manifest_parser.add_argument("stage", help="Stage name")
    add_target_argument(manifest_parser)
    manifest_parser.add_argument("--force", action="store_true", help="Overwrite the manifest template")
    manifest_parser.set_defaults(func=cmd_manifest)

    status_parser = subparsers.add_parser("status", help="Print current state")
    add_target_argument(status_parser)
    status_parser.set_defaults(func=cmd_status)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()