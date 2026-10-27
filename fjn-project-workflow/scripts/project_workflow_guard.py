#!/usr/bin/env python3
"""Audit fjn-project-workflow ledger, state, views, evidence, and folder registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workflow_core import DEFAULT_CONTROL_DIR, WorkflowError, audit_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, help="Project root containing the control directory")
    parser.add_argument("--control-dir", default=DEFAULT_CONTROL_DIR, help=f"Project-relative control directory (default: {DEFAULT_CONTROL_DIR})")
    parser.add_argument("--no-filesystem", action="store_true", help="Skip existence and unregistered-child checks; ledger/state/view checks still run")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = Path(args.project_root).resolve()
    try:
        report = audit_state(root, args.control_dir, check_filesystem=not args.no_filesystem)
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"project-workflow guard {'PASS' if report.passed else 'FAIL'}")
        for message in report.errors:
            print(f"ERROR: {message}")
        for message in report.warnings:
            print(f"WARN: {message}")
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
