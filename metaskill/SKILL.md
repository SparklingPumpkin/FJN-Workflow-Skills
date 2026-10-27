---
name: metaskill
description: 'Use when: creating, composing, updating, reviewing, hardening, or debugging Copilot agent customizations, including agent instructions, *.instructions.md, prompts, hooks, custom agents, SKILL.md workflows, and MCP integrations; route each request to the smallest sufficient primitive stack and choose a quick, standard, or gated implementation process.'
argument-hint: 'customization goal, command, workflow, or target path'
user-invocable: true
---

# Metaskill: Central Customization Planner

## Role

`metaskill` is the central planner for a Copilot customization system. “Skill” in its name is an umbrella term, not a restriction to `SKILL.md`.

Use it to design one primitive or a composition of:

1. Agent instructions (`copilot-instructions.md` or `AGENTS.md`) for always-on project rules.
2. File instructions (`*.instructions.md`) for task- or file-scoped guidance.
3. Prompts (`*.prompt.md`) for focused user-invoked commands.
4. Hooks for deterministic lifecycle enforcement.
5. Custom agents (`*.agent.md`) for context isolation, specialist roles, or tool restrictions.
6. Skills (`SKILL.md`) for on-demand workflows with bundled scripts, references, templates, or assets.
7. MCP integrations for external tools, resources, prompts, and applications.

Do not force every request into a new Skill. Choose the smallest sufficient primitive stack from [the upstream customization baseline](./references/upstream-skill-baseline.md). When a Skill is selected, it may remain the central planner and invoke already-available custom agents or MCP tools, while instructions, prompts, hooks, and configuration files shape the surrounding runtime.

## Capability Boundary

This Skill can author, update, validate, and compose all seven primitive types. It can also plan an invocation graph in which one artifact loads or calls another. It can directly invoke only custom agents and MCP tools already exposed in the current session; instructions, prompts, hooks, and newly created integrations are activated by the VS Code runtime rather than called as ordinary tools from `metaskill`.

Newly written artifacts become active through the VS Code runtime:

1. Instructions are discovered and attached according to their scope.
2. Prompts and user-invocable Skills are selected as slash commands.
3. Custom agents are selected manually or invoked as subagents when discoverable.
4. Hooks run at their configured lifecycle events.
5. MCP servers require valid configuration, trust, startup, and tool enablement before their capabilities are callable.

Never claim that writing a file has already invoked it. Never bypass MCP trust, secret handling, tool approval, or hook safety controls.

## Mandatory First Step: Solution Routing

Before creating files, classify the request and record:

1. Desired outcome and trigger phrases.
2. Scope: workspace, user profile, or external integration.
3. Selected primitive or primitive composition.
4. Runtime wiring: who invokes or loads whom.
5. Executable, security, secret, side-effect, and maintenance risks.
6. The minimum sufficient process profile: `quick`, `standard`, or `gated`, computed from the route rather than chosen by intuition alone.
7. Task mode: `create-or-update` or `review-only`.

Do not ask the user to choose a profile unless the risk cannot be inferred. `metaskill` owns the routing decision. Compute the minimum safe profile from the selected primitives and risk assessment; the user may request a heavier profile, but a lighter-than-minimum profile is invalid.

Every artifact plan entry declares `primitive`, `path`, `purpose`, and `embedded_primitives`. A custom agent with inline hooks must declare `hook` as an embedded primitive, which forces the `gated` profile. Hook and MCP configuration files are first-class artifacts, never generic supporting resources.

Use these composition rules:

1. Put stable global policy in agent instructions, not in every Skill.
2. Put file-pattern rules in file instructions.
3. Use a prompt as the user-facing command when the task is single and parameterized.
4. Use a Skill as the planner when the task is multi-step but all steps can share one context and capability set.
5. Delegate a bounded specialist stage to a custom agent when it needs isolated context or restricted tools.
6. Use a hook only when behavior must be enforced deterministically at a lifecycle event.
7. Use MCP only when capabilities or data must cross the local agent boundary.
8. A composition may use a prompt as the entry point, a Skill as the planner, custom agents as workers, hooks as guards, and MCP as the external capability layer.

