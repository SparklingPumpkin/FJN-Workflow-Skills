#!/usr/bin/env python3
"""Print the content digest that proposer and critic must approve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from improvement_loop_policy import ValidationError, artifact_digest, load_json

CONTROL_RELATIVE = Path("docs/improvement-loop")


def review_target(project_root: Path, target: str) -> dict[str, str]:
    control = project_root.resolve() / CONTROL_RELATIVE
    state = load_json(control / "loop_state.json")
    number = state.get("round")
    if not isinstance(number, int) or number < 1:
        raise ValidationError("loop_state.round must be a positive integer")
    current = control / "rounds" / f"round-{number:03d}"
    if target == "design":
        digest = artifact_digest(
            load_json(control / "goal.json"),
            load_json(current / "design.json"),
        )
    else:
        digest = artifact_digest(
            load_json(control / "goal.json"),
            load_json(current / "design.json"),
            load_json(current / "execution.json"),
            load_json(current / "evaluation.json"),
            load_json(current / "evolution.json"),
            load_json(current / "proposed_tree.json"),
        )
    return {"round_id": f"round-{number:03d}", "target_kind": target, "target_digest": digest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--target", required=True, choices=["design", "evolution"])
    args = parser.parse_args()
    try:
        result = review_target(args.project_root, args.target)
    except ValidationError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())