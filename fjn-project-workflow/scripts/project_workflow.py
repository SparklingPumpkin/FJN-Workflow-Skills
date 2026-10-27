#!/usr/bin/env python3
"""Deterministic controller for project versions, experiments, and directory layout."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_contract import acceptance_evidence_specifications, read_object, validate_acceptance_report, validate_contract
from artifact_review import validate_artifact_review, local_file

from workflow_core import (
    ALL_CHANGE_TYPES,
    CANDIDATE_STATUSES,
    DEFAULT_CONTROL_DIR,
    DEFAULT_MAX_ACTIVE_SIBLINGS,
    DEFAULT_MAX_MANAGED_DEPTH,
    DIRECTORY_ACTIONS,
    DIRECTORY_LEVELS,
    PROMOTABLE_CHANGE_TYPES,
    RUN_STATUSES,
    SCHEMA_VERSION,
    SCOPE_KINDS,
    WorkflowError,
    append_event_and_render,
    atomic_write_json,
    atomic_write_text,
    candidate_id_for,
    control_path,
    exclusive_lock,
    ledger_path,
    load_and_verify,
    make_event,
    next_id,
    now_iso,
    parse_evidence,
    project_path,
    render_views,
    replay_events,
    state_path,
    validate_change_types,
    validate_directory_proposal,
    sha256_file,
    acceptance_snapshot_errors,
    version_id,
)


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SCOPE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,100}$")
PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9]{0,11}$")


def project_root(args: argparse.Namespace) -> Path:
    root = Path(args.project_root).resolve()
    if not root.exists() or not root.is_dir():
        raise WorkflowError(f"Project root is not a directory: {root}")
    return root


def validate_slug(value: str, label: str = "slug") -> str:
    if not SLUG_RE.fullmatch(value):
        raise WorkflowError(f"{label} must use lowercase letters, digits, and single-purpose hyphens: {value}")
    return value


def validate_scope_id(value: str) -> str:
    if not SCOPE_ID_RE.fullmatch(value):
        raise WorkflowError(f"scope_id must be lowercase kebab-case: {value}")
    return value


def validate_prefix(value: str) -> str:
    if not PREFIX_RE.fullmatch(value):
        raise WorkflowError(f"scope prefix must use 1-12 uppercase letters/digits and begin with a letter: {value}")
    return value


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_initial_state(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    stamp = now_iso()
    scope_id = validate_scope_id(args.scope_id)
    prefix = validate_prefix(args.prefix)
    slug = validate_slug(args.initial_slug, "initial version slug")
    initial_id = version_id(prefix, args.initial_version)
    initial_evidence = parse_evidence(root, args.initial_evidence)
    return {
        "schema_version": SCHEMA_VERSION,
        "skill": "fjn-project-workflow",
        "project": {
            "project_id": validate_slug(args.project_id, "project_id"),
            "name": args.project_name.strip(),
            "root_hint": root.name,
            "control_dir": args.control_dir,
            "created_at": stamp,
        },
        "config": {
            "max_active_siblings": args.max_active_siblings,
            "max_managed_depth": args.max_managed_depth,
            "scope_prefix_required": True,
            "legacy_ids_are_aliases_only": True,
            "directory_policy": "hard_block_with_audited_override",
        },
        "scopes": {
            scope_id: {
                "scope_id": scope_id,
                "kind": args.scope_kind,
                "prefix": prefix,
                "label": args.scope_label.strip(),
                "purpose": args.scope_purpose.strip(),
                "parent_scope_id": None,
                "current_version_id": initial_id,
                "next_version_number": args.initial_version + 1,
                "version_ids": [initial_id],
                "candidate_ids": [],
                "created_at": stamp,
            }
        },
        "versions": {
            initial_id: {
                "version_id": initial_id,
                "scope_id": scope_id,
                "number": args.initial_version,
                "slug": slug,
                "status": "current",
                "parent_version_id": None,
                "promoted_from_candidate_id": None,
                "change_types": [],
                "summary": args.initial_summary.strip(),
                "evidence": initial_evidence,
                "legacy_id": args.legacy_id.strip() or None,
                "created_at": stamp,
            }
        },
        "candidates": {},
        "runs": {},
        "directories": {
            "dir-0001": {
                "directory_id": "dir-0001",
                "path": ".",
                "level": "project",
                "parent_directory_id": None,
                "scope_id": scope_id,
                "purpose": "项目边界；其子目录必须按业务职责继续登记。",
                "status": "active",
                "status_reason": "project initialized",
                "manage_children": False,
                "decision_id": None,
                "created_at": stamp,
                "updated_at": stamp,
            }
        },
        "layout_decisions": {},
        "updated_at": stamp,
        "ledger": {"event_count": 0, "head_hash": None},
    }


def cmd_init(args: argparse.Namespace) -> None:
    root = project_root(args)
    target = control_path(root, args.control_dir)
    if state_path(root, args.control_dir).exists() or ledger_path(root, args.control_dir).exists():
        raise WorkflowError(f"Project control already exists: {target}")
    if not args.project_name.strip() or not args.scope_label.strip() or not args.scope_purpose.strip() or not args.initial_summary.strip():
        raise WorkflowError("project name, scope label/purpose, and initial summary must be non-empty")
    if args.scope_kind not in SCOPE_KINDS:
        raise WorkflowError(f"Unknown scope kind: {args.scope_kind}")
    if args.max_active_siblings < 2:
        raise WorkflowError("max_active_siblings must be at least 2")
    if args.max_managed_depth < 3:
        raise WorkflowError("max_managed_depth must be at least 3")
    if args.initial_version < 1:
        raise WorkflowError("initial_version must be at least 1")
    if (args.initial_version > 1 or args.legacy_id.strip()) and not args.initial_evidence:
        raise WorkflowError("Adopting a legacy/high-number baseline requires --initial-evidence reference::claim")
    initial_state = build_initial_state(args, root)
    payload = {
        "initial_state": initial_state,
        "policy_decisions": {
            "version_identity": "scoped mainline vN; one-level candidate suffix; independent run_id",
            "history": "append-only hash-chained JSONL plus materialized JSON and generated Markdown views",
            "legacy_migration": "aliases only; never rename old project paths automatically",
        },
    }
    event = make_event("project_initialized", payload, None, 1)
    if args.dry_run:
        print_json({"action": "initialize", "control_dir": str(target), "event": event})
        return
    with exclusive_lock(root, args.control_dir):
        atomic_write_text(ledger_path(root, args.control_dir), json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        state = replay_events([event])
        atomic_write_json(state_path(root, args.control_dir), state)
        render_views(root, args.control_dir, state)
    print(f"Initialized project control: {target}")


def cmd_status(args: argparse.Namespace) -> None:
    state, _ = load_and_verify(project_root(args), args.control_dir)
    print_json(state)


def cmd_add_scope(args: argparse.Namespace) -> None:
    root = project_root(args)
    if not args.scope_label.strip() or not args.scope_purpose.strip() or not args.initial_summary.strip():
        raise WorkflowError("Scope label/purpose and initial summary must be non-empty")
    if (args.initial_version > 1 or args.legacy_id.strip()) and not args.initial_evidence:
        raise WorkflowError("Adopting a legacy/high-number scope baseline requires --initial-evidence reference::claim")
    if args.dry_run:
        state, _ = load_and_verify(root, args.control_dir)
        scope_id = validate_scope_id(args.scope_id)
        prefix = validate_prefix(args.prefix)
        if scope_id in state["scopes"]:
            raise WorkflowError(f"Scope already exists: {scope_id}")
        if prefix in {item["prefix"] for item in state["scopes"].values()}:
            raise WorkflowError(f"Scope prefix already exists: {prefix}")
        if args.parent_scope_id and args.parent_scope_id not in state["scopes"]:
            raise WorkflowError(f"Unknown parent scope: {args.parent_scope_id}")
        if args.initial_version < 1:
            raise WorkflowError("initial_version must be at least 1")
        parse_evidence(root, args.initial_evidence)
        initial_id = version_id(prefix, args.initial_version)
        print_json(
            {
                "action": "bootstrap_scope",
                "scope_id": scope_id,
                "prefix": prefix,
                "initial_version_id": initial_id,
                "legacy_id": args.legacy_id.strip() or None,
            }
        )
        return
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        scope_id = validate_scope_id(args.scope_id)
        prefix = validate_prefix(args.prefix)
        slug = validate_slug(args.initial_slug, "initial version slug")
        if scope_id in state["scopes"]:
            raise WorkflowError(f"Scope already exists: {scope_id}")
        if prefix in {item["prefix"] for item in state["scopes"].values()}:
            raise WorkflowError(f"Scope prefix already exists: {prefix}")
        if args.parent_scope_id and args.parent_scope_id not in state["scopes"]:
            raise WorkflowError(f"Unknown parent scope: {args.parent_scope_id}")
        if args.scope_kind not in SCOPE_KINDS:
            raise WorkflowError(f"Unknown scope kind: {args.scope_kind}")
        if args.initial_version < 1:
            raise WorkflowError("initial_version must be at least 1")
        stamp = now_iso()
        scope = {
            "scope_id": scope_id,
            "kind": args.scope_kind,
            "prefix": prefix,
            "label": args.scope_label.strip(),
            "purpose": args.scope_purpose.strip(),
            "parent_scope_id": args.parent_scope_id,
            "current_version_id": None,
            "next_version_number": args.initial_version,
            "version_ids": [],
            "candidate_ids": [],
            "created_at": stamp,
        }
        initial_id = version_id(prefix, args.initial_version)
        version = {
            "version_id": initial_id,
            "scope_id": scope_id,
            "number": args.initial_version,
            "slug": slug,
            "status": "current",
            "parent_version_id": None,
            "promoted_from_candidate_id": None,
            "change_types": [],
            "summary": args.initial_summary.strip(),
            "evidence": parse_evidence(root, args.initial_evidence),
            "legacy_id": args.legacy_id.strip() or None,
            "created_at": now_iso(),
        }
        _, event = append_event_and_render(
            root,
            args.control_dir,
            "scope_bootstrapped",
            {"scope": scope, "version": version},
        )
    print_json({"event_id": event["event_id"], "version_id": initial_id})


def cmd_record_legacy_version(args: argparse.Namespace) -> None:
    root = project_root(args)
    if args.number < 1:
        raise WorkflowError("Legacy version number must be at least 1")
    evidence = parse_evidence(root, args.evidence)
    if not evidence:
        raise WorkflowError("Legacy history import requires evidence; unknown relations must stay unknown")
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        scope = state["scopes"].get(args.scope_id)
        if not scope:
            raise WorkflowError(f"Unknown scope: {args.scope_id}")
        if args.number >= scope["next_version_number"]:
            raise WorkflowError(
                "Legacy import may only fill an older number below next_version_number; use a candidate and promotion for future versions"
            )
        identity = version_id(scope["prefix"], args.number)
        if identity in state["versions"]:
            raise WorkflowError(f"Version is already registered: {identity}")
        if args.parent_version_id:
            parent = state["versions"].get(args.parent_version_id)
            if not parent or parent["scope_id"] != args.scope_id:
                raise WorkflowError("Legacy parent must be an existing version in the same scope")
        version = {
            "version_id": identity,
            "scope_id": args.scope_id,
            "number": args.number,
            "slug": validate_slug(args.slug, "legacy version slug"),
            "status": "historical",
            "parent_version_id": args.parent_version_id,
            "promoted_from_candidate_id": None,
            "change_types": validate_change_types(args.change_type),
            "summary": args.summary.strip(),
            "evidence": evidence,
            "legacy_id": args.legacy_id.strip(),
            "created_at": now_iso(),
        }
        if not version["summary"] or not version["legacy_id"]:
            raise WorkflowError("Legacy version summary and original legacy_id are required")
        _, event = append_event_and_render(root, args.control_dir, "legacy_version_recorded", {"version": version})
    print_json({"event_id": event["event_id"], "version": version})


def layout_payload(args: argparse.Namespace, state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not args.reason.strip() or not args.purpose.strip():
        raise WorkflowError("Layout reason and directory purpose must be non-empty")
    validation = validate_directory_proposal(
        state,
        args.path,
        args.level,
        args.parent_directory_id,
        args.action,
        args.override_reason,
    )
    if validation["errors"]:
        raise WorkflowError("; ".join(validation["errors"]))
    decision_id = next_id("layout", state["layout_decisions"])
    decision = {
        "decision_id": decision_id,
        "scope_id": args.scope_id,
        "candidate_id": args.candidate_id,
        "action": args.action,
        "target_path": validation.get("normalized_path", Path(args.path).as_posix()),
        "target_level": args.level,
        "parent_directory_id": args.parent_directory_id,
        "purpose": args.purpose.strip(),
        "reason": args.reason.strip(),
        "alternatives_considered": args.alternative,
        "active_sibling_count_at_decision": validation["active_sibling_count"],
        "override_reason": args.override_reason.strip() or None,
        "status": "planned",
        "applied_directory_id": None,
        "created_at": now_iso(),
    }
    if args.scope_id and args.scope_id not in state["scopes"]:
        raise WorkflowError(f"Unknown scope: {args.scope_id}")
    if args.candidate_id and args.candidate_id not in state["candidates"]:
        raise WorkflowError(f"Unknown candidate: {args.candidate_id}")
    return decision, validation


def cmd_plan_layout(args: argparse.Namespace) -> None:
    root = project_root(args)
    state, _ = load_and_verify(root, args.control_dir)
    decision, validation = layout_payload(args, state)
    if not args.record:
        print_json({"recorded": False, "decision": decision, "validation": validation})
        return
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        decision, validation = layout_payload(args, state)
        _, event = append_event_and_render(root, args.control_dir, "layout_decision_recorded", {"decision": decision})
    print_json({"recorded": True, "event_id": event["event_id"], "decision": decision, "validation": validation})


def cmd_register_directory(args: argparse.Namespace) -> None:
    root = project_root(args)
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        decision = state["layout_decisions"].get(args.decision_id)
        if not decision:
            raise WorkflowError(f"Unknown layout decision: {args.decision_id}")
        if decision["status"] != "planned":
            raise WorkflowError(f"Layout decision is already applied: {args.decision_id}")
        validation = validate_directory_proposal(
            state,
            decision["target_path"],
            decision["target_level"],
            decision["parent_directory_id"],
            decision["action"],
            decision.get("override_reason") or "",
        )
        if validation["errors"]:
            raise WorkflowError("; ".join(validation["errors"]))
        if decision["action"] == "reuse":
            existing = next(
                item for item in state["directories"].values() if item["path"] == decision["target_path"]
            )
            _, event = append_event_and_render(
                root,
                args.control_dir,
                "layout_reuse_applied",
                {"decision_id": decision["decision_id"], "directory_id": existing["directory_id"]},
            )
            print_json({"event_id": event["event_id"], "reused_directory": existing})
            return
        target = project_path(root, decision["target_path"])
        created_now = False
        if args.create_directory:
            target.mkdir(parents=False, exist_ok=False)
            created_now = True
        elif not target.is_dir():
            raise WorkflowError(f"Directory does not exist; use --create-directory or create it after an approved plan: {target}")
        directory_id = next_id("dir", state["directories"])
        stamp = now_iso()
        directory = {
            "directory_id": directory_id,
            "path": decision["target_path"],
            "level": decision["target_level"],
            "parent_directory_id": decision["parent_directory_id"],
            "scope_id": decision.get("scope_id"),
            "purpose": decision["purpose"],
            "status": "active",
            "status_reason": "registered from approved layout decision",
            "manage_children": args.manage_children,
            "decision_id": decision["decision_id"],
            "created_at": stamp,
            "updated_at": stamp,
        }
        event_count_before = state["ledger"]["event_count"]
        try:
            _, event = append_event_and_render(root, args.control_dir, "directory_registered", {"directory": directory})
        except Exception:
            if created_now:
                try:
                    current_state, current_events = load_and_verify(root, args.control_dir)
                    ledger_unchanged = (
                        current_state["ledger"]["event_count"] == event_count_before
                        and len(current_events) == event_count_before
                    )
                except WorkflowError:
                    ledger_unchanged = False
                if ledger_unchanged:
                    target.rmdir()
            raise
    print_json({"event_id": event["event_id"], "directory": directory})


def cmd_set_directory_status(args: argparse.Namespace) -> None:
    root = project_root(args)
    if args.status not in {"active", "archived", "superseded", "external"}:
        raise WorkflowError(f"Unknown directory status: {args.status}")
    if not args.reason.strip():
        raise WorkflowError("A status reason is required")
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        if args.directory_id not in state["directories"]:
            raise WorkflowError(f"Unknown directory: {args.directory_id}")
        _, event = append_event_and_render(
            root,
            args.control_dir,
            "directory_status_changed",
            {"directory_id": args.directory_id, "status": args.status, "reason": args.reason.strip()},
        )
    print_json({"event_id": event["event_id"], "directory_id": args.directory_id, "status": args.status})


def cmd_create_candidate(args: argparse.Namespace) -> None:
    root = project_root(args)
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        scope = state["scopes"].get(args.scope_id)
        if not scope:
            raise WorkflowError(f"Unknown scope: {args.scope_id}")
        base_id = args.base_version_id or scope.get("current_version_id")
        if base_id not in state["versions"] or state["versions"][base_id]["scope_id"] != args.scope_id:
            raise WorkflowError(f"Base version does not belong to scope {args.scope_id}: {base_id}")
        directory = state["directories"].get(args.directory_id)
        if not directory or directory["level"] != "candidate" or directory["status"] != "active":
            raise WorkflowError("Candidate creation requires an active registered directory at level 'candidate'")
        decision = state["layout_decisions"].get(directory["decision_id"])
        if not decision or decision.get("candidate_id"):
            raise WorkflowError("Candidate directory layout must be planned before candidate identity exists; its decision cannot belong to another candidate")
        candidate_id = candidate_id_for(state, base_id)
        if Path(directory["path"]).name != candidate_id:
            raise WorkflowError(
                f"Candidate directory basename must equal the bounded candidate identity '{candidate_id}'"
            )
        candidate = {
            "candidate_id": candidate_id,
            "scope_id": args.scope_id,
            "base_version_id": base_id,
            "slug": validate_slug(args.slug, "candidate slug"),
            "status": "planned",
            "hypothesis": args.hypothesis.strip(),
            "change_types": validate_change_types(args.change_type),
            "directory_id": args.directory_id,
            "run_ids": [],
            "conclusion": None,
            "evidence": [],
            "promoted_to_version_id": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        if not candidate["hypothesis"]:
            raise WorkflowError("Candidate hypothesis must be non-empty")
        if args.acceptance_contract:
            try:
                contract = read_object(root, args.acceptance_contract)
            except (OSError, ValueError, TypeError) as exc:
                raise WorkflowError(f"Cannot read acceptance contract: {exc}") from exc
            errors = validate_contract(contract)
            if errors:
                raise WorkflowError("Acceptance contract rejected: " + "; ".join(errors))
            source = parse_evidence(root, [args.acceptance_contract + "::pre-registered user acceptance criteria"])[0]
            if not source.get("sha256_when_recorded"):
                raise WorkflowError("Acceptance contract must be a local file <=10 MB")
            candidate["acceptance_contract"] = {"source": source, "content": contract}
        _, event = append_event_and_render(root, args.control_dir, "candidate_created", {"candidate": candidate})
    print_json({"event_id": event["event_id"], "candidate": candidate})


def cmd_suggest_candidate_id(args: argparse.Namespace) -> None:
    root = project_root(args)
    state, _ = load_and_verify(root, args.control_dir)
    scope = state["scopes"].get(args.scope_id)
    if not scope:
        raise WorkflowError(f"Unknown scope: {args.scope_id}")
    base_id = args.base_version_id or scope.get("current_version_id")
    if base_id not in state["versions"] or state["versions"][base_id]["scope_id"] != args.scope_id:
        raise WorkflowError(f"Base version does not belong to scope {args.scope_id}: {base_id}")
    print(candidate_id_for(state, base_id))


def make_run_id(state: dict[str, Any], variant: str) -> str:
    validate_slug(variant, "run variant")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"run-{stamp}-{variant}"
    candidate = base
    suffix = 2
    while candidate in state["runs"]:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def cmd_suggest_run_id(args: argparse.Namespace) -> None:
    root = project_root(args)
    state, _ = load_and_verify(root, args.control_dir)
    print(make_run_id(state, args.variant))


def cmd_register_run(args: argparse.Namespace) -> None:
    root = project_root(args)
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        candidate = state["candidates"].get(args.candidate_id)
        if not candidate:
            raise WorkflowError(f"Unknown candidate: {args.candidate_id}")
        if candidate["status"] in {"passed", "failed", "abandoned", "promoted"}:
            raise WorkflowError(f"Cannot add runs to concluded candidate {args.candidate_id}")
        directory = state["directories"].get(args.directory_id)
        if not directory or directory["level"] != "run" or directory["status"] != "active":
            raise WorkflowError("Run registration requires an active registered directory at level 'run'")
        parent = state["directories"].get(directory["parent_directory_id"])
        if not parent or parent["directory_id"] != candidate["directory_id"]:
            raise WorkflowError("Run directory must be a direct child of the candidate directory")
        validate_slug(args.variant, "run variant")
        run_id = args.run_id
        if not re.fullmatch(r"run-\d{8}T\d{6}Z-[a-z0-9][a-z0-9-]{0,47}(?:-\d+)?", run_id):
            raise WorkflowError(f"Invalid run_id: {run_id}")
        run_tail = re.sub(r"^run-\d{8}T\d{6}Z-", "", run_id)
        if run_tail != args.variant and not re.fullmatch(rf"{re.escape(args.variant)}-\d+", run_tail):
            raise WorkflowError(f"run_id must use variant '{args.variant}' with only an optional collision counter")
        if run_id in state["runs"]:
            raise WorkflowError(f"Run is already registered: {run_id}")
        if Path(directory["path"]).name != run_id:
            raise WorkflowError(
                f"Run directory basename must equal run_id '{run_id}'; do not encode another version string."
            )
        run = {
            "run_id": run_id,
            "candidate_id": args.candidate_id,
            "variant": args.variant,
            "status": "planned",
            "directory_id": args.directory_id,
            "config_identity": args.config_identity.strip(),
            "code_identity": args.code_identity.strip(),
            "data_identity": args.data_identity.strip(),
            "artifact_review_required": True,
            "summary": "",
            "evidence": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        if not all([run["config_identity"], run["code_identity"], run["data_identity"]]):
            raise WorkflowError("Every run must record config, code, and data identity")
        _, event = append_event_and_render(root, args.control_dir, "run_registered", {"run": run})
    print_json({"event_id": event["event_id"], "run": run})


def cmd_rename_run(args: argparse.Namespace) -> None:
    root = project_root(args)
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        run = state["runs"].get(args.run_id)
        if not run:
            raise WorkflowError(f"Unknown run: {args.run_id}")
        if run["status"] in {"completed", "failed", "cancelled"}:
            raise WorkflowError("Only planned or running runs may be renamed")
        new_run_id = args.new_run_id
        new_variant = validate_slug(args.new_variant, "new run variant")
        if not re.fullmatch(r"run-\d{8}T\d{6}Z-[a-z0-9][a-z0-9-]{0,47}(?:-\d+)?", new_run_id):
            raise WorkflowError(f"Invalid new run_id: {new_run_id}")
        run_tail = re.sub(r"^run-\d{8}T\d{6}Z-", "", new_run_id)
        if run_tail != new_variant and not re.fullmatch(rf"{re.escape(new_variant)}-\d+", run_tail):
            raise WorkflowError(f"new run_id must use variant '{new_variant}' with only an optional collision counter")
        if new_run_id in state["runs"]:
            raise WorkflowError(f"Run is already registered: {new_run_id}")
        directory = state["directories"][run["directory_id"]]
        old_relative_path = Path(directory["path"])
        if old_relative_path.name != args.run_id:
            raise WorkflowError("Registered run directory basename does not match the old run_id")
        new_relative_path = old_relative_path.with_name(new_run_id)
        old_path = project_path(root, old_relative_path)
        new_path = project_path(root, new_relative_path)
        if not old_path.is_dir():
            raise WorkflowError(f"Registered run directory is missing: {old_path}")
        if new_path.exists():
            raise WorkflowError(f"Target run directory already exists: {new_path}")
        reason = args.reason.strip()
        if not reason:
            raise WorkflowError("Run rename reason must be non-empty")
        payload = {
            "old_run_id": args.run_id,
            "new_run_id": new_run_id,
            "new_variant": new_variant,
            "new_directory_path": new_relative_path.as_posix(),
            "reason": reason,
        }
        old_path.rename(new_path)
        try:
            _, event = append_event_and_render(root, args.control_dir, "run_renamed", payload)
        except Exception:
            new_path.rename(old_path)
            raise
    print_json({"event_id": event["event_id"], **payload})


def cmd_set_run_status(args: argparse.Namespace) -> None:
    root = project_root(args)
    if args.status not in RUN_STATUSES:
        raise WorkflowError(f"Unknown run status: {args.status}")
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        run = state["runs"].get(args.run_id)
        if not run:
            raise WorkflowError(f"Unknown run: {args.run_id}")
        allowed_transitions = {
            "planned": {"running", "completed", "failed", "cancelled"},
            "running": {"completed", "failed", "cancelled"},
            "completed": set(),
            "failed": set(),
            "cancelled": set(),
        }
        if args.status not in allowed_transitions.get(run["status"], set()):
            raise WorkflowError(f"Invalid or duplicate run transition: {run['status']} -> {args.status}")
        terminal = args.status in {"completed", "failed", "cancelled"}
        evidence = parse_evidence(root, args.evidence)
        if terminal and (not args.summary.strip() or not evidence):
            raise WorkflowError("A terminal run status requires a summary and at least one durable evidence reference")
        payload = {
            "run_id": args.run_id,
            "status": args.status,
            "summary": args.summary.strip(),
            "evidence": evidence,
        }
        _, event = append_event_and_render(root, args.control_dir, "run_status_changed", payload)
    print_json({"event_id": event["event_id"], **payload})


def cmd_record_artifact_review(args: argparse.Namespace) -> None:
    root = project_root(args)
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        try:
            path = local_file(root, args.review_file)
            review = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise WorkflowError(f"Invalid artifact review file: {exc}") from exc
        errors = validate_artifact_review(root, state, args.run_id, review)
        if errors:
            raise WorkflowError("; ".join(errors))
        payload = {"run_id": args.run_id, "artifact_review": {
            "reference": args.review_file, "sha256": sha256_file(path),
            "review": review, "recorded_at": now_iso(),
        }}
        _, event = append_event_and_render(root, args.control_dir, "artifact_review_recorded", payload)
    print_json({"event_id": event["event_id"], **payload, "deletion_executed": False})


def verified_acceptance(root: Path, candidate: dict[str, Any], reference: str, state: dict[str, Any]) -> dict[str, Any]:
    if not reference:
        raise WorkflowError("Passed/promoted candidates require --acceptance-report; a durable path alone is not acceptance")
    prior = candidate.get("acceptance_report")
    if prior:
        errors = acceptance_snapshot_errors(root, prior)
        if errors:
            raise WorkflowError("Previously accepted evidence rejected: " + "; ".join(errors))
    try:
        content = read_object(root, reference)
    except (OSError, ValueError, TypeError) as exc:
        raise WorkflowError(f"Cannot read acceptance report: {exc}") from exc
    contract = candidate.get("acceptance_contract")
    if not contract:
        raise WorkflowError("Acceptance requires a pre-registered --acceptance-contract on create-candidate; legacy records are not retroactively certified")
    contract_path = Path(contract["source"]["reference"])
    if not contract_path.is_absolute():
        contract_path = root / contract_path
    if not contract_path.is_file() or sha256_file(contract_path) != contract["source"].get("sha256_when_recorded"):
        raise WorkflowError("Pre-registered acceptance contract missing/changed; do not rewrite the user target after execution")
    completed_runs = {run_id for run_id in candidate["run_ids"] if state["runs"].get(run_id, {}).get("status") == "completed"}
    errors = validate_acceptance_report(content, root, candidate["candidate_id"], completed_runs, contract["content"])
    if errors:
        raise WorkflowError("Acceptance report rejected: " + "; ".join(errors))
    source = parse_evidence(root, [reference + "::structured acceptance checked against raw evidence"])[0]
    if not source.get("sha256_when_recorded"):
        raise WorkflowError("Acceptance report must be a local file no larger than 10 MB")
    snapshots = parse_evidence(root, acceptance_evidence_specifications(content, root))
    return {"source": source, "content": content, "evidence_snapshots": snapshots}


def cmd_conclude_candidate(args: argparse.Namespace) -> None:
    root = project_root(args)
    if args.status not in {"passed", "failed", "abandoned"}:
        raise WorkflowError("Candidate conclusion status must be passed, failed, or abandoned")
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        candidate = state["candidates"].get(args.candidate_id)
        if not candidate:
            raise WorkflowError(f"Unknown candidate: {args.candidate_id}")
        if candidate["status"] in {"passed", "failed", "abandoned", "promoted"}:
            raise WorkflowError(f"Candidate is already concluded: {args.candidate_id}")
        evidence = parse_evidence(root, args.evidence)
        if not args.summary.strip() or not evidence:
            raise WorkflowError("Candidate conclusion requires a summary and durable evidence")
        payload = {
            "candidate_id": args.candidate_id,
            "status": args.status,
            "summary": args.summary.strip(),
            "evidence": evidence,
        }
        if args.status == "passed":
            payload["acceptance_report"] = verified_acceptance(root, candidate, args.acceptance_report, state)
        _, event = append_event_and_render(root, args.control_dir, "candidate_concluded", payload)
    print_json({"event_id": event["event_id"], **payload})


def cmd_correct_conclusion(args: argparse.Namespace) -> None:
    """Append an evidence-backed erratum without changing status or identity."""
    root = project_root(args)
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        kind = "candidate" if args.candidate_id else "run"
        identity = args.candidate_id or args.run_id
        collection = "candidates" if kind == "candidate" else "runs"
        record = state[collection].get(identity)
        if record is None:
            raise WorkflowError(f"Unknown {kind}: {identity}")
        allowed = {"passed", "failed", "abandoned"} if kind == "candidate" else {"completed", "failed", "cancelled"}
        if record["status"] not in allowed:
            raise WorkflowError("Correct only terminal conclusions; promoted candidate snapshots remain immutable")
        if not args.summary.strip() or not args.reason.strip():
            raise WorkflowError("Correction requires a nonempty summary and reason")
        field = "conclusion" if kind == "candidate" else "summary"
        previous = record.get(field)
        if previous == args.summary.strip():
            raise WorkflowError("Correction must change the recorded conclusion")
        evidence = parse_evidence(root, args.evidence)
        payload = {
            "target_kind": kind, "target_id": identity,
            "previous_summary": previous, "summary": args.summary.strip(),
            "reason": args.reason.strip(), "evidence": evidence,
        }
        _, event = append_event_and_render(root, args.control_dir, "conclusion_corrected", payload)
    print_json({"event_id": event["event_id"], **payload})


def cmd_promote(args: argparse.Namespace) -> None:
    root = project_root(args)
    with exclusive_lock(root, args.control_dir):
        state, _ = load_and_verify(root, args.control_dir)
        candidate = state["candidates"].get(args.candidate_id)
        if not candidate:
            raise WorkflowError(f"Unknown candidate: {args.candidate_id}")
        if candidate["status"] != "passed":
            raise WorkflowError("Only a passed candidate can replace current")
        scope = state["scopes"][candidate["scope_id"]]
        if candidate["base_version_id"] != scope["current_version_id"]:
            raise WorkflowError("Candidate base is no longer current; rebase into a new candidate instead of silently promoting stale work")
        change_types = validate_change_types(candidate["change_types"])
        if not set(change_types) & PROMOTABLE_CHANGE_TYPES:
            raise WorkflowError(
                "Candidate only changes parameters/retries/evaluation/results; keep it as a child experiment instead of consuming a mainline version"
            )
        evidence = parse_evidence(root, args.evidence)
        combined_evidence = candidate["evidence"] + evidence
        if not combined_evidence:
            raise WorkflowError("Promotion requires durable evidence")
        report_reference = candidate.get("acceptance_report", {}).get("source", {}).get("reference", "")
        acceptance = verified_acceptance(root, candidate, report_reference, state)
        prior = candidate.get("acceptance_report")
        if prior and acceptance["source"]["sha256_when_recorded"] != prior["source"]["sha256_when_recorded"]:
            raise WorkflowError("Accepted report changed after conclusion; use a new candidate rather than changing accepted evidence")
        number = scope["next_version_number"]
        new_id = version_id(scope["prefix"], number)
        version = {
            "version_id": new_id,
            "scope_id": candidate["scope_id"],
            "number": number,
            "slug": validate_slug(args.slug, "version slug"),
            "status": "current",
            "parent_version_id": candidate["base_version_id"],
            "promoted_from_candidate_id": candidate["candidate_id"],
            "change_types": change_types,
            "summary": args.summary.strip(),
            "evidence": combined_evidence,
            "legacy_id": None,
            "created_at": now_iso(),
            "acceptance_report": acceptance,
        }
        if not version["summary"]:
            raise WorkflowError("Promoted current truth summary must be non-empty")
        payload = {
            "candidate_id": candidate["candidate_id"],
            "previous_version_id": scope["current_version_id"],
            "version": version,
        }
        _, event = append_event_and_render(root, args.control_dir, "version_promoted", payload)
    print_json({"event_id": event["event_id"], "version": version})


def cmd_rebuild_state(args: argparse.Namespace) -> None:
    root = project_root(args)
    with exclusive_lock(root, args.control_dir):
        _, events = load_and_verify(root, args.control_dir) if not args.force else (None, None)
        if events is None:
            from workflow_core import read_events

            events = read_events(ledger_path(root, args.control_dir))
        state = replay_events(events)
        if args.dry_run:
            print_json(state)
            return
        atomic_write_json(state_path(root, args.control_dir), state)
        render_views(root, args.control_dir, state, overwrite_snapshots=args.force)
    print(f"Rebuilt state and generated views from {len(events)} ledger events")


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", required=True, help="Project root; the controller never discovers or writes another project implicitly")
    parser.add_argument("--control-dir", default=DEFAULT_CONTROL_DIR, help=f"Project-relative control directory (default: {DEFAULT_CONTROL_DIR})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize an append-only project control plane")
    add_common(init)
    init.add_argument("--project-id", required=True)
    init.add_argument("--project-name", required=True)
    init.add_argument("--scope-id", default="project")
    init.add_argument("--scope-kind", choices=sorted(SCOPE_KINDS), default="project")
    init.add_argument("--scope-label", default="项目主线")
    init.add_argument("--scope-purpose", required=True)
    init.add_argument("--prefix", default="P")
    init.add_argument("--initial-version", type=int, default=1)
    init.add_argument("--initial-slug", default="baseline")
    init.add_argument("--initial-summary", required=True)
    init.add_argument("--legacy-id", default="")
    init.add_argument("--initial-evidence", action="append", default=[])
    init.add_argument("--max-active-siblings", type=int, default=DEFAULT_MAX_ACTIVE_SIBLINGS)
    init.add_argument("--max-managed-depth", type=int, default=DEFAULT_MAX_MANAGED_DEPTH)
    init.add_argument("--dry-run", action="store_true")
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status", help="Print materialized project state after ledger verification")
    add_common(status)
    status.set_defaults(func=cmd_status)

    scope = sub.add_parser("add-scope", help="Add a project/workstream/component namespace and baseline")
    add_common(scope)
    scope.add_argument("--scope-id", required=True)
    scope.add_argument("--scope-kind", choices=sorted(SCOPE_KINDS), required=True)
    scope.add_argument("--scope-label", required=True)
    scope.add_argument("--scope-purpose", required=True)
    scope.add_argument("--prefix", required=True)
    scope.add_argument("--parent-scope-id")
    scope.add_argument("--initial-version", type=int, default=1)
    scope.add_argument("--initial-slug", default="baseline")
    scope.add_argument("--initial-summary", required=True)
    scope.add_argument("--legacy-id", default="")
    scope.add_argument("--initial-evidence", action="append", default=[])
    scope.add_argument("--dry-run", action="store_true")
    scope.set_defaults(func=cmd_add_scope)

    legacy = sub.add_parser("record-legacy-version", help="Register an old version as an alias without renaming any existing path")
    add_common(legacy)
    legacy.add_argument("--scope-id", required=True)
    legacy.add_argument("--number", type=int, required=True)
    legacy.add_argument("--legacy-id", required=True)
    legacy.add_argument("--slug", required=True)
    legacy.add_argument("--summary", required=True)
    legacy.add_argument("--parent-version-id")
    legacy.add_argument("--change-type", action="append", choices=sorted(ALL_CHANGE_TYPES), required=True)
    legacy.add_argument("--evidence", action="append", required=True)
    legacy.set_defaults(func=cmd_record_legacy_version)

    layout = sub.add_parser("plan-layout", help="Validate and optionally record where a new folder belongs")
    add_common(layout)
    layout.add_argument("--path", required=True)
    layout.add_argument("--level", choices=sorted(DIRECTORY_LEVELS), required=True)
    layout.add_argument("--parent-directory-id", required=True)
    layout.add_argument("--scope-id")
    layout.add_argument("--candidate-id")
    layout.add_argument("--action", choices=sorted(DIRECTORY_ACTIONS), required=True)
    layout.add_argument("--purpose", required=True)
    layout.add_argument("--reason", required=True)
    layout.add_argument("--alternative", action="append", default=[])
    layout.add_argument("--override-reason", default="")
    layout.add_argument("--record", action="store_true")
    layout.set_defaults(func=cmd_plan_layout)

    directory = sub.add_parser("register-directory", help="Apply a recorded layout decision to an existing or new folder")
    add_common(directory)
    directory.add_argument("--decision-id", required=True)
    directory.add_argument("--create-directory", action="store_true")
    directory.add_argument("--manage-children", action="store_true")
    directory.set_defaults(func=cmd_register_directory)

    directory_status = sub.add_parser("set-directory-status", help="Archive/supersede a directory without deleting history")
    add_common(directory_status)
    directory_status.add_argument("--directory-id", required=True)
    directory_status.add_argument("--status", required=True)
    directory_status.add_argument("--reason", required=True)
    directory_status.set_defaults(func=cmd_set_directory_status)

    suggest_candidate = sub.add_parser("suggest-candidate-id", help="Print the next bounded vN-a identity before planning its directory")
    add_common(suggest_candidate)
    suggest_candidate.add_argument("--scope-id", required=True)
    suggest_candidate.add_argument("--base-version-id")
    suggest_candidate.set_defaults(func=cmd_suggest_candidate_id)

    candidate = sub.add_parser("create-candidate", help="Create the next one-level child experiment under a mainline version")
    add_common(candidate)
    candidate.add_argument("--scope-id", required=True)
    candidate.add_argument("--base-version-id")
    candidate.add_argument("--slug", required=True)
    candidate.add_argument("--hypothesis", required=True)
    candidate.add_argument("--change-type", action="append", choices=sorted(ALL_CHANGE_TYPES), required=True)
    candidate.add_argument("--directory-id", required=True)
    candidate.add_argument("--acceptance-contract", default="", help="Freeze user criteria before execution; required for later passed/promote")
    candidate.set_defaults(func=cmd_create_candidate)

    suggest_run = sub.add_parser("suggest-run-id", help="Print the next stable run_id before planning its directory")
    add_common(suggest_run)
    suggest_run.add_argument("--variant", required=True)
    suggest_run.set_defaults(func=cmd_suggest_run_id)

    run = sub.add_parser("register-run", help="Register a retry/seed/parameter execution with a run_id, never another version suffix")
    add_common(run)
    run.add_argument("--candidate-id", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--variant", required=True)
    run.add_argument("--directory-id", required=True)
    run.add_argument("--config-identity", required=True)
    run.add_argument("--code-identity", required=True)
    run.add_argument("--data-identity", required=True)
    run.set_defaults(func=cmd_register_run)

    rename_run = sub.add_parser("rename-run", help="Append a corrective event that renames an active run and its directory")
    add_common(rename_run)
    rename_run.add_argument("--run-id", required=True)
    rename_run.add_argument("--new-run-id", required=True)
    rename_run.add_argument("--new-variant", required=True)
    rename_run.add_argument("--reason", required=True)
    rename_run.set_defaults(func=cmd_rename_run)

    run_status = sub.add_parser("set-run-status", help="Update run status with durable evidence for terminal states")
    add_common(run_status)
    run_status.add_argument("--run-id", required=True)
    run_status.add_argument("--status", choices=sorted(RUN_STATUSES), required=True)
    run_status.add_argument("--summary", default="")
    run_status.add_argument("--evidence", action="append", default=[])
    run_status.set_defaults(func=cmd_set_run_status)

    conclude = sub.add_parser("conclude-candidate", help="Persist a passed/failed/abandoned child experiment conclusion")
    add_common(conclude)
    conclude.add_argument("--candidate-id", required=True)
    conclude.add_argument("--status", choices=["passed", "failed", "abandoned"], required=True)
    conclude.add_argument("--summary", required=True)
    conclude.add_argument("--evidence", action="append", required=True)
    conclude.add_argument("--acceptance-report", default="", help="Structured criterion checks, required for passed")
    conclude.set_defaults(func=cmd_conclude_candidate)

    correction = sub.add_parser("correct-conclusion", help="Append an evidence-backed correction to a terminal candidate or run")
    add_common(correction)
    target = correction.add_mutually_exclusive_group(required=True)
    target.add_argument("--candidate-id")
    target.add_argument("--run-id")
    correction.add_argument("--summary", required=True)
    correction.add_argument("--reason", required=True)
    correction.add_argument("--evidence", action="append", required=True)
    correction.set_defaults(func=cmd_correct_conclusion)

    promote = sub.add_parser("promote", help="Promote a passed structural/contract candidate to the next mainline version")
    add_common(promote)
    promote.add_argument("--candidate-id", required=True)
    promote.add_argument("--slug", required=True)
    promote.add_argument("--summary", required=True)
    promote.add_argument("--evidence", action="append", default=[])
    promote.set_defaults(func=cmd_promote)

    artifacts = sub.add_parser("record-artifact-review", help="Mark terminal run artifacts for later review; never delete")
    add_common(artifacts)
    artifacts.add_argument("--run-id", required=True)
    artifacts.add_argument("--review-file", required=True, help="Project-relative immutable JSON review")
    artifacts.set_defaults(func=cmd_record_artifact_review)

    rebuild = sub.add_parser("rebuild-state", help="Rebuild materialized state and views from the append-only ledger")
    add_common(rebuild)
    rebuild.add_argument("--dry-run", action="store_true")
    rebuild.add_argument("--force", action="store_true", help="Allow recovery when state.json is stale; ledger integrity is still mandatory")
    rebuild.set_defaults(func=cmd_rebuild_state)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
