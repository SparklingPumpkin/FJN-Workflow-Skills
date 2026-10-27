#!/usr/bin/env python3
"""Adaptive guard for metaskill routing and Copilot customization artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from metaskill_policy import (
    PROFILE_RANK,
    PROFILE_REQUIRED_STAGES,
    PRIMITIVES,
    REVIEW_REQUIRED_STAGES,
    RISK_FLAGS,
    STAGE_ORDER,
    minimum_profile,
    required_stages,
)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LOCAL_LINK_RE = re.compile(r"\]\(([^)]+)\)")
SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|github[_-]?token|gh[_-]?token|secret|password)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(bearer\s+[a-z0-9._-]+|ghp_[a-z0-9]+|github_pat_[a-z0-9_]+)",
    re.IGNORECASE,
)
HOOK_EVENTS = {
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "SubagentStart",
    "SubagentStop",
    "Stop",
}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def passed(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def meta_dir(target_dir: Path) -> Path:
    return target_dir / ".metaskill"


def state_path(target_dir: Path) -> Path:
    return meta_dir(target_dir) / "run_state.json"


def manifest_path(target_dir: Path, stage: str) -> Path:
    return meta_dir(target_dir) / "stage_manifests" / f"{stage}.json"


def non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def load_json(path: Path, report: Report, *, required: bool = True) -> dict[str, Any] | None:
    if not path.exists():
        if required:
            report.error(f"Missing file: {path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"Invalid JSON in {path}: {exc}")
        return None
    if not isinstance(payload, dict):
        report.error(f"Expected JSON object in {path}")
        return None
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_path(payload: dict[str, Any], dotted_path: str, report: Report) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            report.error(f"Missing manifest field: {dotted_path}")
            return None
        current = current[part]
    if not non_empty(current):
        report.error(f"Empty manifest field: {dotted_path}")
    return current


def require_list(
    payload: dict[str, Any], dotted_path: str, report: Report, min_items: int = 1
) -> list[Any]:
    value = require_path(payload, dotted_path, report)
    if not isinstance(value, list):
        report.error(f"Manifest field must be a list: {dotted_path}")
        return []
    if len(value) < min_items:
        report.error(f"Manifest list needs at least {min_items} item(s): {dotted_path}")
    return value


def require_bool(payload: dict[str, Any], dotted_path: str, report: Report) -> bool:
    value = require_path(payload, dotted_path, report)
    if not isinstance(value, bool):
        report.error(f"Manifest field must be a boolean: {dotted_path}")
        return False
    return value


def ordered_unique_stages(stages: list[Any], report: Report) -> list[str]:
    selected: list[str] = []
    for value in stages:
        if not isinstance(value, str) or value not in STAGE_ORDER:
            report.error(f"Unknown selected stage: {value!r}")
            continue
        if value in selected:
            report.error(f"Duplicate selected stage: {value}")
            continue
        selected.append(value)
    expected = [stage for stage in STAGE_ORDER if stage in selected]
    if selected != expected:
        report.error(f"selected_stages must follow stage order: {expected}")
    return selected


def validate_artifact_plan(items: list[Any], report: Report, prefix: str) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, dict):
            report.error(f"{item_prefix} must be an object")
            continue
        primitive = item.get("primitive")
        path = item.get("path")
        purpose = item.get("purpose")
        embedded = item.get("embedded_primitives", [])
        if primitive not in PRIMITIVES:
            report.error(f"{item_prefix}.primitive must be one of {sorted(PRIMITIVES)}")
        if not isinstance(path, str) or not path.strip():
            report.error(f"{item_prefix}.path must be a non-empty string")
        if not isinstance(purpose, str) or not purpose.strip():
            report.error(f"{item_prefix}.purpose must be a non-empty string")
        if not isinstance(embedded, list) or any(value not in PRIMITIVES for value in embedded):
            report.error(f"{item_prefix}.embedded_primitives must contain only known primitives")
        if embedded and primitive != "custom-agent":
            report.error(f"{item_prefix}.embedded_primitives is only supported for custom-agent artifacts")
        artifacts.append(item)
    return artifacts


def validate_solution_routing(manifest: dict[str, Any], report: Report) -> None:
    route = manifest.get("solution_routing", {})
    task_mode = require_path(manifest, "solution_routing.task_mode", report)
    if task_mode not in {"create-or-update", "review-only"}:
        report.error("solution_routing.task_mode must be create-or-update or review-only")
    require_path(manifest, "solution_routing.desired_outcome", report)
    require_list(manifest, "solution_routing.trigger_phrases", report)
    require_path(manifest, "solution_routing.scope", report)
    primitives = require_list(manifest, "solution_routing.selected_primitives", report)
    invalid = [value for value in primitives if value not in PRIMITIVES]
    if invalid:
        report.error(f"Unknown primitives: {invalid}; allowed: {sorted(PRIMITIVES)}")
    if len(set(map(str, primitives))) != len(primitives):
        report.error("selected_primitives contains duplicates")

    artifacts = validate_artifact_plan(
        require_list(manifest, "solution_routing.artifact_plan", report),
        report,
        "solution_routing.artifact_plan",
    )
    artifact_primitives: set[Any] = set()
    for item in artifacts:
        artifact_primitives.add(item.get("primitive"))
        artifact_primitives.update(item.get("embedded_primitives", []))
    missing_artifacts = set(primitives) - artifact_primitives
    if missing_artifacts:
        report.error(f"Selected primitives without an artifact plan: {sorted(missing_artifacts)}")
    undeclared_primitives = artifact_primitives - set(primitives)
    if undeclared_primitives:
        report.error(
            f"Artifact plan contains primitives absent from selected_primitives: {sorted(undeclared_primitives)}"
        )

    supporting_resources = route.get("supporting_resources")
    if not isinstance(supporting_resources, list):
        report.error("solution_routing.supporting_resources must be a list")
    elif any(
        isinstance(resource, str) and Path(resource).name == "mcp.json"
        for resource in supporting_resources
    ) and "mcp" not in primitives:
        report.error("A supporting mcp.json requires 'mcp' in selected_primitives")
    require_list(manifest, "solution_routing.runtime_wiring", report)
    risk_factors = route.get("risk_factors")
    if not isinstance(risk_factors, list):
        report.error("solution_routing.risk_factors must be a list, including [] when none")
    risk_assessment = route.get("risk_assessment")
    if not isinstance(risk_assessment, dict):
        report.error("solution_routing.risk_assessment must be an object")
    else:
        for flag in RISK_FLAGS:
            require_bool(manifest, f"solution_routing.risk_assessment.{flag}", report)

    profile = require_path(manifest, "solution_routing.workflow_profile", report)
    selected = ordered_unique_stages(
        require_list(manifest, "solution_routing.selected_stages", report), report
    )
    require_path(manifest, "solution_routing.routing_rationale", report)
    if profile not in PROFILE_REQUIRED_STAGES:
        report.error(f"workflow_profile must be one of {sorted(PROFILE_REQUIRED_STAGES)}")
        return

    minimum, reasons = minimum_profile(route)
    if PROFILE_RANK[profile] < PROFILE_RANK[minimum]:
        report.error(
            f"Routing profile '{profile}' is too light; minimum is '{minimum}' because: "
            + "; ".join(reasons)
        )
    override_reason = route.get("workflow_profile_override_reason", "")
    if not isinstance(override_reason, str):
        report.error("solution_routing.workflow_profile_override_reason must be a string")
    elif PROFILE_RANK[profile] > PROFILE_RANK[minimum] and not override_reason.strip():
        report.error(
            f"Routing profile '{profile}' is heavier than minimum '{minimum}'; "
            "record workflow_profile_override_reason or use the computed minimum"
        )
    elif PROFILE_RANK[profile] == PROFILE_RANK[minimum] and override_reason.strip():
        report.warn("workflow_profile_override_reason is ignored when profile equals the minimum")

    required = required_stages(profile, task_mode)
    missing = [stage for stage in required if stage not in selected]
    if missing:
        report.error(f"Profile '{profile}' is missing required stages: {missing}")
    allowed_optional: set[str] = set()
    if profile in {"standard", "gated"}:
        allowed_optional.add("migration_audit")
    if profile == "standard":
        allowed_optional.add("local_contract")
    extra = [stage for stage in selected if stage not in required and stage not in allowed_optional]
    if extra:
        report.error(f"Profile '{profile}' contains unsupported extra stages: {extra}")
    if route.get("risk_assessment", {}).get("migrates_existing_customization") is True:
        if "migration_audit" not in selected:
            report.error("Migration work must select the migration_audit stage")
    if task_mode == "review-only" and "implementation" in selected:
        report.error("review-only routing must not select implementation")


def validate_scope_intake(manifest: dict[str, Any], target_dir: Path, report: Report) -> None:
    require_path(manifest, "scope_intake.target_name", report)
    target = require_path(manifest, "scope_intake.target_dir", report)
    require_path(manifest, "scope_intake.purpose", report)
    require_list(manifest, "scope_intake.trigger_phrases", report)
    require_path(manifest, "scope_intake.expected_users", report)
    require_list(manifest, "scope_intake.selected_primitives", report)
    require_path(manifest, "scope_intake.scope", report)
    require_path(manifest, "scope_intake.composition_reason", report)
    if isinstance(target, str) and Path(target).resolve() != target_dir:
        report.error(f"scope_intake.target_dir '{target}' differs from '{target_dir}'")


def route_section(routing: dict[str, Any] | None) -> dict[str, Any]:
    if routing is None:
        return {}
    section = routing.get("solution_routing", {})
    return section if isinstance(section, dict) else {}


def validate_upstream_baseline(
    manifest: dict[str, Any], routing: dict[str, Any] | None, report: Report
) -> None:
    checked = require_list(manifest, "upstream_baseline.selected_primitives_checked", report)
    if routing:
        expected = set(routing.get("solution_routing", {}).get("selected_primitives", []))
        missing = expected - set(checked)
        if missing:
            report.error(f"Upstream rules not checked for primitives: {sorted(missing)}")
        extra = set(checked) - expected
        if extra:
            report.error(f"Upstream checks contain unselected primitives: {sorted(extra)}")
    for field in [
        "locations_checked",
        "discovery_and_invocation_checked",
        "schema_checked",
        "security_checked",
    ]:
        if manifest.get("upstream_baseline", {}).get(field) is not True:
            report.error(f"upstream_baseline.{field} must be true")
    require_path(manifest, "upstream_baseline.notes", report)


def validate_local_contract(
    manifest: dict[str, Any], routing: dict[str, Any] | None, report: Report
) -> None:
    require_list(manifest, "local_contract.local_rules", report)
    require_path(manifest, "local_contract.guard_policy", report)
    require_path(manifest, "local_contract.approval_and_secret_policy", report)
    contract = manifest.get("local_contract", {})
    for field in ["needs_stage_gating", "needs_guard_script", "needs_hooks", "needs_mcp"]:
        if not isinstance(contract.get(field), bool):
            report.error(f"local_contract.{field} must be a boolean")
    if contract.get("needs_stage_gating"):
        require_path(manifest, "local_contract.state_location", report)
    primitives = set(route_section(routing).get("selected_primitives", []))
    if "hook" in primitives and contract.get("needs_hooks") is not True:
        report.error("local_contract.needs_hooks must be true when a hook is selected")
    if "mcp" in primitives and contract.get("needs_mcp") is not True:
        report.error("local_contract.needs_mcp must be true when MCP is selected")


def artifact_keys(items: list[Any]) -> set[tuple[Any, Any, Any, tuple[Any, ...]]]:
    return {
        (
            item.get("primitive"),
            item.get("path"),
            item.get("purpose"),
            tuple(item.get("embedded_primitives", [])),
        )
        for item in items
        if isinstance(item, dict)
    }


def validate_asset_plan(
    manifest: dict[str, Any], routing: dict[str, Any] | None, report: Report
) -> None:
    artifacts = require_list(manifest, "asset_plan.artifacts", report)
    validate_artifact_plan(artifacts, report, "asset_plan.artifacts")
    resources = manifest.get("asset_plan", {}).get("supporting_resources")
    commands = manifest.get("asset_plan", {}).get("validation_commands")
    if not isinstance(resources, list):
        report.error("asset_plan.supporting_resources must be a list")
    if not isinstance(commands, list) or not commands:
        report.error("asset_plan.validation_commands must be a non-empty list")
    route = route_section(routing)
    if artifact_keys(artifacts) != artifact_keys(route.get("artifact_plan", [])):
        report.error("asset_plan.artifacts must match the routed artifact plan")
    if isinstance(resources, list) and set(resources) != set(route.get("supporting_resources", [])):
        report.error("asset_plan.supporting_resources must match the routed supporting resources")


def parse_frontmatter(path: Path, report: Report) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        report.error(f"{path} must start with YAML frontmatter marker ---")
        return None
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        report.error(f"{path} frontmatter is missing closing ---")
        return None
    for line_number, line in enumerate(lines[1:end], start=2):
        if "\t" in line:
            report.error(f"Tab found in {path} frontmatter at line {line_number}")
    try:
        frontmatter = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        report.error(f"Invalid YAML frontmatter in {path}: {exc}")
        return None
    if not isinstance(frontmatter, dict):
        report.error(f"Frontmatter must be a YAML mapping: {path}")
        return None
    return frontmatter


def validate_local_links(path: Path, report: Report) -> None:
    text = path.read_text(encoding="utf-8")
    for target in LOCAL_LINK_RE.findall(text):
        clean = target.split("#", 1)[0].split("?", 1)[0]
        if not clean or clean.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (path.parent / clean).resolve()
        if not resolved.exists():
            report.error(f"Broken local reference in {path}: {target}")


def validate_invocation_flags(frontmatter: dict[str, Any], path: Path, report: Report) -> None:
    for key in ["user-invocable", "disable-model-invocation"]:
        if key in frontmatter and not isinstance(frontmatter[key], bool):
            report.error(f"{key} must be a boolean in {path}")


def path_contains(path: Path, parts: tuple[str, ...]) -> bool:
    return any(path.parts[index : index + len(parts)] == parts for index in range(len(path.parts)))


def validate_discovery_location(
    path: Path, primitive: str, report: Report, scope: str = "workspace"
) -> None:
    if scope != "workspace":
        return
    if primitive == "file-instructions" and not path_contains(path, (".github", "instructions")):
        report.error(f"Workspace file instructions must be under .github/instructions: {path}")
    elif primitive == "prompt" and not path_contains(path, (".github", "prompts")):
        report.error(f"Workspace prompts must be under .github/prompts: {path}")
    elif primitive == "custom-agent" and not path_contains(path, (".github", "agents")):
        report.error(f"Workspace custom agents must be under .github/agents: {path}")
    elif primitive == "skill" and not any(
        path_contains(path, parts)
        for parts in [
            (".github", "skills"),
            (".agents", "skills"),
            (".claude", "skills"),
            ("FJN-Agent", "skills"),
        ]
    ):
        report.error(f"Workspace Skill is not in a supported discovery directory: {path}")


def validate_markdown_artifact(
    path: Path,
    primitive: str,
    report: Report,
    declared_embedded: set[str] | None = None,
    scope: str = "workspace",
) -> None:
    if primitive == "agent-instructions":
        if path.name not in {
            "copilot-instructions.md",
            "AGENTS.md",
            "CLAUDE.md",
            "CLAUDE.local.md",
        }:
            report.error(f"Unsupported project-wide instructions filename: {path}")
        validate_local_links(path, report)
        return

    frontmatter = parse_frontmatter(path, report)
    if frontmatter is None:
        return
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        report.error(f"{primitive} artifact missing description: {path}")
    elif len(description) > 1024:
        report.error(f"Description exceeds 1024 characters: {path}")
    validate_invocation_flags(frontmatter, path, report)

    if primitive == "skill":
        name = frontmatter.get("name")
        if path.name != "SKILL.md":
            report.error(f"Skill entry point must be named SKILL.md: {path}")
        if not name or not NAME_RE.match(name):
            report.error(f"Skill name must be lowercase alphanumeric plus hyphens: {path}")
        elif name != path.parent.name:
            report.error(f"Skill name '{name}' must match folder '{path.parent.name}'")
        if description and not any(term in description.lower() for term in ["use when", "when", "当"]):
            report.warn(f"Skill description should include concrete trigger phrasing: {path}")
        context = frontmatter.get("context")
        if context is not None and context not in {"inline", "fork"}:
            report.error(f"Skill context must be inline or fork: {path}")
        elif context == "fork":
            report.warn(
                f"Skill context fork is experimental and requires "
                f"github.copilot.chat.skillTool.enabled: {path}"
            )
    elif primitive == "file-instructions" and not path.name.endswith(".instructions.md"):
        report.error(f"File instructions must end with .instructions.md: {path}")
    elif primitive == "prompt" and not path.name.endswith(".prompt.md"):
        report.error(f"Prompt must end with .prompt.md: {path}")
    elif primitive == "custom-agent" and not path.name.endswith(".agent.md"):
        report.error(f"Custom agent must end with .agent.md: {path}")
    if primitive in {"prompt", "custom-agent"}:
        tools = frontmatter.get("tools")
        if tools is not None and not isinstance(tools, list):
            report.error(f"tools must be a YAML list in {path}")
        model = frontmatter.get("model")
        if model is not None and not (
            isinstance(model, str)
            or (isinstance(model, list) and all(isinstance(value, str) for value in model))
        ):
            report.error(f"model must be a string or string list in {path}")
    if primitive == "prompt" and "agent" in frontmatter and not isinstance(
        frontmatter["agent"], str
    ):
        report.error(f"agent must be a string in {path}")
    if primitive == "file-instructions" and "applyTo" in frontmatter:
        apply_to = frontmatter["applyTo"]
        if not isinstance(apply_to, (str, list)):
            report.error(f"applyTo must be a string or list in {path}")
        if apply_to == "**":
            report.warn(f"applyTo '**' loads this instruction for every file operation: {path}")
    if primitive == "custom-agent":
        declared_embedded = declared_embedded or set()
        if "infer" in frontmatter:
            report.warn(f"infer is deprecated; use invocation flags instead: {path}")
        agents = frontmatter.get("agents")
        if agents is not None and not (
            isinstance(agents, list) and all(isinstance(value, str) for value in agents)
        ):
            report.error(f"agents must be a string list in {path}")
        tools = frontmatter.get("tools")
        if isinstance(agents, list) and agents and agents != ["*"]:
            if not isinstance(tools, list) or "agent" not in tools:
                report.error(f"A custom agent that allows named subagents needs the agent tool: {path}")
        handoffs = frontmatter.get("handoffs")
        if handoffs is not None:
            if not isinstance(handoffs, list):
                report.error(f"handoffs must be a list in {path}")
            else:
                for index, handoff in enumerate(handoffs):
                    prefix = f"{path}:handoffs[{index}]"
                    if not isinstance(handoff, dict):
                        report.error(f"{prefix} must be an object")
                        continue
                    for field in ["label", "agent"]:
                        if not isinstance(handoff.get(field), str) or not handoff[field].strip():
                            report.error(f"{prefix}.{field} must be a non-empty string")
                    if "prompt" in handoff and not isinstance(handoff["prompt"], str):
                        report.error(f"{prefix}.prompt must be a string")
                    if "send" in handoff and not isinstance(handoff["send"], bool):
                        report.error(f"{prefix}.send must be a boolean")
        inline_hooks = frontmatter.get("hooks")
        if inline_hooks is not None:
            if "hook" not in declared_embedded:
                report.error(f"Custom agent inline hooks must be declared as embedded_primitives: {path}")
            validate_hook_artifact(path, {"hooks": inline_hooks}, report)
        elif "hook" in declared_embedded:
            report.error(f"Artifact plan declares an embedded hook but the custom agent has none: {path}")
    validate_discovery_location(path, primitive, report, scope)
    validate_local_links(path, report)


def scan_hardcoded_secrets(value: Any, path: str, report: Report) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if SECRET_KEY_RE.search(str(key)) and isinstance(child, str):
                if child and not child.startswith(("${", "${input:", "${env:")):
                    report.error(f"Possible hardcoded secret at {child_path}")
            scan_hardcoded_secrets(child, child_path, report)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_hardcoded_secrets(child, f"{path}[{index}]", report)
    elif isinstance(value, str) and SECRET_VALUE_RE.search(value):
        report.error(f"Possible hardcoded secret literal at {path}")


def validate_hook_command_target(path: Path, command: str, prefix: str, report: Report) -> None:
    try:
        first_token = shlex.split(command)[0]
    except (ValueError, IndexError):
        report.error(f"{prefix} cannot be parsed")
        return
    if first_token.startswith(("./", "../")) and "${" not in first_token:
        candidates = [(ancestor / first_token).resolve() for ancestor in path.parents]
        if not any(candidate.exists() for candidate in candidates):
            report.error(
                f"Hook command target '{first_token}' does not exist relative to any workspace ancestor of {path}"
            )


def validate_hook_artifact(path: Path, payload: dict[str, Any], report: Report) -> None:
    hooks = payload.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        report.error(f"Hook configuration must contain a non-empty hooks object: {path}")
        return
    for event, entries in hooks.items():
        if event not in HOOK_EVENTS:
            report.error(f"Unsupported hook event '{event}' in {path}")
        if not isinstance(entries, list) or not entries:
            report.error(f"Hook event '{event}' must contain a non-empty list in {path}")
            continue
        for index, entry in enumerate(entries):
            prefix = f"{path}:hooks.{event}[{index}]"
            if not isinstance(entry, dict):
                report.error(f"{prefix} must be an object")
                continue
            if entry.get("type") != "command":
                report.error(f"{prefix}.type must be 'command'")
            command_fields = [field for field in ["command", "windows", "linux", "osx"] if field in entry]
            if not command_fields:
                report.error(f"{prefix} needs command or a platform-specific command")
            for field in command_fields:
                command = entry.get(field)
                if not isinstance(command, str) or not command.strip():
                    report.error(f"{prefix}.{field} must be a non-empty string")
                else:
                    validate_hook_command_target(path, command, f"{prefix}.{field}", report)
            timeout = entry.get("timeout")
            if timeout is not None and (
                not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0
            ):
                report.error(f"{prefix}.timeout must be a positive number")
            if "cwd" in entry and not isinstance(entry["cwd"], str):
                report.error(f"{prefix}.cwd must be a string")
            if "env" in entry:
                env = entry["env"]
                if not isinstance(env, dict) or any(not isinstance(key, str) for key in env):
                    report.error(f"{prefix}.env must be an object with string keys")
                elif any(not isinstance(value, (str, int, float, bool)) for value in env.values()):
                    report.error(f"{prefix}.env values must be scalar")


def validate_mcp_artifact(path: Path, payload: dict[str, Any], report: Report) -> None:
    unknown_top_level = set(payload) - {"servers", "inputs", "sandbox"}
    if unknown_top_level:
        report.error(f"Unsupported top-level MCP fields in {path}: {sorted(unknown_top_level)}")
    inputs = payload.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, list):
            report.error(f"MCP inputs must be a list: {path}")
        else:
            seen_ids: set[str] = set()
            for index, item in enumerate(inputs):
                prefix = f"{path}:inputs[{index}]"
                if not isinstance(item, dict):
                    report.error(f"{prefix} must be an object")
                    continue
                input_type = item.get("type")
                input_id = item.get("id")
                if input_type not in {"promptString", "pickString", "command"}:
                    report.error(f"{prefix}.type is unsupported")
                if not isinstance(input_id, str) or not input_id:
                    report.error(f"{prefix}.id must be a non-empty string")
                elif input_id in seen_ids:
                    report.error(f"Duplicate MCP input id: {input_id}")
                else:
                    seen_ids.add(input_id)
                if input_type in {"promptString", "pickString"} and not isinstance(
                    item.get("description"), str
                ):
                    report.error(f"{prefix}.description is required")
                if input_type == "pickString" and not isinstance(item.get("options"), list):
                    report.error(f"{prefix}.options must be a list")
                if input_type == "command" and not isinstance(item.get("command"), str):
                    report.error(f"{prefix}.command is required")
    sandbox = payload.get("sandbox")
    if sandbox is not None:
        if not isinstance(sandbox, dict):
            report.error(f"MCP sandbox must be an object: {path}")
        else:
            filesystem = sandbox.get("filesystem", {})
            network = sandbox.get("network", {})
            if not isinstance(filesystem, dict) or not isinstance(network, dict):
                report.error(f"MCP sandbox filesystem and network must be objects: {path}")
            else:
                for key in ["allowWrite", "denyRead", "denyWrite"]:
                    value = filesystem.get(key)
                    if value is not None and (
                        not isinstance(value, list) or any(not isinstance(item, str) for item in value)
                    ):
                        report.error(f"sandbox.filesystem.{key} must be a string list")
                for key in ["allowedDomains", "deniedDomains"]:
                    value = network.get(key)
                    if value is not None and (
                        not isinstance(value, list) or any(not isinstance(item, str) for item in value)
                    ):
                        report.error(f"sandbox.network.{key} must be a string list")
    servers = payload.get("servers")
    if not isinstance(servers, dict) or not servers:
        report.error(f"MCP configuration must contain a non-empty servers object: {path}")
        return
    for name, server in servers.items():
        prefix = f"{path}:servers.{name}"
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
            report.error(f"MCP server name must be camelCase without spaces or symbols: {name!r}")
        if not isinstance(server, dict) or not server:
            report.error(f"{prefix} must be a non-empty object")
            continue
        server_type = server.get("type")
        if server_type is None:
            server_type = "stdio" if "command" in server else "http" if "url" in server else None
        if server_type not in {"stdio", "http", "sse"}:
            report.error(f"{prefix}.type must be stdio, http, or sse")
            continue
        if server_type == "stdio":
            unknown = set(server) - {
                "type",
                "command",
                "args",
                "cwd",
                "env",
                "envFile",
                "dev",
                "sandboxEnabled",
            }
            if unknown:
                report.error(f"Unsupported stdio MCP fields at {prefix}: {sorted(unknown)}")
            if "url" in server:
                report.error(f"{prefix} cannot combine stdio command with url")
            if not isinstance(server.get("command"), str) or not server["command"].strip():
                report.error(f"{prefix}.command must be a non-empty string for stdio")
            if "args" in server and (
                not isinstance(server["args"], list)
                or any(not isinstance(value, (str, int, float, bool)) for value in server["args"])
            ):
                report.error(f"{prefix}.args must be a scalar list")
            if "cwd" in server and not isinstance(server["cwd"], str):
                report.error(f"{prefix}.cwd must be a string")
            if "env" in server:
                env = server["env"]
                if not isinstance(env, dict) or any(not isinstance(key, str) for key in env):
                    report.error(f"{prefix}.env must be an object")
                elif any(value is not None and not isinstance(value, (str, int, float)) for value in env.values()):
                    report.error(f"{prefix}.env values must be strings, numbers, or null")
            if "envFile" in server and not isinstance(server["envFile"], str):
                report.error(f"{prefix}.envFile must be a string")
            if "sandboxEnabled" in server and not isinstance(server["sandboxEnabled"], bool):
                report.error(f"{prefix}.sandboxEnabled must be a boolean")
        else:
            unknown = set(server) - {"type", "url", "headers", "oauth", "dev"}
            if unknown:
                report.error(f"Unsupported {server_type} MCP fields at {prefix}: {sorted(unknown)}")
            if "command" in server:
                report.error(f"{prefix} cannot combine {server_type} url with command")
            url = server.get("url")
            if not isinstance(url, str) or not url.strip():
                report.error(f"{prefix}.url must be a non-empty string for {server_type}")
            else:
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https", "unix", "pipe"}:
                    report.error(f"{prefix}.url has an unsupported scheme")
                elif parsed.scheme in {"http", "https"} and not parsed.netloc:
                    report.error(f"{prefix}.url must include a host")
            headers = server.get("headers")
            if headers is not None and (
                not isinstance(headers, dict)
                or any(not isinstance(key, str) or not isinstance(value, str) for key, value in headers.items())
            ):
                report.error(f"{prefix}.headers must be a string-to-string object")
            oauth = server.get("oauth")
            if oauth is not None:
                if not isinstance(oauth, dict) or not isinstance(oauth.get("clientId"), str):
                    report.error(f"{prefix}.oauth requires a string clientId")
                elif "enterpriseManaged" in oauth and not isinstance(oauth["enterpriseManaged"], bool):
                    report.error(f"{prefix}.oauth.enterpriseManaged must be a boolean")


def validate_json_artifact(
    path: Path, primitive: str, report: Report, scope: str = "workspace"
) -> None:
    payload = load_json(path, report)
    if payload is None:
        return
    scan_hardcoded_secrets(payload, str(path), report)
    if primitive == "hook":
        if scope == "workspace" and not path_contains(path, (".github", "hooks")):
            report.error(f"Workspace hook configuration must be under .github/hooks: {path}")
        validate_hook_artifact(path, payload, report)
    if primitive == "mcp":
        if scope == "workspace" and (path.name != "mcp.json" or path.parent.name != ".vscode"):
            report.error(f"Workspace MCP configuration must be .vscode/mcp.json: {path}")
        validate_mcp_artifact(path, payload, report)


def resolve_artifact_path(target_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (target_dir / path).resolve()


def validate_declared_artifacts(
    target_dir: Path, routing: dict[str, Any] | None, report: Report
) -> None:
    if routing is None:
        report.error("Cannot validate implementation without solution_routing manifest")
        return
    artifacts = routing.get("solution_routing", {}).get("artifact_plan", [])
    scope = route_section(routing).get("scope", "workspace")
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        primitive = item.get("primitive")
        raw_path = item.get("path")
        if primitive not in PRIMITIVES or not isinstance(raw_path, str):
            continue
        path = resolve_artifact_path(target_dir, raw_path)
        if not path.exists():
            report.error(f"Declared {primitive} artifact does not exist: {path}")
            continue
        if path.is_dir():
            report.error(f"Artifact plan must point to an entry file, not a directory: {path}")
            continue
        if primitive in {
            "agent-instructions",
            "file-instructions",
            "prompt",
            "custom-agent",
            "skill",
        }:
            validate_markdown_artifact(
                path,
                primitive,
                report,
                set(item.get("embedded_primitives", [])),
                scope,
            )
        elif primitive in {"hook", "mcp"}:
            validate_json_artifact(path, primitive, report, scope)


def validate_supporting_resources(
    target_dir: Path, routing: dict[str, Any] | None, report: Report
) -> None:
    if routing is None:
        return
    route = routing.get("solution_routing", {})
    selected_primitives = set(route.get("selected_primitives", []))
    raw_paths = list(route.get("supporting_resources", []))
    for item in route.get("artifact_plan", []):
        if not isinstance(item, dict) or item.get("primitive") != "skill":
            continue
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            continue
        skill_md = resolve_artifact_path(target_dir, raw_path)
        for folder_name in ["scripts", "templates"]:
            folder = skill_md.parent / folder_name
            if folder.exists():
                raw_paths.extend(str(path) for path in folder.rglob("*") if path.is_file())

    checked: set[Path] = set()
    for raw_path in raw_paths:
        if not isinstance(raw_path, str):
            report.error(f"Supporting resource path must be a string: {raw_path!r}")
            continue
        path = resolve_artifact_path(target_dir, raw_path)
        if path in checked:
            continue
        checked.add(path)
        if not path.exists() or not path.is_file():
            report.error(f"Declared supporting resource does not exist: {path}")
            continue
        if path.suffix == ".py":
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                report.error(f"Python script does not compile: {path}: {exc.msg}")
        elif path.suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                report.error(f"JSON resource does not parse: {path}: {exc}")
                continue
            if isinstance(payload, dict) and "hooks" in payload:
                report.error(f"Hook configuration must be declared in artifact_plan, not supporting_resources: {path}")
                if "hook" not in selected_primitives:
                    report.error(f"Hook resource is absent from selected_primitives: {path}")
            if isinstance(payload, dict) and "servers" in payload:
                report.error(f"MCP configuration must be declared in artifact_plan, not supporting_resources: {path}")
                if "mcp" not in selected_primitives:
                    report.error(f"MCP resource is absent from selected_primitives: {path}")


def validate_materialized_route_risk(
    target_dir: Path, routing: dict[str, Any] | None, report: Report
) -> None:
    """Reject a route that became more complex after files were materialized."""
    route = route_section(routing)
    risks = route.get("risk_assessment", {})
    if not isinstance(risks, dict):
        return
    for item in route.get("artifact_plan", []):
        if not isinstance(item, dict) or item.get("primitive") != "skill":
            continue
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            continue
        skill_md = resolve_artifact_path(target_dir, raw_path)
        if not skill_md.exists():
            continue
        bundled: list[Path] = []
        for folder_name in ["scripts", "references", "templates", "assets", "examples"]:
            folder = skill_md.parent / folder_name
            if folder.exists():
                bundled.extend(path for path in folder.rglob("*") if path.is_file())
        if bundled and risks.get("bundled_resources_or_scripts") is not True:
            report.error(
                "Implementation added bundled Skill resources but routing marked "
                "bundled_resources_or_scripts=false. Return to solution_routing and reroute. "
                f"Examples: {[str(path) for path in bundled[:3]]}"
            )
    minimum, reasons = minimum_profile(route)
    profile = route.get("workflow_profile")
    if profile in PROFILE_RANK and PROFILE_RANK[profile] < PROFILE_RANK[minimum]:
        report.error(
            f"Materialized customization requires profile '{minimum}', not '{profile}': "
            + "; ".join(reasons)
        )


def validate_implementation(
    target_dir: Path,
    manifest: dict[str, Any],
    routing: dict[str, Any] | None,
    report: Report,
) -> None:
    created = manifest.get("implementation", {}).get("files_created")
    updated = manifest.get("implementation", {}).get("files_updated")
    if not non_empty(created) and not non_empty(updated):
        report.error("implementation needs files_created or files_updated")
    implemented = require_list(manifest, "implementation.artifacts_implemented", report)
    require_list(manifest, "implementation.runtime_wiring_implemented", report)
    route = route_section(routing)
    covered = set(str(value) for value in implemented)
    for item in route.get("artifact_plan", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("primitive")) not in covered and str(item.get("path")) not in covered:
            report.error(
                f"implementation.artifacts_implemented does not cover {item.get('primitive')} at {item.get('path')}"
            )
    validate_declared_artifacts(target_dir, routing, report)
    validate_supporting_resources(target_dir, routing, report)
    validate_materialized_route_risk(target_dir, routing, report)


def validate_validation_stage(
    target_dir: Path,
    manifest: dict[str, Any],
    routing: dict[str, Any] | None,
    report: Report,
) -> None:
    validate_declared_artifacts(target_dir, routing, report)
    validate_supporting_resources(target_dir, routing, report)
    validate_materialized_route_risk(target_dir, routing, report)
    require_list(manifest, "validation.commands_run", report)
    require_list(manifest, "validation.artifact_checks", report)
    require_path(manifest, "validation.runtime_wiring_check", report)
    require_path(manifest, "validation.security_check", report)
    failures = manifest.get("validation", {}).get("known_failures")
    if not isinstance(failures, list):
        report.error("validation.known_failures must be a list")
    elif failures:
        report.error("validation.known_failures must be empty before the stage can pass")
    plan_manifest = load_json(manifest_path(target_dir, "asset_plan"), report, required=False)
    if plan_manifest is not None:
        planned = set(plan_manifest.get("asset_plan", {}).get("validation_commands", []))
        actual = set(manifest.get("validation", {}).get("commands_run", []))
        missing_commands = planned - actual
        if missing_commands:
            report.error(f"Planned validation commands were not recorded as run: {sorted(missing_commands)}")


def validate_handoff(
    manifest: dict[str, Any], state: dict[str, Any] | None, report: Report
) -> None:
    require_path(manifest, "handoff.usage", report)
    require_list(manifest, "handoff.selected_primitives", report)
    require_path(manifest, "handoff.workflow_profile", report)
    stages_run = require_list(manifest, "handoff.stages_run", report)
    require_list(manifest, "handoff.changed_files", report)
    require_path(manifest, "handoff.validation_summary", report)
    activation = manifest.get("handoff", {}).get("activation_or_approval_steps")
    gaps = manifest.get("handoff", {}).get("known_gaps")
    if not isinstance(activation, list):
        report.error("handoff.activation_or_approval_steps must be a list")
    if not isinstance(gaps, list):
        report.error("handoff.known_gaps must be a list")
    require_path(manifest, "handoff.next_maintenance_step", report)
    if state:
        selected = state.get("selected_stages", [])
        if set(manifest.get("handoff", {}).get("selected_primitives", [])) != set(
            state.get("selected_primitives", [])
        ):
            report.error("handoff.selected_primitives must match run state")
        if manifest.get("handoff", {}).get("workflow_profile") != state.get("workflow_profile"):
            report.error("handoff.workflow_profile must match run state")
        for stage in selected:
            if stage == "handoff":
                continue
            guard_status = state.get("stages", {}).get(stage, {}).get("guard_status")
            if guard_status not in {"pass", "overridden"}:
                report.error(f"Cannot hand off: selected stage '{stage}' guard is '{guard_status}'")
        if state.get("override_history") and not gaps:
            report.error("handoff.known_gaps must disclose documented stage overrides")
        missing = [stage for stage in selected if stage != "handoff" and stage not in stages_run]
        if missing:
            report.error(f"handoff.stages_run is missing completed stages: {missing}")


def validate_migration_audit(manifest: dict[str, Any], report: Report) -> None:
    require_path(manifest, "migration_audit.source_skill_or_workflow", report)
    require_list(manifest, "migration_audit.retained_rules", report)
    require_path(manifest, "migration_audit.compatibility_notes", report)
    for field in ["removed_rules", "new_hard_gates"]:
        value = manifest.get("migration_audit", {}).get(field)
        if not isinstance(value, list):
            report.error(f"migration_audit.{field} must be a list")


def validate_stage(
    target_dir: Path,
    stage: str,
    state: dict[str, Any] | None,
    manifest: dict[str, Any],
    routing: dict[str, Any] | None,
    report: Report,
) -> None:
    if manifest.get("stage") != stage:
        report.error(f"Manifest stage is '{manifest.get('stage')}', expected '{stage}'")
    if state:
        selected = state.get("selected_stages", [])
        if stage not in selected:
            report.error(f"Stage '{stage}' is not selected by the current routing decision")
        if state.get("active_stage") != stage:
            report.error(
                f"Guard may only validate the active stage '{state.get('active_stage')}', not '{stage}'"
            )
        if stage in selected:
            index = selected.index(stage)
            for previous in selected[:index]:
                previous_state = state.get("stages", {}).get(previous, {})
                acceptable = (
                    previous_state.get("guard_status") == "pass"
                    and previous_state.get("status") == "completed"
                ) or (
                    previous_state.get("guard_status") == "overridden"
                    and previous_state.get("status") == "overridden"
                )
                if not acceptable:
                    report.error(
                        f"Earlier selected stage '{previous}' must be completed or explicitly overridden"
                    )
                expected_hash = previous_state.get("manifest_sha256")
                previous_manifest = manifest_path(target_dir, previous)
                if previous_state.get("guard_status") == "pass":
                    if not isinstance(expected_hash, str) or not previous_manifest.exists():
                        report.error(f"Earlier stage '{previous}' lacks bound manifest evidence")
                    elif sha256_file(previous_manifest) != expected_hash:
                        report.error(
                            f"Earlier stage manifest changed after guard pass: {previous_manifest}. "
                            "Re-enter and revalidate that stage."
                        )
    if stage == "solution_routing":
        validate_solution_routing(manifest, report)
    elif stage == "scope_intake":
        validate_scope_intake(manifest, target_dir, report)
        route = route_section(routing)
        expected = set(route.get("selected_primitives", []))
        actual = set(manifest.get("scope_intake", {}).get("selected_primitives", []))
        if actual != expected:
            report.error("scope_intake.selected_primitives must match solution_routing")
        scope = manifest.get("scope_intake", {})
        if scope.get("purpose") != route.get("desired_outcome"):
            report.error("scope_intake.purpose must match solution_routing.desired_outcome")
        if set(scope.get("trigger_phrases", [])) != set(route.get("trigger_phrases", [])):
            report.error("scope_intake.trigger_phrases must match solution_routing")
        if scope.get("scope") != route.get("scope"):
            report.error("scope_intake.scope must match solution_routing.scope")
    elif stage == "upstream_baseline":
        validate_upstream_baseline(manifest, routing, report)
    elif stage == "local_contract":
        validate_local_contract(manifest, routing, report)
    elif stage == "asset_plan":
        validate_asset_plan(manifest, routing, report)
    elif stage == "implementation":
        validate_implementation(target_dir, manifest, routing, report)
    elif stage == "validation":
        validate_validation_stage(target_dir, manifest, routing, report)
    elif stage == "handoff":
        validate_handoff(manifest, state, report)
    elif stage == "migration_audit":
        validate_migration_audit(manifest, report)


def apply_routing_to_state(state: dict[str, Any], manifest: dict[str, Any]) -> None:
    route = manifest["solution_routing"]
    selected = route["selected_stages"]
    state["workflow_profile"] = route["workflow_profile"]
    state["selected_primitives"] = route["selected_primitives"]
    state["selected_stages"] = selected
    for stage in STAGE_ORDER:
        stage_state = state.setdefault("stages", {}).setdefault(stage, {})
        if stage == "solution_routing":
            continue
        if stage in selected:
            stage_state["status"] = "not_started"
            stage_state["guard_status"] = "not_run"
            stage_state.pop("last_guard_at", None)
        else:
            stage_state["status"] = "not_required"
            stage_state["guard_status"] = "not_required"
            stage_state.pop("last_guard_at", None)


def update_state(
    target_dir: Path,
    stage: str,
    manifest: dict[str, Any] | None,
    report: Report,
) -> None:
    path = state_path(target_dir)
    if not path.exists():
        return
    state = json.loads(path.read_text(encoding="utf-8"))
    if manifest is not None:
        manifest["status"] = "completed" if report.passed else "in_progress"
        manifest["updated_at"] = now_iso()
        write_json(manifest_path(target_dir, stage), manifest)
    if stage == "solution_routing" and manifest is not None and report.passed:
        apply_routing_to_state(state, manifest)
    stage_state = state.setdefault("stages", {}).setdefault(stage, {})
    stage_state["guard_status"] = "pass" if report.passed else "fail"
    stage_state["status"] = "completed" if report.passed else "in_progress"
    stage_state["last_guard_at"] = now_iso()
    if manifest is not None and report.passed:
        stage_state["manifest_sha256"] = sha256_file(manifest_path(target_dir, stage))
    else:
        stage_state.pop("manifest_sha256", None)
    state["updated_at"] = now_iso()
    state.setdefault("guard_history", []).append(
        {
            "stage": stage,
            "status": stage_state["guard_status"],
            "checked_at": stage_state["last_guard_at"],
            "errors": report.errors,
            "warnings": report.warnings,
        }
    )
    write_json(path, state)


def print_report(stage: str, report: Report) -> None:
    status = "PASS" if report.passed else "FAIL"
    print(f"metaskill guard {status}: {stage}")
    for message in report.errors:
        print(f"ERROR: {message}")
    for message in report.warnings:
        print(f"WARN: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-dir",
        "--skill-dir",
        dest="target_dir",
        required=True,
        help="Target customization root (legacy alias: --skill-dir)",
    )
    parser.add_argument("--stage", required=True, choices=STAGE_ORDER, help="Stage to validate")
    parser.add_argument(
        "--write-state",
        action="store_true",
        help="Write pass/fail and routing decisions into .metaskill/run_state.json",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    target_dir = Path(args.target_dir).resolve()
    report = Report()
    state = load_json(state_path(target_dir), report)
    manifest = load_json(manifest_path(target_dir, args.stage), report)
    routing = manifest if args.stage == "solution_routing" else load_json(
        manifest_path(target_dir, "solution_routing"), report
    )
    if manifest is not None:
        validate_stage(target_dir, args.stage, state, manifest, routing, report)
    if args.write_state:
        update_state(target_dir, args.stage, manifest, report)
    print_report(args.stage, report)
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