## Adaptive Process Profiles

Always choose the lowest profile that satisfies the risk and evidence needs. For stateful runs, fill the routing facts first, then run `metaskill_next.py route`; the shared policy computes the minimum profile and exact stage subset. A heavier profile is allowed only with a recorded reason. A lighter profile is rejected.

The mechanical router follows these escalation rules:

1. `quick`: one low-risk static artifact.
2. `standard`: a custom agent, two coordinated primitives, bundled scripts or resources, repository exploration, migration, command execution, or network access.
3. `gated`: hooks or MCP, three or more coordinated primitives, trust or permission changes, secrets or untrusted input, external side effects, destructive or outside-workspace writes, long-running state, omission history, or required hard gates.

The profile may escalate during implementation. It may never be silently downgraded.

### Quick

Use for one small static artifact with clear requirements, no executable behavior, no tool or trust change, and low omission risk. Examples include a concise prompt, scoped instruction, or single-file Skill.

Run only:

1. `solution_routing`
2. `implementation`
3. `validation`
4. `handoff`

Do not create `.metaskill` state by default. Perform the same routing rubric in the working context and include the routing decision and validation result in the handoff. If machine-auditable routing is desired, initialize state and use the router described below; a routed `quick` run still selects only four stages.

For a `review-only` task, omit `implementation`; run `solution_routing`, `validation`, and `handoff`.

Typical `quick` cases are a single static prompt, one narrow instruction file, or a small single-file Skill without scripts. The routing decision and normal validation still happen; only the durable stage bureaucracy is omitted.

### Standard

Use for one bundled Skill, one custom agent, two coordinated primitive types, migration of an existing customization, or work requiring moderate repository exploration without high-risk runtime enforcement.

Run:

1. `solution_routing`
2. `scope_intake`
3. `upstream_baseline`
4. `asset_plan`
5. `implementation`
6. `validation`
7. `handoff`

For `review-only`, omit `asset_plan` and `implementation` unless the user expands the request to include fixes.

Initialize `.metaskill` state when traceability is useful. `local_contract` is optional.

Typical `standard` cases are a Skill with bundled scripts or references, a custom agent, a prompt-plus-Skill pair, or migration work. Add `migration_audit` automatically when an existing customization is being replaced or consolidated.

### Gated

Use the complete workflow when any of these are true:

1. Hooks execute or block lifecycle actions.
2. A new MCP server or external tool integration is added.
3. Credentials, untrusted input, destructive actions, or external side effects are involved.
4. Three or more primitive types must be coordinated.
5. The target workflow is long-running, stateful, failure-prone, or has previously omitted required work.
6. The target itself needs manifests, stage transitions, or hard completion gates.

Run all required stages:

1. `solution_routing`
2. `scope_intake`
3. `upstream_baseline`
4. `local_contract`
5. `asset_plan`
6. `implementation`
7. `validation`
8. `handoff`

For `review-only`, omit `asset_plan` and `implementation`; keep `local_contract` and full validation because the reviewed system is high-risk.

Use `migration_audit` when replacing or consolidating existing customizations.

Escalate immediately from `quick` to `standard` or `gated` when implementation reveals a higher-risk primitive, executable code, unclear ownership, cross-artifact coupling, or missing evidence. Do not downgrade merely to save work.

## Stateful Workflow

For `standard` runs that need traceability and all `gated` runs, state lives under the target customization root:

1. `.metaskill/run_state.json`
2. `.metaskill/stage_manifests/<stage>.json`

Use:

1. `python ./scripts/metaskill_next.py init --target-dir <target_customization_root>`
2. Fill only the routing facts in `solution_routing`: task mode, outcome, triggers, scope, primitives, artifact plan, supporting resources, runtime wiring, and risk assessment. Leave profile, stages, and rationale for the route command.
3. `python ./scripts/metaskill_next.py route --target-dir <target_customization_root>` computes the minimum profile, selected stages, and rationale. Use `--profile <heavier-profile> --override-reason <reason>` only for deliberate extra assurance.
4. `python ./scripts/metaskill_guard.py --target-dir <target_customization_root> --stage <stage> --write-state`
5. `python ./scripts/metaskill_next.py enter <next_selected_stage> --target-dir <target_customization_root>`

