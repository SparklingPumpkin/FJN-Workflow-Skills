# FJN-Workflow-Skills

Independent repository for these sibling skills:

- [fjn-research-flow](fjn-research-flow/SKILL.md)
- [fjn-project-improvement-loop](fjn-project-improvement-loop/SKILL.md)
- [fjn-project-workflow](fjn-project-workflow/SKILL.md)
- [metaskill](metaskill/SKILL.md)

The initial contents come from the server's FJN-Agent checkout, preserving its
existing skill versions. Keep these four directories as siblings so their
relative references remain valid.
Remote: git@github.com:SparklingPumpkin/FJN-Workflow-Skills.git

This repository can be cloned independently or used as the
`skills/workflow-skills` submodule in FJN-Agent. Access each skill directly at
`skills/workflow-skills/<name>/SKILL.md`; no outer `skills/<name>` aliases are kept.

Clone FJN-Agent with `git clone --recurse-submodules`, or initialize this
submodule in an existing checkout with:

```sh
git submodule update --init -- skills/workflow-skills
```

Publish skill changes here first, then commit the updated submodule reference
in FJN-Agent. The parent pins a specific commit, not the latest branch contents.

Do not run the existing server-to-GitHub upload script until it has been adapted
for this nested repository. Publishing these repositories does not adapt that script.
