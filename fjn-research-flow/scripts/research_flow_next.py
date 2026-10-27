#!/usr/bin/env python3
"""Stage controller for fjn-research-flow runs."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


STAGE_ORDER = [
    "anchor_scope",
    "operation_guide",
    "scouting_evidence",
    "frontier_omission_audit",
    "candidate_admission",
    "metadata_consolidation",
    "analysis_notes",
    "final_report",
]

OPTIONAL_STAGES = ["collection_rule_expansion"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def flow_dir(run_root: Path) -> Path:
    return run_root / ".research_flow"


def state_path(run_root: Path) -> Path:
    return flow_dir(run_root) / "run_state.json"


def manifest_dir(run_root: Path) -> Path:
    return flow_dir(run_root) / "stage_manifests"


def manifest_path(run_root: Path, stage: str) -> Path:
    return manifest_dir(run_root) / f"{stage}.json"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def default_state(run_root: Path) -> dict:
    stamp = now_iso()
    return {
        "schema_version": 2,
        "skill": "fjn-research-flow",
        "run_id": run_root.name or "research-flow-run",
        "run_root": str(run_root),
        "created_at": stamp,
        "updated_at": stamp,
        "active_stage": STAGE_ORDER[0],
        "stage_order": STAGE_ORDER,
        "stages": {
            stage: {"status": "not_started", "guard_status": "not_run"}
            for stage in STAGE_ORDER
        },
        "guard_history": [],
    }


def default_manifest(run_root: Path, stage: str) -> dict:
    return {
        "schema_version": 1,
        "stage": stage,
        "status": "in_progress",
        "updated_at": now_iso(),
        "summary": "",
        "scope": {
            "research_question": "",
            "target_route": "",
            "output_directory": str(run_root),
            "time_windows": {
                "main_window": "",
                "recent_watch_window": "",
                "mature_framework_window": "",
            },
            "candidate_boundaries": {
                "method": "",
                "platform": "",
                "reference": "",
                "non_fit": "",
            },
        },
        "operation_guide": {
            "search_batches": [],
            "sources": [],
            "variant_axes": [],
            "query_axis_expansion": {
                "problem_terms": [],
                "representation_terms": [],
                "mechanism_terms": [],
                "application_terms": [],
                "source_surface_terms": [],
                "negative_or_boundary_terms": [],
                "cross_product_templates": [],
                "narrowness_risks": [],
                "final_query_axes": [],
                "pre_search_review": "",
            },
            "dedup_rules": [],
            "quality_gates": [],
            "completion_criteria": [],
        },
        "scouting_evidence": {
            "paper_searches": [],
            "repository_searches": [],
            "recent_window_checks": [],
            "mature_framework_checks": [],
            "variant_sweeps": [],
            "reverse_output_representation_sweeps": [],
            "candidate_leads": [],
            "negative_findings": [],
            "fallbacks_used": [],
        },
        "frontier_omission_audit": {
            "frontier_windows": {
                "current_year": "",
                "previous_year": "",
                "recent_months": "",
            },
            "top_venue_sources_checked": [],
            "official_source_checks": [],
            "recent_window_queries": [],
            "repository_created_date_sweeps": [],
            "source_failures_and_fallbacks": [],
            "staleness_diagnosis": "",
            "premature_convergence_risk": "",
            "display_filter_plan": "",
            "missing_anchor_replay_checks": [],
            "negative_frontier_findings": [],
            "audit_file": "frontier_omission_audit.md",
        },
        "candidate_admission": {
            "official_source_matrix": [],
            "scouting_dispositions": [],
            "candidates": [],
        },
        "metadata_consolidation": {
            "metadata_md": "metadata.md",
            "metadata_json": "metadata.json",
            "markdown_filter": "",
            "markdown_display": {
                "mode": "filtered",
                "code_backed_gate": "",
                "no_code_gate": "",
                "popularity_gate": "",
                "full_catalog_location": "metadata.json",
                "filtered_out_count": "",
                "override_reason": "",
            },
            "abstract_innovation": {
                "json_field": "abstract_innovation",
                "source_field": "abstract_innovation_source",
                "status_field": "abstract_innovation_status",
                "source_policy": "Prefer paper abstract from official or aggregator sources; if unavailable, use project page or README and mark the fallback explicitly.",
                "missing_abstract_policy": "Do not infer detailed mechanisms from title-only evidence; write a conservative pending-abstract note.",
                "markdown_column": "摘要创新点",
                "markdown_columns": ["名称", "日期 / venue", "发表机构", "核心输出", "输入假设", "热门度", "摘要创新点"],
                "removed_markdown_columns": ["生成模式", "状态 / 备注", "状态/备注"],
            },
            "platform_paper_association": {
                "association_field": "paper_association",
                "source_field": "paper_association_source",
                "status_field": "paper_association_status",
                "required_for_types": ["platform", "platform_tool"],
                "allowed_statuses": [
                    "own_paper",
                    "own_paper_or_project_paper",
                    "related_paper",
                    "related_paper_or_publication_gate",
                    "no_formal_paper_found",
                    "paper_pending",
                ],
                "no_paper_statuses": ["no_formal_paper_found"],
                "source_policy": "Check README, project page, Paper/arXiv/DOI/BibTeX links, and cited published-work dependencies before deciding paper association for any platform/tool entry.",
                "no_paper_claim_policy": "Do not infer absence of a paper from platform/tool classification. Only write no-formal-paper wording after a checked-negative README/project/BibTeX/arXiv/DOI pass is recorded.",
            },
            "sync_notes": "",
        },
        "analysis_notes": {"not_applicable_reason": "", "files": []},
        "final_report": {
            "coverage_by_route": "",
            "recent_results_summary": "",
            "frontier_results_summary": "",
            "official_source_summary": "",
            "mature_framework_summary": "",
            "variant_axes_searched": [],
            "metadata_display_filter_summary": "",
            "staleness_or_saturation_diagnosis": "",
            "completion_blockers_checked": [],
            "likely_omissions": [],
            "recommended_next_phase": "",
        },
        "collection_rule_expansion": {
            "missed_anchor": {},
            "failure_diagnosis": "",
            "new_query_axes": [],
            "validation_queries": [],
            "classification_caution": "",
        },
    }


def ensure_stage_known(stage: str) -> None:
    if stage not in STAGE_ORDER and stage not in OPTIONAL_STAGES:
        allowed = ", ".join(STAGE_ORDER + OPTIONAL_STAGES)
        raise SystemExit(f"Unknown stage '{stage}'. Allowed stages: {allowed}")


def load_state(run_root: Path) -> dict:
    path = state_path(run_root)
    if not path.exists():
        raise SystemExit(f"Run is not initialized: {path}")
    return load_json(path)


def save_state(run_root: Path, state: dict) -> None:
    state["updated_at"] = now_iso()
    write_json(state_path(run_root), state)


def ensure_manifest(run_root: Path, stage: str, overwrite: bool = False) -> Path:
    path = manifest_path(run_root, stage)
    if path.exists() and not overwrite:
        return path
    write_json(path, default_manifest(run_root, stage))
    return path


def previous_required_stage(stage: str) -> str | None:
    if stage not in STAGE_ORDER:
        return None
    index = STAGE_ORDER.index(stage)
    if index == 0:
        return None
    return STAGE_ORDER[index - 1]


def cmd_init(args: argparse.Namespace) -> None:
    run_root = Path(args.run).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    path = state_path(run_root)
    if path.exists() and not args.force:
        print(f"Already initialized: {path}")
        return

    state = default_state(run_root)
    state["stages"][STAGE_ORDER[0]]["status"] = "in_progress"
    write_json(path, state)
    ensure_manifest(run_root, STAGE_ORDER[0], overwrite=args.force)
    print(f"Initialized research-flow run at {flow_dir(run_root)}")


def cmd_enter(args: argparse.Namespace) -> None:
    stage = args.stage
    ensure_stage_known(stage)
    run_root = Path(args.run).resolve()
    state = load_state(run_root)
    previous = previous_required_stage(stage)
    if previous and not args.force:
        previous_guard = state.get("stages", {}).get(previous, {}).get("guard_status")
        if previous_guard != "pass":
            raise SystemExit(
                f"Cannot enter '{stage}' because previous stage '{previous}' guard is '{previous_guard}'. "
                "Run the guard or use --force for a documented user override."
            )

    state.setdefault("stages", {}).setdefault(stage, {"status": "not_started", "guard_status": "not_run"})
    state["active_stage"] = stage
    state["stages"][stage]["status"] = "in_progress"
    state["stages"][stage].setdefault("guard_status", "not_run")
    save_state(run_root, state)
    path = ensure_manifest(run_root, stage)
    print(f"Entered stage '{stage}'. Manifest: {path}")


def cmd_manifest(args: argparse.Namespace) -> None:
    stage = args.stage
    ensure_stage_known(stage)
    run_root = Path(args.run).resolve()
    load_state(run_root)
    path = ensure_manifest(run_root, stage, overwrite=args.force)
    print(path)


def cmd_status(args: argparse.Namespace) -> None:
    run_root = Path(args.run).resolve()
    state = load_state(run_root)
    print(json.dumps(state, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a stage-gated research run")
    init_parser.add_argument("--run", required=True, help="Output directory for the research run")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing flow state")
    init_parser.set_defaults(func=cmd_init)

    enter_parser = subparsers.add_parser("enter", help="Enter a stage after the previous guard passed")
    enter_parser.add_argument("stage", help="Stage name")
    enter_parser.add_argument("--run", required=True, help="Output directory for the research run")
    enter_parser.add_argument("--force", action="store_true", help="Allow documented override of previous guard")
    enter_parser.set_defaults(func=cmd_enter)

    manifest_parser = subparsers.add_parser("manifest", help="Create or show a stage manifest path")
    manifest_parser.add_argument("stage", help="Stage name")
    manifest_parser.add_argument("--run", required=True, help="Output directory for the research run")
    manifest_parser.add_argument("--force", action="store_true", help="Overwrite the manifest template")
    manifest_parser.set_defaults(func=cmd_manifest)

    status_parser = subparsers.add_parser("status", help="Print current flow state")
    status_parser.add_argument("--run", required=True, help="Output directory for the research run")
    status_parser.set_defaults(func=cmd_status)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()