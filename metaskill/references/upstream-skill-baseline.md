# Upstream Copilot Customization Baseline

This file is a local working baseline adapted from the built-in Copilot agent-customization guidance. It covers the primitive system that `metaskill` can plan and compose. Current VS Code behavior and schemas remain authoritative.

## Choosing The Right Primitive

Use this decision table before creating any Copilot customization composition.

| Need | Better Primitive | Typical Workspace Location |
| --- | --- | --- |
| Always-on project behavior | Agent instructions | `.github/copilot-instructions.md`, root/nested `AGENTS.md`, or compatible `CLAUDE.md` locations |
| File-pattern- or task-specific behavior | File instructions | `.github/instructions/*.instructions.md` or `.claude/rules/` |
| Single focused command with parameters | Prompt | `.github/prompts/*.prompt.md` |
| Deterministic lifecycle enforcement | Hook | `.github/hooks/*.json` or inline custom-agent hooks |
| Context-isolated specialist or restricted tools | Custom agent | `.github/agents/*.agent.md` or `.claude/agents/` |
| Repeatable on-demand workflow with bundled resources | Skill | `.github/skills/<name>/`, `.agents/skills/<name>/`, or `.claude/skills/<name>/` |
| External tools, resources, prompts, or applications | MCP | `.vscode/mcp.json` |

User-profile equivalents are managed in the active VS Code profile. Their exact filesystem locations are runtime-managed and can vary; prefer the relevant VS Code command or Customizations editor instead of guessing a path. User-level Skills can also live under `~/.copilot/skills/<name>/`, `~/.agents/skills/<name>/`, or `~/.claude/skills/<name>/`.

The selected solution can compose primitives. For example, a prompt can be the user-facing command, a Skill can plan the workflow, custom agents can perform isolated stages, hooks can enforce policy, and MCP can expose external capabilities.

## Runtime And Invocation Boundaries

Creating a customization artifact is not the same as executing it.

1. Agent instructions are automatically loaded for their configured scope. Multiple instruction sources may be combined, so avoid conflicting authorities.
2. File instructions are attached when their configured pattern matches or when manually added. Do not promise semantic auto-loading without verifying the installed runtime behavior.
3. Prompts are explicitly run by the user, commonly through slash commands.
4. Hooks run only at matching lifecycle events.
5. Custom agents are selected by the user or invoked as discoverable subagents.
6. Skills are discovered from `name` and `description`, then loaded progressively.
7. MCP tools are available only after configuration, trust, startup, discovery, and tool enablement.

A planner can author all of these and can invoke custom agents or MCP tools already available in its current tool set. A newly created custom agent, hook, or MCP configuration may require a fresh session, lifecycle event, trust confirmation, or server restart before it can be tested end to end.

Skills can also use experimental `context: fork` to run in a dedicated subagent context when supported and enabled. Treat this as a Skill execution mode, not as a replacement for a reusable custom-agent persona with explicit tools or handoffs.

## Primitive Composition Rules

1. Prefer one primitive when one is sufficient.
2. Do not duplicate stable rules across instructions, prompts, agents, and Skills; keep one source of truth and reference it.
3. Use guidance primitives for judgment and hooks for deterministic enforcement.
4. Use MCP only for a real external capability boundary, not merely to wrap a local script that the repository can already execute safely.
5. Keep user entry points few and clear. A composition should normally have one obvious prompt, Skill, or custom agent entry point.
6. Give each custom agent one bounded role and the minimum tools needed.

## Agent Instructions

Prefer one clearly documented project-wide authority. VS Code can combine `.github/copilot-instructions.md`, `AGENTS.md`, compatible `CLAUDE.md`, personal instructions, and organization instructions, but no deterministic ordering should be assumed among combined files. Include only rules relevant to nearly every task and link to detailed project documentation instead of copying it.

## File Instructions

Use `*.instructions.md` for one concern with a useful `description` and, when appropriate, a narrow `applyTo` glob. Without `applyTo`, the current runtime may require manual attachment rather than automatic application. Avoid `applyTo: "**"` unless every matching operation truly requires the content.

## Prompts

Use `*.prompt.md` for a single focused, parameterized task. Keep tool selection minimal. A prompt can select a standard or custom agent and can reference files or tools.

## Hooks

