---
name: replace-with-prompt-name
description: 'Run one focused, parameterized task for replace-with-use-case.'
argument-hint: 'replace with expected input'
agent: agent
tools: []
---

# Replace With Focused Task

Perform one clearly bounded task using the user's input.

Return:

1. The requested result.
2. Validation or evidence appropriate to the task.
3. Any unresolved gap.---
name: "Replace With Prompt Name"
description: "Run a focused replace-with-task operation."
argument-hint: "Replace with required inputs"
agent: "agent"
tools: [read, search]
---

Complete this single focused task: ${input:task}

## Output

Return the exact artifact or summary required by the task.
