#!/usr/bin/env python3
"""Core ledger, policy, and rendering functions for fjn-project-workflow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from acceptance_contract import validate_acceptance_report, validate_contract


SCHEMA_VERSION = 1
DEFAULT_CONTROL_DIR = "docs/project-control"
DEFAULT_MAX_ACTIVE_SIBLINGS = 6
DEFAULT_MAX_MANAGED_DEPTH = 8
SCOPE_KINDS = {"project", "workstream", "component"}
DIRECTORY_LEVELS = {
    "project",
    "area",
    "workstream",
    "experiment_family",
    "candidate",
    "run",
    "artifact",
    "archive",
}
DIRECTORY_ACTIONS = {
    "reuse",
    "new_child",
    "new_group",
    "local_restructure",
    "broad_restructure",
}
CANDIDATE_STATUSES = {"planned", "running", "passed", "failed", "abandoned", "promoted"}
RUN_STATUSES = {"planned", "running", "completed", "failed", "cancelled"}
PROMOTABLE_CHANGE_TYPES = {
    "code_architecture",
    "data_contract",
    "workflow_contract",
    "business_goal",
    "delivery_contract",
    "validated_default_change",
}
ALL_CHANGE_TYPES = PROMOTABLE_CHANGE_TYPES | {
    "parameter_only",
    "seed_or_retry",
    "smoke_only",
    "evaluation_only",
    "result_only",
}
ALLOWED_CHILD_LEVELS = {
    "project": {"area", "workstream", "archive"},
    "area": {"area", "workstream", "experiment_family", "archive"},
    "workstream": {"area", "experiment_family", "archive"},
    "experiment_family": {"experiment_family", "candidate", "archive"},
    "candidate": {"run", "archive"},
    "run": {"artifact", "archive"},
    "artifact": {"artifact", "archive"},
    "archive": {"archive"},
}
VERSION_RE = re.compile(r"^(?P<prefix>[A-Z][A-Z0-9]{0,11})-v(?P<number>[1-9]\d*)$")
CANDIDATE_RE = re.compile(r"^(?P<version>[A-Z][A-Z0-9]{0,11}-v[1-9]\d*)-(?P<letter>[a-z])$")
VERSION_TOKEN_RE = re.compile(r"(?:^|[-_])(?:[A-Z][A-Z0-9]{0,11}-)?[vV]\d+(?=$|[-_])")
AMBIGUOUS_NAME_RE = re.compile(r"(?i)(?:^|[-_])(final\d*|latest|new|newer|best-new)(?:$|[-_])")


class WorkflowError(RuntimeError):
    """A deterministic workflow policy or consistency error."""


class AuditReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def passed(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "errors": self.errors, "warnings": self.warnings}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_relative_path(value: str, *, allow_dot: bool = False) -> str:
    path = Path(value)
    if path.is_absolute():
        raise WorkflowError(f"Path must be project-relative: {value}")
    normalized = Path(os.path.normpath(value)).as_posix()
    if normalized == "." and allow_dot:
        return normalized
    if normalized in {"", "."} or normalized == ".." or normalized.startswith("../"):
        raise WorkflowError(f"Path escapes or does not identify a project child: {value}")
    return normalized


def project_path(project_root: Path, relative_path: str) -> Path:
    root = project_root.resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WorkflowError(f"Path escapes project root: {relative_path}") from exc
    return path


def control_path(project_root: Path, control_dir: str = DEFAULT_CONTROL_DIR) -> Path:
    relative = ensure_relative_path(control_dir)
    return project_path(project_root, relative)


def state_path(project_root: Path, control_dir: str = DEFAULT_CONTROL_DIR) -> Path:
    return control_path(project_root, control_dir) / "state.json"


def ledger_path(project_root: Path, control_dir: str = DEFAULT_CONTROL_DIR) -> Path:
    return control_path(project_root, control_dir) / "events.jsonl"


def lock_path(project_root: Path, control_dir: str = DEFAULT_CONTROL_DIR) -> Path:
    return control_path(project_root, control_dir) / ".write.lock"


@contextmanager
def exclusive_lock(project_root: Path, control_dir: str = DEFAULT_CONTROL_DIR) -> Iterable[None]:
    path = lock_path(project_root, control_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise WorkflowError(
            f"Another workflow write may be active: {path}. Remove the lock only after confirming no writer is running."
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()} created_at={now_iso()}\n")
        yield
    finally:
        path.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"Expected a JSON object in {path}")
    return value


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(payload) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def make_event(event_type: str, payload: dict[str, Any], previous_hash: str | None, sequence: int) -> dict[str, Any]:
    event = {
        "schema_version": SCHEMA_VERSION,
        "sequence": sequence,
        "event_id": f"evt-{sequence:06d}",
        "event_type": event_type,
        "recorded_at": now_iso(),
        "previous_hash": previous_hash,
        "payload": payload,
    }
    event["event_hash"] = sha256_text(canonical_json(event))
    return event


def read_events(path: Path, report: AuditReport | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        if report is not None:
            report.error(f"Missing append-only ledger: {path}")
            return events
        raise WorkflowError(f"Missing append-only ledger: {path}")
    previous_hash: str | None = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            message = f"Invalid ledger JSON at line {line_number}: {exc}"
            if report is not None:
                report.error(message)
                continue
            raise WorkflowError(message) from exc
        if not isinstance(event, dict):
            message = f"Ledger line {line_number} is not an object"
            if report is not None:
                report.error(message)
                continue
            raise WorkflowError(message)
        supplied_hash = event.get("event_hash")
        hash_input = dict(event)
        hash_input.pop("event_hash", None)
        expected_hash = sha256_text(canonical_json(hash_input))
        expected_sequence = len(events) + 1
        errors = []
        if event.get("sequence") != expected_sequence:
            errors.append(f"sequence is {event.get('sequence')}, expected {expected_sequence}")
        if event.get("previous_hash") != previous_hash:
            errors.append("previous_hash does not match ledger head")
        if supplied_hash != expected_hash:
            errors.append("event_hash is invalid")
        if errors:
            message = f"Ledger integrity failure at line {line_number}: {'; '.join(errors)}"
            if report is not None:
                report.error(message)
            else:
                raise WorkflowError(message)
        events.append(event)
        previous_hash = supplied_hash
    return events


def _base_state(initial: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    state = deepcopy(initial)
    state["ledger"] = {"event_count": 0, "head_hash": None}
    state["updated_at"] = event["recorded_at"]
    return state


def apply_event(state: dict[str, Any] | None, event: dict[str, Any]) -> dict[str, Any]:
    event_type = event["event_type"]
    payload = event["payload"]
    if event_type == "project_initialized":
        if state is not None:
            raise WorkflowError("project_initialized must be the first event")
        state = _base_state(payload["initial_state"], event)
    elif state is None:
        raise WorkflowError(f"First ledger event is not project_initialized: {event_type}")
    elif event_type == "scope_added":
        scope = deepcopy(payload["scope"])
        state["scopes"][scope["scope_id"]] = scope
    elif event_type == "scope_bootstrapped":
        scope = deepcopy(payload["scope"])
        version = deepcopy(payload["version"])
        scope["current_version_id"] = version["version_id"]
        scope["next_version_number"] = version["number"] + 1
        scope["version_ids"].append(version["version_id"])
        state["scopes"][scope["scope_id"]] = scope
        state["versions"][version["version_id"]] = version
    elif event_type == "version_bootstrapped":
        version = deepcopy(payload["version"])
        state["versions"][version["version_id"]] = version
        scope = state["scopes"][version["scope_id"]]
        scope["current_version_id"] = version["version_id"]
        scope["next_version_number"] = version["number"] + 1
        scope["version_ids"].append(version["version_id"])
    elif event_type == "legacy_version_recorded":
        version = deepcopy(payload["version"])
        state["versions"][version["version_id"]] = version
        scope = state["scopes"][version["scope_id"]]
        scope["version_ids"].append(version["version_id"])
        scope["next_version_number"] = max(scope["next_version_number"], version["number"] + 1)
    elif event_type == "layout_decision_recorded":
        decision = deepcopy(payload["decision"])
        state["layout_decisions"][decision["decision_id"]] = decision
    elif event_type == "layout_reuse_applied":
        decision = state["layout_decisions"][payload["decision_id"]]
        decision["status"] = "applied"
        decision["applied_directory_id"] = payload["directory_id"]
    elif event_type == "directory_registered":
        directory = deepcopy(payload["directory"])
        state["directories"][directory["directory_id"]] = directory
        decision = state["layout_decisions"][directory["decision_id"]]
        decision["status"] = "applied"
        decision["applied_directory_id"] = directory["directory_id"]
    elif event_type == "directory_status_changed":
        directory = state["directories"][payload["directory_id"]]
        directory["status"] = payload["status"]
        directory["status_reason"] = payload["reason"]
        directory["updated_at"] = event["recorded_at"]
    elif event_type == "candidate_created":
        candidate = deepcopy(payload["candidate"])
        state["candidates"][candidate["candidate_id"]] = candidate
        state["scopes"][candidate["scope_id"]]["candidate_ids"].append(candidate["candidate_id"])
    elif event_type == "run_registered":
        run = deepcopy(payload["run"])
        state["runs"][run["run_id"]] = run
        state["candidates"][run["candidate_id"]]["run_ids"].append(run["run_id"])
    elif event_type == "run_renamed":
        old_run_id = payload["old_run_id"]
        new_run_id = payload["new_run_id"]
        run = state["runs"].pop(old_run_id)
        run["run_id"] = new_run_id
        run["variant"] = payload["new_variant"]
        run["rename_reason"] = payload["reason"]
        run["updated_at"] = event["recorded_at"]
        state["runs"][new_run_id] = run
        candidate_run_ids = state["candidates"][run["candidate_id"]]["run_ids"]
        candidate_run_ids[candidate_run_ids.index(old_run_id)] = new_run_id
        directory = state["directories"][run["directory_id"]]
        directory["path"] = payload["new_directory_path"]
        directory["updated_at"] = event["recorded_at"]
        decision = state["layout_decisions"][directory["decision_id"]]
        decision["path"] = payload["new_directory_path"]
    elif event_type == "run_status_changed":
        run = state["runs"][payload["run_id"]]
        run["status"] = payload["status"]
        run["summary"] = payload["summary"]
        run["evidence"].extend(deepcopy(payload["evidence"]))
        run["updated_at"] = event["recorded_at"]
    elif event_type == "artifact_review_recorded":
        state["runs"][payload["run_id"]]["artifact_review"] = deepcopy(payload["artifact_review"])
    elif event_type == "candidate_concluded":
        candidate = state["candidates"][payload["candidate_id"]]
        candidate["status"] = payload["status"]
        candidate["conclusion"] = payload["summary"]
        candidate["evidence"].extend(deepcopy(payload["evidence"]))
        candidate["updated_at"] = event["recorded_at"]
        if "acceptance_report" in payload:
            candidate["acceptance_report"] = deepcopy(payload["acceptance_report"])
    elif event_type == "conclusion_corrected":
        collection = "candidates" if payload["target_kind"] == "candidate" else "runs"
        record = state[collection][payload["target_id"]]
        field = "conclusion" if collection == "candidates" else "summary"
        if record.get(field) != payload["previous_summary"]:
            raise WorkflowError("Correction does not match the prior recorded conclusion")
        record.setdefault("conclusion_corrections", []).append({
            **deepcopy(payload), "recorded_at": event["recorded_at"],
        })
        record[field] = payload["summary"]
        record["evidence"].extend(deepcopy(payload["evidence"]))
        record["updated_at"] = event["recorded_at"]
    elif event_type == "version_promoted":
        previous = state["versions"][payload["previous_version_id"]]
        previous["status"] = "superseded"
        previous["superseded_at"] = event["recorded_at"]
        candidate = state["candidates"][payload["candidate_id"]]
        candidate["status"] = "promoted"
        candidate["promoted_to_version_id"] = payload["version"]["version_id"]
        candidate["updated_at"] = event["recorded_at"]
        version = deepcopy(payload["version"])
        state["versions"][version["version_id"]] = version
        scope = state["scopes"][version["scope_id"]]
        scope["current_version_id"] = version["version_id"]
        scope["next_version_number"] = version["number"] + 1
        scope["version_ids"].append(version["version_id"])
    else:
        raise WorkflowError(f"Unknown event type: {event_type}")
    state["updated_at"] = event["recorded_at"]
    state["ledger"] = {"event_count": event["sequence"], "head_hash": event["event_hash"]}
    return state


def replay_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] | None = None
    for event in events:
        state = apply_event(state, event)
    if state is None:
        raise WorkflowError("Ledger is empty")
    return state


def load_and_verify(project_root: Path, control_dir: str = DEFAULT_CONTROL_DIR) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = read_json(state_path(project_root, control_dir))
    events = read_events(ledger_path(project_root, control_dir))
    replayed = replay_events(events)
    if state != replayed:
        raise WorkflowError("state.json does not match a replay of events.jsonl; run rebuild-state after auditing the ledger")
    return state, events


def append_event_and_render(
    project_root: Path,
    control_dir: str,
    event_type: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    state, events = load_and_verify(project_root, control_dir)
    event = make_event(event_type, payload, state["ledger"]["head_hash"], len(events) + 1)
    next_state = apply_event(deepcopy(state), event)
    render_current(next_state)
    render_version_ledger(next_state)
    render_directory_map(next_state)
    for version in next_state["versions"].values():
        render_version_snapshot(next_state, version)
    append_jsonl(ledger_path(project_root, control_dir), event)
    atomic_write_json(state_path(project_root, control_dir), next_state)
    render_views(project_root, control_dir, next_state)
    return next_state, event


def next_id(prefix: str, existing: Iterable[str]) -> str:
    maximum = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for value in existing:
        match = pattern.match(value)
        if match:
            maximum = max(maximum, int(match.group(1)))
    return f"{prefix}-{maximum + 1:04d}"


def version_id(prefix: str, number: int) -> str:
    return f"{prefix}-v{number}"


def candidate_id_for(state: dict[str, Any], base_version_id: str) -> str:
    used = {
        match.group("letter")
        for value in state["candidates"]
        if (match := CANDIDATE_RE.match(value)) and match.group("version") == base_version_id
    }
    for code in range(ord("a"), ord("z") + 1):
        letter = chr(code)
        if letter not in used:
            return f"{base_version_id}-{letter}"
    raise WorkflowError(f"Candidate suffix space exhausted for {base_version_id}; create a new semantic scope or consolidate candidates")


def parse_evidence(project_root: Path, specifications: Iterable[str]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for specification in specifications:
        if "::" not in specification:
            raise WorkflowError("Evidence must use 'reference::claim' so the durable ledger preserves what the source proves")
        reference, claim = (part.strip() for part in specification.split("::", 1))
        if not reference or not claim:
            raise WorkflowError("Evidence reference and claim must both be non-empty")
        entry: dict[str, Any] = {
            "reference": reference,
            "claim": claim,
            "recorded_at": now_iso(),
            "kind": "external",
            "exists_when_recorded": None,
            "sha256_when_recorded": None,
            "size_when_recorded": None,
            "mtime_ns_when_recorded": None,
        }
        parsed = urlparse(reference)
        if parsed.scheme in {"http", "https"} or reference.startswith(("user:", "external:")):
            evidence.append(entry)
            continue
        path = Path(reference)
        if not path.is_absolute():
            path = project_path(project_root, ensure_relative_path(reference, allow_dot=True))
            entry["reference"] = path.relative_to(project_root.resolve()).as_posix()
        else:
            path = path.resolve()
        if not path.exists():
            raise WorkflowError(f"Local evidence does not exist: {path}")
        entry["kind"] = "local_file" if path.is_file() else "local_directory"
        entry["exists_when_recorded"] = True
        if path.is_file():
            stat = path.stat()
            entry["size_when_recorded"] = stat.st_size
            entry["mtime_ns_when_recorded"] = stat.st_mtime_ns
            if stat.st_size <= 10 * 1024 * 1024:
                entry["sha256_when_recorded"] = sha256_file(path)
        evidence.append(entry)
    return evidence


def acceptance_snapshot_errors(project_root: Path, acceptance: dict[str, Any]) -> list[str]:
    """Accepted evidence is a hard gate, unlike ordinary historical ledger warnings."""
    sources = acceptance.get("evidence_snapshots")
    if not isinstance(sources, list) or not sources:
        return ["acceptance has no reviewed-evidence snapshots; re-audit in a new candidate"]
    errors: list[str] = []
    for source in sources:
        path = Path(source["reference"])
        if not path.is_absolute():
            path = project_root / path
        if not path.is_file():
            errors.append(f"accepted evidence missing: {source['reference']}")
            continue
        expected_hash = source.get("sha256_when_recorded")
        if expected_hash:
            changed = sha256_file(path) != expected_hash
        else:
            stat = path.stat()
            changed = stat.st_size != source.get("size_when_recorded") or stat.st_mtime_ns != source.get("mtime_ns_when_recorded")
        if changed:
            errors.append(f"accepted evidence changed: {source['reference']}")
    return errors


def validate_change_types(change_types: Iterable[str]) -> list[str]:
    values = sorted(set(change_types))
    if not values:
        raise WorkflowError("At least one change type is required")
    unknown = set(values) - ALL_CHANGE_TYPES
    if unknown:
        raise WorkflowError(f"Unknown change types: {', '.join(sorted(unknown))}")
    return values


def validate_directory_proposal(
    state: dict[str, Any],
    relative_path: str,
    level: str,
    parent_directory_id: str,
    action: str,
    override_reason: str = "",
) -> dict[str, Any]:
    report = AuditReport()
    path = ensure_relative_path(relative_path)
    if level not in DIRECTORY_LEVELS:
        report.error(f"Unknown directory level: {level}")
    if action not in DIRECTORY_ACTIONS:
        report.error(f"Unknown layout action: {action}")
    if action == "new_group" and level not in {"area", "workstream", "experiment_family"}:
        report.error("new_group must introduce a semantic area, workstream, or experiment_family level")
    parent = state["directories"].get(parent_directory_id)
    if parent is None:
        report.error(f"Unknown parent directory: {parent_directory_id}")
        return {
            **report.as_dict(),
            "normalized_path": path,
            "active_sibling_count": 0,
            "recommendation": "register a valid parent first",
        }
    parent_path = Path(parent["path"])
    candidate_path = Path(path)
    expected_parent = Path(".") if candidate_path.parent == Path("") else candidate_path.parent
    if expected_parent != parent_path:
        report.error(f"New managed directories must be direct children of '{parent['path']}'; register intermediate semantic folders first")
    if level not in ALLOWED_CHILD_LEVELS.get(parent["level"], set()):
        report.error(f"Directory level '{level}' is not allowed below '{parent['level']}'")
    existing = next((entry for entry in state["directories"].values() if entry["path"] == path), None)
    if action == "reuse" and existing is None:
        report.error(f"Reuse action requires an existing registered directory: {path}")
    elif action == "reuse" and existing is not None:
        if existing.get("parent_directory_id") != parent_directory_id or existing.get("level") != level:
            report.error("Reused directory must keep its registered parent and semantic level")
        if existing.get("status") != "active":
            report.error(f"Only an active directory can be reused: {path}")
    elif existing is not None:
        report.error(f"Directory path is already registered: {path}")
    depth = len(candidate_path.parts)
    if depth > state["config"]["max_managed_depth"]:
        report.error(f"Managed path depth {depth} exceeds configured maximum {state['config']['max_managed_depth']}")
    basename = candidate_path.name
    version_tokens = VERSION_TOKEN_RE.findall(basename)
    if len(version_tokens) > 1:
        report.error("Directory basename contains stacked version tokens; keep one candidate identity and move run details into run metadata")
    if AMBIGUOUS_NAME_RE.search(basename):
        report.error("Directory basename uses ambiguous final/latest/new naming; use a stable semantic name or run_id")
    if level == "run" and VERSION_TOKEN_RE.search(basename):
        report.error("Run directories must use run_id/variant identity, not another version token")
    governed_levels = {"experiment_family", "candidate"}
    active_siblings = [
        entry
        for entry in state["directories"].values()
        if entry.get("parent_directory_id") == parent_directory_id
        and entry.get("status") == "active"
        and entry.get("level") == level
    ]
    threshold = state["config"]["max_active_siblings"]
    if (
        level in governed_levels
        and len(active_siblings) >= threshold
        and action != "reuse"
    ):
        message = (
            f"Parent already has {len(active_siblings)} active managed children (limit {threshold}); "
            "create a semantic group/restructure, or provide an audited override reason"
        )
        if override_reason.strip():
            report.warn(f"OVERRIDE: {message} Reason: {override_reason.strip()}")
        else:
            report.error(message)
    recommendation = "register as a direct child"
    if level in governed_levels and len(active_siblings) >= threshold:
        recommendation = "introduce a semantic grouping level or record a local/broad restructure before adding more experiments"
    elif action == "reuse":
        recommendation = "reuse an existing registered directory; do not create or register a duplicate"
    return {
        **report.as_dict(),
        "normalized_path": path,
        "active_sibling_count": len(active_siblings),
        "recommendation": recommendation,
    }


def audit_state(project_root: Path, control_dir: str = DEFAULT_CONTROL_DIR, check_filesystem: bool = True) -> AuditReport:
    report = AuditReport()
    events = read_events(ledger_path(project_root, control_dir), report)
    if report.errors:
        return report
    try:
        replayed = replay_events(events)
        state = read_json(state_path(project_root, control_dir))
    except WorkflowError as exc:
        report.error(str(exc))
        return report
    if state != replayed:
        report.error("state.json differs from ledger replay")
    if state.get("schema_version") != SCHEMA_VERSION:
        report.error(f"Unsupported state schema_version: {state.get('schema_version')}")
    for scope_id, scope in state.get("scopes", {}).items():
        prefix = scope.get("prefix", "")
        if not re.fullmatch(r"[A-Z][A-Z0-9]{0,11}", prefix):
            report.error(f"Scope {scope_id} has invalid prefix: {prefix}")
        current_id = scope.get("current_version_id")
        if current_id:
            current = state["versions"].get(current_id)
            if not current:
                report.error(f"Scope {scope_id} current version is missing: {current_id}")
            elif current.get("status") != "current":
                report.error(f"Scope {scope_id} current version is not marked current: {current_id}")
        current_versions = [
            item for item in state["versions"].values() if item.get("scope_id") == scope_id and item.get("status") == "current"
        ]
        if len(current_versions) > 1:
            report.error(f"Scope {scope_id} has multiple current versions")
    for version_key, version in state.get("versions", {}).items():
        match = VERSION_RE.fullmatch(version_key)
        if not match:
            report.error(f"Version ID violates bounded naming policy: {version_key}")
        elif int(match.group("number")) != version.get("number"):
            report.error(f"Version number and ID disagree: {version_key}")
        parent = version.get("parent_version_id")
        if parent and parent not in state["versions"]:
            report.error(f"Version {version_key} has missing parent {parent}")
        if parent and not version.get("evidence"):
            report.error(f"Version relation {parent} -> {version_key} lacks evidence")
        acceptance = version.get("acceptance_report")
        if acceptance:
            for error in acceptance_snapshot_errors(project_root, acceptance):
                report.error(f"Version {version_key}: {error}")
            source = acceptance.get("source", {})
            path = Path(source.get("reference", ""))
            if not path.is_absolute():
                path = project_root / path
            if not path.is_file() or sha256_file(path) != source.get("sha256_when_recorded"):
                report.error(f"Version {version_key} acceptance report missing/changed")
            candidate = state["candidates"].get(version.get("promoted_from_candidate_id"), {})
            completed_runs = {run_id for run_id in candidate.get("run_ids", []) if state["runs"].get(run_id, {}).get("status") == "completed"}
            for error in validate_acceptance_report(acceptance.get("content"), project_root, candidate.get("candidate_id", ""), completed_runs, candidate.get("acceptance_contract", {}).get("content")):
                report.error(f"Version {version_key} acceptance: {error}")
    for candidate_key, candidate in state.get("candidates", {}).items():
        if not CANDIDATE_RE.fullmatch(candidate_key):
            report.error(f"Candidate ID violates one-level suffix policy: {candidate_key}")
        if candidate.get("base_version_id") not in state["versions"]:
            report.error(f"Candidate {candidate_key} has unknown base version")
        directory = state.get("directories", {}).get(candidate.get("directory_id"))
        if not directory:
            report.error(f"Candidate {candidate_key} has unknown directory_id")
        elif directory.get("level") != "candidate":
            report.error(f"Candidate {candidate_key} directory is not level=candidate")
        elif Path(directory["path"]).name != candidate_key:
            report.error(f"Candidate {candidate_key} directory basename does not match its identity")
        if candidate.get("status") in {"passed", "failed", "abandoned", "promoted"} and not candidate.get("evidence"):
            report.error(f"Concluded candidate {candidate_key} has no durable evidence")
        acceptance = candidate.get("acceptance_report")
        if acceptance:
            for error in acceptance_snapshot_errors(project_root, acceptance):
                report.error(f"Candidate {candidate_key}: {error}")
            contract = candidate.get("acceptance_contract", {}).get("content")
            if contract is None:
                report.error(f"Candidate {candidate_key} acceptance lacks pre-registered contract")
            completed_runs = {run_id for run_id in candidate.get("run_ids", []) if state["runs"].get(run_id, {}).get("status") == "completed"}
            for error in validate_acceptance_report(acceptance.get("content"), project_root, candidate_key, completed_runs, contract):
                report.error(f"Candidate {candidate_key} acceptance: {error}")
            source = acceptance.get("source", {})
            path = Path(source.get("reference", ""))
            if not path.is_absolute():
                path = project_root / path
            if not path.is_file() or sha256_file(path) != source.get("sha256_when_recorded"):
                report.error(f"Candidate {candidate_key} acceptance report missing/changed; re-audit required")
        contract_record = candidate.get("acceptance_contract")
        if contract_record:
            for error in validate_contract(contract_record.get("content")):
                report.error(f"Candidate {candidate_key} contract: {error}")
            source = contract_record.get("source", {})
            path = Path(source.get("reference", ""))
            if not path.is_absolute():
                path = project_root / path
            if not path.is_file() or sha256_file(path) != source.get("sha256_when_recorded"):
                report.error(f"Candidate {candidate_key} pre-registered contract missing/changed")
    paths: dict[str, str] = {}
    for directory_id, directory in state.get("directories", {}).items():
        path = directory.get("path", "")
        if path in paths:
            report.error(f"Directories {paths[path]} and {directory_id} register the same path: {path}")
        paths[path] = directory_id
        parent_id = directory.get("parent_directory_id")
        if parent_id:
            parent = state["directories"].get(parent_id)
            if not parent:
                report.error(f"Directory {directory_id} has unknown parent {parent_id}")
            elif (Path(".") if Path(path).parent == Path("") else Path(path).parent) != Path(parent["path"]):
                report.error(f"Directory {directory_id} is not a direct child of registered parent {parent_id}")
        if not str(directory.get("purpose", "")).strip():
            report.error(f"Directory {directory_id} has no purpose")
        if check_filesystem and directory.get("status") == "active":
            absolute = project_path(project_root, path)
            if not absolute.exists():
                report.warn(f"Active registered directory is missing on disk: {path}")
        if check_filesystem and directory.get("manage_children") and directory.get("status") == "active":
            absolute = project_path(project_root, path)
            if absolute.is_dir():
                registered_children = {
                    Path(item["path"]).name
                    for item in state["directories"].values()
                    if item.get("parent_directory_id") == directory_id and item.get("status") == "active"
                }
                unregistered = sorted(child.name for child in absolute.iterdir() if child.is_dir() and child.name not in registered_children)
                if unregistered:
                    report.warn(
                        f"Managed directory {path} has unregistered child folders: {', '.join(unregistered[:12])}"
                    )
    for run_id, run in state.get("runs", {}).items():
        if not re.fullmatch(r"run-\d{8}T\d{6}Z-[a-z0-9][a-z0-9-]{0,47}(?:-\d+)?", run_id):
            report.error(f"Run ID violates run naming policy: {run_id}")
        if run.get("candidate_id") not in state["candidates"]:
            report.error(f"Run {run_id} has unknown candidate")
            continue
        directory = state.get("directories", {}).get(run.get("directory_id"))
        if not directory:
            report.error(f"Run {run_id} has unknown directory_id")
            continue
        if directory.get("level") != "run":
            report.error(f"Run {run_id} directory is not level=run")
        if Path(directory["path"]).name != run_id:
            report.error(f"Run {run_id} directory basename does not match run_id")
        candidate_directory_id = state["candidates"][run["candidate_id"]].get("directory_id")
        if directory.get("parent_directory_id") != candidate_directory_id:
            report.error(f"Run {run_id} directory is not directly below its candidate directory")
    evidence_owners: list[tuple[str, dict[str, Any]]] = []
    for collection_name in ["versions", "candidates", "runs"]:
        for identity, record in state.get(collection_name, {}).items():
            for evidence in record.get("evidence", []):
                evidence_owners.append((identity, evidence))
    for owner, evidence in evidence_owners:
        if evidence.get("kind") not in {"local_file", "local_directory"}:
            continue
        reference = str(evidence.get("reference", ""))
        path = Path(reference)
        if not path.is_absolute():
            path = project_path(project_root, reference)
        if not path.exists():
            report.warn(
                f"Evidence source for {owner} is no longer present: {reference}; the ledger still preserves its claim and recorded hash"
            )
            continue
        expected_hash = evidence.get("sha256_when_recorded")
        if expected_hash and path.is_file() and sha256_file(path) != expected_hash:
            report.warn(f"Evidence file for {owner} changed after it was recorded: {reference}")
        elif path.is_file() and not expected_hash:
            stat = path.stat()
            if (
                evidence.get("size_when_recorded") != stat.st_size
                or evidence.get("mtime_ns_when_recorded") != stat.st_mtime_ns
            ):
                report.warn(f"Large evidence file metadata for {owner} changed after it was recorded: {reference}")
    for decision_id, decision in state.get("layout_decisions", {}).items():
        if decision.get("status") == "planned":
            report.warn(f"Layout decision has not been applied: {decision_id}")
    root = control_path(project_root, control_dir)
    expected_views = {
        root / "CURRENT.md": render_current(state),
        root / "VERSION_LEDGER.md": render_version_ledger(state),
        root / "DIRECTORY_MAP.md": render_directory_map(state),
    }
    if any(r.get("artifact_review_required") or r.get("artifact_review") for r in state.get("runs", {}).values()):
        from artifact_review import render_artifact_reviews
        expected_views[root / "ARTIFACT_REVIEW.md"] = render_artifact_reviews(state)
    for run_id, run in state.get("runs", {}).items():
        if run.get("status") in {"completed", "failed", "cancelled"} and run.get("artifact_review_required") and not run.get("artifact_review"):
            report.warn(f"Terminal run needs artifact review: {run_id}")
        record = run.get("artifact_review")
        if record and check_filesystem:
            source = project_root / record["reference"]
            if not source.is_file() or sha256_file(source) != record["sha256"]:
                report.error(f"Artifact review missing/changed for {run_id}; append a new review instead")
    for path, expected in expected_views.items():
        if not path.exists():
            report.error(f"Missing generated control view: {path}")
        elif path.read_text(encoding="utf-8") != expected:
            report.error(f"Generated control view is stale or manually edited: {path}")
    for version in state.get("versions", {}).values():
        path = root / "versions" / f"{version['version_id']}.md"
        expected = render_version_snapshot(state, version)
        if not path.exists():
            report.error(f"Missing immutable version snapshot: {path}")
        elif path.read_text(encoding="utf-8") != expected:
            report.error(f"Immutable version snapshot was modified: {path}")
    return report


def markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def evidence_summary(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "—"
    return "; ".join(f"{item['reference']}：{item['claim']}" for item in entries)


def render_version_ledger(state: dict[str, Any]) -> str:
    lines = [
        "# 项目版本总账",
        "",
        "> 本文件由 `fjn-project-workflow` 根据不可追加覆盖的事件账本生成；请勿手改。",
        "",
        f"更新时间：{state['updated_at']}",
        "",
    ]
    for scope in state["scopes"].values():
        lines.extend(
            [
                f"## {scope['label']}（{scope['scope_id']}）",
                "",
                f"作用域类型：`{scope['kind']}`  ",
                f"当前版本：`{scope.get('current_version_id') or '尚未建立'}`",
                "",
                "### 主线版本",
                "",
                "| 版本 | 日期 | 状态 | 父版本 | 来源候选 | 变更类型 | 摘要 | 证据 |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        versions = sorted(
            (state["versions"][key] for key in scope["version_ids"]),
            key=lambda item: item["number"],
        )
        for version in versions:
            lines.append(
                "| {version_id} | {date} | {status} | {parent} | {candidate} | {types} | {summary} | {evidence} |".format(
                    version_id=version["version_id"],
                    date=version["created_at"],
                    status=version["status"],
                    parent=version.get("parent_version_id") or "—",
                    candidate=version.get("promoted_from_candidate_id") or "—",
                    types=", ".join(version.get("change_types", [])) or "—",
                    summary=markdown_escape(version["summary"]),
                    evidence=markdown_escape(evidence_summary(version.get("evidence", []))),
                )
            )
        lines.extend(
            [
                "",
                "### 子实验候选",
                "",
                "| 候选 | 基线 | 状态 | 假设 | 结论 | 运行数 | 证据 |",
                "|---|---|---|---|---|---:|---|",
            ]
        )
        candidates = [state["candidates"][key] for key in scope["candidate_ids"]]
        for candidate in candidates:
            lines.append(
                "| {candidate_id} | {base} | {status} | {hypothesis} | {conclusion} | {runs} | {evidence} |".format(
                    candidate_id=candidate["candidate_id"],
                    base=candidate["base_version_id"],
                    status=candidate["status"],
                    hypothesis=markdown_escape(candidate["hypothesis"]),
                    conclusion=markdown_escape(candidate.get("conclusion") or "—"),
                    runs=len(candidate.get("run_ids", [])),
                    evidence=markdown_escape(evidence_summary(candidate.get("evidence", []))),
                )
            )
        lines.append("")
    lines.extend(
        [
            "## 血缘解释",
            "",
            "仅当事件账本中同时保存父版本、晋级候选和证据时，才生成承接关系。没有证据的旧关系应登记为未知，不得推断连线。",
            "",
        ]
    )
    return "\n".join(lines)


def render_current(state: dict[str, Any]) -> str:
    lines = [
        "# 当前项目控制面",
        "",
        "> 由机器状态生成，只展示当前版本与仍活跃的候选；完整历史见 `VERSION_LEDGER.md`。",
        "",
        f"项目：{state['project']['name']}（`{state['project']['project_id']}`）  ",
        f"更新时间：{state['updated_at']}",
        "",
    ]
    active_statuses = {"planned", "running", "passed"}
    for scope in state["scopes"].values():
        lines.extend([f"## {scope['label']}", ""])
        current_id = scope.get("current_version_id")
        if current_id:
            current = state["versions"][current_id]
            lines.extend(
                [
                    f"当前版本：`{current_id}`（{current['slug']}）",
                    "",
                    current["summary"],
                    "",
                ]
            )
            if current.get("evidence"):
                lines.append("当前证据：")
                lines.extend(f"- `{item['reference']}`：{item['claim']}" for item in current["evidence"])
                lines.append("")
        else:
            lines.extend(["当前版本：尚未建立。", ""])
        active = [
            state["candidates"][key]
            for key in scope["candidate_ids"]
            if state["candidates"][key]["status"] in active_statuses
        ]
        lines.append("活跃候选：")
        if not active:
            lines.append("- 无。")
        for candidate in active:
            lines.append(f"- `{candidate['candidate_id']}` [{candidate['status']}]：{candidate['hypothesis']}")
        lines.append("")
    return "\n".join(lines)


def render_directory_map(state: dict[str, Any]) -> str:
    lines = [
        "# 文件夹职责总表",
        "",
        "> 每个受管文件夹必须有唯一职责、层级和父级。新增实验目录前先记录布局决策。",
        "",
        f"活跃平级目录预算：{state['config']['max_active_siblings']}  ",
        f"最大受管深度：{state['config']['max_managed_depth']}",
        "",
        "| ID | 路径 | 层级 | 父级 | 作用域 | 状态 | 管理直接子目录 | 职责 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    directories = sorted(state["directories"].values(), key=lambda item: (len(Path(item["path"]).parts), item["path"]))
    for directory in directories:
        lines.append(
            "| {id} | {path} | {level} | {parent} | {scope} | {status} | {managed} | {purpose} |".format(
                id=directory["directory_id"],
                path=markdown_escape(directory["path"]),
                level=directory["level"],
                parent=directory.get("parent_directory_id") or "—",
                scope=directory.get("scope_id") or "—",
                status=directory["status"],
                managed="是" if directory.get("manage_children") else "否",
                purpose=markdown_escape(directory["purpose"]),
            )
        )
    lines.extend(
        [
            "",
            "## 布局决策历史",
            "",
            "| 决策 | 状态 | 动作 | 目标路径 | 理由 | 备选方案 | 豁免理由 |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for decision in state["layout_decisions"].values():
        lines.append(
            "| {identity} | {status} | {action} | {path} | {reason} | {alternatives} | {override} |".format(
                identity=decision["decision_id"],
                status=decision["status"],
                action=decision["action"],
                path=markdown_escape(decision["target_path"]),
                reason=markdown_escape(decision["reason"]),
                alternatives=markdown_escape("; ".join(decision.get("alternatives_considered", [])) or "—"),
                override=markdown_escape(decision.get("override_reason") or "—"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_version_snapshot(state: dict[str, Any], version: dict[str, Any]) -> str:
    scope = state["scopes"][version["scope_id"]]
    lines = [
        f"# {version['version_id']}：{version['slug']}",
        "",
        "> 该文件是版本建立时的不可变快照。状态变化和后续候选见 `../VERSION_LEDGER.md`。",
        "",
        f"作用域：{scope['label']}（`{scope['scope_id']}`）  ",
        f"建立时间：{version['created_at']}  ",
        f"父版本：`{version.get('parent_version_id') or '无'}`  ",
        f"来源候选：`{version.get('promoted_from_candidate_id') or '初始基线'}`  ",
        f"旧标识：`{version.get('legacy_id') or '无'}`",
        "",
        "## 当前真相摘要",
        "",
        version["summary"],
        "",
        "## 改变类型",
        "",
    ]
    change_types = version.get("change_types", [])
    lines.extend(f"- `{item}`" for item in change_types)
    if not change_types:
        lines.append("- 初始基线。")
    lines.extend(["", "## 证据", ""])
    evidence = version.get("evidence", [])
    lines.extend(f"- `{item['reference']}`：{item['claim']}" for item in evidence)
    if not evidence:
        lines.append("- 初始基线由项目初始化事件建立。")
    source_candidate_id = version.get("promoted_from_candidate_id")
    if source_candidate_id and source_candidate_id in state["candidates"]:
        candidate = state["candidates"][source_candidate_id]
        lines.extend(
            [
                "",
                "## 晋级依据",
                "",
                f"- 候选：`{source_candidate_id}`",
                f"- 假设：{candidate['hypothesis']}",
                f"- 结论：{candidate.get('conclusion') or '未记录'}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_views(
    project_root: Path,
    control_dir: str,
    state: dict[str, Any],
    *,
    overwrite_snapshots: bool = False,
) -> None:
    root = control_path(project_root, control_dir)
    atomic_write_text(root / "CURRENT.md", render_current(state))
    atomic_write_text(root / "VERSION_LEDGER.md", render_version_ledger(state))
    atomic_write_text(root / "DIRECTORY_MAP.md", render_directory_map(state))
    if any(r.get("artifact_review_required") or r.get("artifact_review") for r in state.get("runs", {}).values()):
        from artifact_review import render_artifact_reviews
        atomic_write_text(root / "ARTIFACT_REVIEW.md", render_artifact_reviews(state))
    snapshots = root / "versions"
    for version in state["versions"].values():
        path = snapshots / f"{version['version_id']}.md"
        if overwrite_snapshots or not path.exists():
            atomic_write_text(path, render_version_snapshot(state, version))