Use hooks for deterministic lifecycle behavior such as blocking dangerous operations, injecting runtime context, or forcing a mechanical check. Hooks receive JSON on stdin and must return the documented output contract. Keep commands small, auditable, sanitized, time-bounded, and free of hardcoded secrets.

Hook availability and inline-agent-hook behavior can depend on the installed VS Code/Copilot version, settings, and organization policy. Inline custom-agent hooks require `chat.useCustomAgentHooks`. Hooks are preview functionality and may be disabled by organization policy. The handoff must distinguish schema validation from actual runtime activation.

## Custom Agents

Use `*.agent.md` for role isolation, specialist context, tool restrictions, or orchestrated handoffs. Keep the description discoverable, constraints explicit, tools minimal, and handoffs acyclic. Validate `agents` together with the `agent` tool, treat `infer` as deprecated, and distinguish VS Code agents from GitHub Copilot coding-agent targets and their `mcp-servers` metadata.

## Skill Directory

Typical skill layout:

```text
skills/<skill-name>/
  SKILL.md
  scripts/
  references/
  templates/
  assets/
```

`SKILL.md` is required. Other directories are optional and should exist only when they carry useful reusable material.

## Frontmatter

Use this shape:

```yaml
---
name: skill-name
description: 'Use when: concrete trigger terms and task description.'
argument-hint: 'optional short hint'
user-invocable: true
---
```

Rules:

1. `name` must be 1-64 characters, lowercase, alphanumeric plus hyphens, and match the folder name.
2. Quote `description` when it contains colons.
3. Keep `description` under 1024 characters.
4. Put discovery keywords in `description`, not only in the body.
5. Use `user-invocable: false` only when the skill should be auto-loaded but hidden from slash-command usage.
6. Use `disable-model-invocation: true` only when the skill should be user-invoked but not automatically selected.
7. Use experimental `context: fork` only when isolated execution is desirable and `github.copilot.chat.skillTool.enabled` is enabled; allowed values are `inline` and `fork`.

## Body Structure

Recommended sections:

1. `When To Use`
2. `When Not To Use`, if confusion is likely
3. `Core Principles`
4. `Workflow` or `Procedure`
5. `Validation`
6. `Output Pattern`
7. `Maintenance Notes`

Keep the body concise. Long examples, schemas, and detailed reference material should move into `./references/` or `./templates/`.

## Progressive Loading

The agent first sees only the skill name and description. It loads the body only when the skill looks relevant. It loads resource files only when the body references them or the task needs them.

Practical rules:

1. Make the description keyword-rich.
2. Keep `SKILL.md` readable and below a few hundred lines when possible.
3. Link local resources with relative `./` paths.
4. Put executable checks in `./scripts/` instead of prose.

## Common Pitfalls

1. Vague descriptions that do not include trigger phrases.
2. Folder name and frontmatter `name` mismatch.
3. Broken YAML caused by unquoted colons or tabs.
4. A monolithic `SKILL.md` that should have references or scripts.
5. Step lists without validation criteria.
6. Relying on instruction text to enforce deterministic constraints that should be checked by a script or hook.
7. Adding hard workflow stages for tiny skills where a simple checklist is enough.

## Baseline Validation Checklist

Before handoff, check:

1. The file is in the intended skill directory.
2. The frontmatter parses and contains `name` plus `description`.
3. The description names when the skill should trigger.
4. Local resource links are valid.
5. Scripts compile or run a small self-test.
6. JSON/YAML templates parse.
7. The final response states how the skill should be invoked and what validation passed.

## MCP Integrations

Workspace MCP servers are configured in `.vscode/mcp.json`; profile configurations are managed through VS Code. Do not hardcode API keys or tokens. Review the server source and command, choose the correct local or remote runtime, consider sandboxing for local stdio servers, and state that user trust and startup may still be required.

MCP can expose tools, read-only resources, prompt templates, and interactive applications. Treat server configuration and implementation as executable supply-chain changes, so they normally require the `gated` metaskill profile.

## Cross-Primitive Validation Checklist

Before handoff:

1. Confirm every artifact is in a supported location and its discovery metadata describes when it should load.
2. Verify every declared local reference exists.
3. Check the invocation graph from entry point through planners, workers, hooks, and external tools.
4. Confirm that the same rule is not maintained independently in multiple primitives.
5. Parse frontmatter or JSON and compile bundled scripts where applicable.
6. Document runtime steps that cannot be completed merely by writing files, including reload, lifecycle trigger, trust, startup, and approval.