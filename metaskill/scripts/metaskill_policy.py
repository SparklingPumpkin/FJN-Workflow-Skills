#!/usr/bin/env python3
"""Shared routing policy for adaptive metaskill runs."""

from __future__ import annotations

from typing import Any


STAGE_ORDER = [
    "solution_routing",
    "scope_intake",
    "upstream_baseline",
    "migration_audit",
    "local_contract",
    "asset_plan",
    "implementation",
    "validation",
    "handoff",
]

PROFILE_REQUIRED_STAGES = {
    "quick": ["solution_routing", "implementation", "validation", "handoff"],
    "standard": [
        "solution_routing",
        "scope_intake",
        "upstream_baseline",
        "asset_plan",
        "implementation",
        "validation",
        "handoff",
    ],
    "gated": [
        "solution_routing",
        "scope_intake",
        "upstream_baseline",
        "local_contract",
        "asset_plan",
        "implementation",
        "validation",
        "handoff",
    ],
}

REVIEW_REQUIRED_STAGES = {
    "quick": ["solution_routing", "validation", "handoff"],
    "standard": [
        "solution_routing",
        "scope_intake",
        "upstream_baseline",
        "validation",
        "handoff",
    ],
    "gated": [
        "solution_routing",
        "scope_intake",
        "upstream_baseline",
        "local_contract",
        "validation",
        "handoff",
    ],
}

PROFILE_RANK = {"quick": 0, "standard": 1, "gated": 2}

PRIMITIVES = {
    "agent-instructions",
    "file-instructions",
    "prompt",
    "hook",
    "custom-agent",
    "skill",
    "mcp",
}

RISK_FLAGS = [
    "bundled_resources_or_scripts",
    "requires_repository_exploration",
    "migrates_existing_customization",
    "changes_tools_or_trust",
    "handles_secrets_or_untrusted_input",
    "has_external_side_effects",
    "long_running_or_stateful",
    "omission_history",
    "requires_hard_gates",
    "executes_commands",
    "destructive_operations",
    "writes_outside_workspace",
    "network_access",
    "expands_permissions_or_approvals",
]


def selected_primitive_set(route: dict[str, Any]) -> set[str]:
    """Return all top-level and embedded primitives declared by a route."""
    primitives = {
        value for value in route.get("selected_primitives", []) if isinstance(value, str)
    }
    for item in route.get("artifact_plan", []):
        if not isinstance(item, dict):
            continue
        primitive = item.get("primitive")
        if isinstance(primitive, str):
            primitives.add(primitive)
        primitives.update(
            value for value in item.get("embedded_primitives", []) if isinstance(value, str)
        )
    for resource in route.get("supporting_resources", []):
        if isinstance(resource, str):
            normalized = resource.replace("\\", "/")
            if normalized == "mcp.json" or normalized.endswith("/mcp.json"):
                primitives.add("mcp")
    return primitives


def minimum_profile(route: dict[str, Any]) -> tuple[str, list[str]]:
    """Choose the lowest safe profile and explain every escalation factor."""
    primitives = selected_primitive_set(route)
    risks = route.get("risk_assessment", {})
    if not isinstance(risks, dict):
        risks = {}
    reasons: list[str] = []

    gated_flags = [
        "changes_tools_or_trust",
        "handles_secrets_or_untrusted_input",
        "has_external_side_effects",
        "long_running_or_stateful",
        "omission_history",
        "requires_hard_gates",
        "destructive_operations",
        "writes_outside_workspace",
        "expands_permissions_or_approvals",
    ]
    if primitives & {"hook", "mcp"}:
        reasons.append("hooks or MCP integrations require gated review")
    reasons.extend(flag for flag in gated_flags if risks.get(flag) is True)
    if len(primitives) >= 3:
        reasons.append("three or more primitives are coordinated")
    if reasons:
        return "gated", reasons

    standard_flags = [
        "bundled_resources_or_scripts",
        "requires_repository_exploration",
        "migrates_existing_customization",
        "executes_commands",
        "network_access",
    ]
    if "custom-agent" in primitives:
        reasons.append("custom agents require role and tool-boundary review")
    if len(primitives) >= 2:
        reasons.append("multiple primitives are coordinated")
    reasons.extend(flag for flag in standard_flags if risks.get(flag) is True)
    if reasons:
        return "standard", reasons
    return "quick", ["one low-risk static customization artifact"]


def required_stages(profile: str, task_mode: str) -> list[str]:
    """Return required stages for a profile and task mode."""
    profiles = REVIEW_REQUIRED_STAGES if task_mode == "review-only" else PROFILE_REQUIRED_STAGES
    return list(profiles[profile])


def recommended_stages(route: dict[str, Any], profile: str) -> list[str]:
    """Return ordered stages, adding migration audit when the route requires it."""
    task_mode = route.get("task_mode", "create-or-update")
    selected = required_stages(profile, task_mode)
    risks = route.get("risk_assessment", {})
    if isinstance(risks, dict) and risks.get("migrates_existing_customization") is True:
        selected.append("migration_audit")
    return [stage for stage in STAGE_ORDER if stage in selected]