---
name: replace-with-skill-name
description: 'Use when: replace with concrete trigger terms and task description.'
argument-hint: 'replace with short user-facing hint'
user-invocable: true
# context: fork  # Optional experimental isolation; omit for normal inline loading.
---

# Replace With Skill Title

## When To Use

Use this skill when:

1. Replace with trigger case.
2. Replace with trigger case.

## Core Principles

1. Keep the skill focused on one repeatable workflow.
2. Move long examples into `./references/`.
3. Move deterministic checks into `./scripts/`.

## Workflow

1. Anchor the task and define the completion evidence.
2. Use any relevant instructions attached by the runtime.
3. Invoke only custom agents or MCP tools already available in the current session.
4. Implement the smallest useful change.
5. Validate with the narrowest executable check.
6. Report changed files, validation, and any activation still required.

## Validation

1. Check frontmatter and folder-name match.
2. Run bundled scripts or template parsers if present.
3. State any known gaps.

## Output Pattern

List the files this skill creates or updates.