The legacy `--skill-dir` argument remains accepted. The routing guard independently recomputes the minimum profile, rejects under-routing, and writes the selected profile and stages into run state; unselected stages become `not_required`.

## Stage Contracts

1. `solution_routing`: choose primitives, artifact paths, runtime wiring, and risks; then compute the minimum profile and selected stages.
2. `scope_intake`: define name, location, users, scope, triggers, and composition purpose.
3. `upstream_baseline`: verify current rules for every selected primitive.
4. `migration_audit`: when selected, record retained behavior, removals, compatibility changes, and new hard gates.
5. `local_contract`: define local constraints, approvals, security controls, state, manifests, guards, and hooks.
6. `asset_plan`: enumerate all files, resources, validation commands, and generated outputs.
7. `implementation`: make the smallest coherent changes without unrelated refactors.
8. `validation`: validate syntax, paths, discovery metadata, scripts, JSON, runtime wiring, and primitive-specific safety.
9. `handoff`: report invocation or activation instructions, changed files, validation, known gaps, and maintenance ownership.

The agent makes semantic decisions. Scripts enforce structure, coverage, stage order, and file consistency. Do not advance or finalize when a selected stage guard fails unless the user explicitly authorizes an override recorded with `--force --override-reason`; disclose every override in the final known gaps.

## Primitive-Specific Validation

Validate only what the selected solution uses:

1. Agent instructions: correct scope, one authoritative project-wide file, concise universally applicable rules.
2. File instructions: frontmatter, meaningful `description`, narrow `applyTo`, and no accidental `"**"` context burn.
3. Prompt: focused task, correct parameters, minimal tools, and valid referenced agent or resources.
4. Hook: valid event and command schema, small auditable command, positive timeout, no embedded secrets, an existing relative command target when statically resolvable, and documented input sanitization and blocking semantics.
5. Custom agent: meaningful description, minimal tools, clear boundaries, valid invocation flags, and no circular handoffs.
6. Skill: required `SKILL.md`, folder/name match, concrete description, progressive loading, `./` resource links, and valid bundled resources.
7. MCP: valid `.vscode/mcp.json` or profile configuration with supported server type and required command or URL, no hardcoded credentials, trusted source review, runtime location, sandbox decision, and explicit user trust/startup handoff.

Validation confirms artifact structure, not runtime availability. For example, a newly authored custom agent is not callable until VS Code discovers it; a hook is not proven active until its lifecycle event fires; and a new MCP server is not callable until the user trusts and starts it.

Start from the matching template only when useful:

1. [Agent instructions](./templates/agent-instructions.template.md)
2. [File instructions](./templates/file-instructions.template.md)
3. [Prompt](./templates/prompt.template.md)
4. [Hook](./templates/hook.template.json)
5. [Custom agent](./templates/custom-agent.template.md)
6. [Skill](./templates/SKILL.template.md)
7. [MCP](./templates/mcp.template.json)

These are examples, not reasons to create every primitive.

For Python scripts, compile them. For JSON artifacts, parse them. For local links and declared artifacts, verify that targets exist.

## Output Pattern

Every handoff states:

1. Selected primitive composition and why simpler alternatives were insufficient.
2. Selected process profile and stages actually run.
3. Runtime invocation or activation path.
4. Files created or changed.
5. Validation performed and evidence produced.
6. Known gaps, approvals still required, and next maintenance step.

## Maintenance Notes

1. Keep this metaskill aligned with current Copilot customization schemas and locations; upstream runtime behavior is authoritative.
2. Keep FJN-specific stage gating as a local hardening layer rather than presenting it as an upstream requirement.
3. Avoid making every micro-step a stage. Add a gate only where omission or unsafe execution is plausible.
4. Treat missed steps as rule-learning cases and improve the routing rubric or guard conservatively.
5. Use [fjn-research-flow](../fjn-research-flow/SKILL.md) only as the local reference implementation for genuinely stage-gated workflows, not as the default complexity target.