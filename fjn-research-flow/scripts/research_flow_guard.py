#!/usr/bin/env python3
"""Validation guard for fjn-research-flow stage manifests and outputs."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

ALLOWED_CANDIDATE_TYPES = {
    "method",
    "geometry_backbone",
    "init_opt_system",
    "platform_tool",
    "paper_lead",
    "reference",
    "extra_lead",
    "non_fit",
}

ALLOWED_SCOUTING_DISPOSITIONS = {"admit", "reject", "merge", "defer"}

ALLOWED_PLATFORM_PAPER_ASSOCIATION_STATUSES = {
    "own_paper",
    "own_paper_or_project_paper",
    "related_paper",
    "related_paper_or_publication_gate",
    "no_formal_paper_found",
    "paper_pending",
}

NO_FORMAL_PAPER_STATUSES = {"no_formal_paper_found"}


class GuardReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def passed(self) -> bool:
        return not self.errors


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def flow_dir(run_root: Path) -> Path:
    return run_root / ".research_flow"


def state_path(run_root: Path) -> Path:
    return flow_dir(run_root) / "run_state.json"


def manifest_path(run_root: Path, stage: str) -> Path:
    return flow_dir(run_root) / "stage_manifests" / f"{stage}.json"


def load_json(path: Path, report: GuardReport) -> dict[str, Any] | None:
    if not path.exists():
        report.error(f"Missing file: {path}")
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
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


def non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def require_path(payload: dict[str, Any], dotted_path: str, report: GuardReport) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            report.error(f"Missing manifest field: {dotted_path}")
            return None
        current = current[part]
    if not non_empty(current):
        report.error(f"Empty manifest field: {dotted_path}")
    return current


def require_list(payload: dict[str, Any], dotted_path: str, report: GuardReport, min_items: int = 1) -> list[Any]:
    value = require_path(payload, dotted_path, report)
    if not isinstance(value, list):
        report.error(f"Manifest field must be a list: {dotted_path}")
        return []
    if len(value) < min_items:
        report.error(f"Manifest list needs at least {min_items} item(s): {dotted_path}")
    return value


def strip_markdown_link(text: str) -> str:
    text = text.strip()
    match = re.match(r"\[([^\]]+)\]\([^\)]+\)", text)
    if match:
        return match.group(1).strip()
    return re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE).strip(" `*")


def extract_markdown_table_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        first = strip_markdown_link(cells[0])
        if not first or first in {"名称", "Name", "---"} or set(first) <= {"-", ":"}:
            continue
        names.add(first)
    return names


def extract_markdown_table_headers(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    headers: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and cells[0] in {"名称", "Name"}:
            headers.append(cells)
    return headers


def catalog_names(catalog: list[Any]) -> set[str]:
    names: set[str] = set()
    for item in catalog:
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
            names.add(item["name"].strip())
    return names


def normalize_candidate_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def validate_named_records(
    records: list[Any],
    report: GuardReport,
    field_name: str,
    required_fields: list[str],
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            report.error(f"{field_name}[{index}] must be an object")
            continue
        for field in required_fields:
            if not non_empty(record.get(field)):
                report.error(f"{field_name}[{index}] missing {field}")
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        key = normalize_candidate_name(name)
        if key in normalized:
            report.error(f"Duplicate normalized candidate name in {field_name}: {name}")
            continue
        normalized[key] = record
    return normalized


def is_platform_catalog_entry(item: dict[str, Any]) -> bool:
    type_value = str(item.get("type", "")).strip().lower()
    pool_status = str(item.get("pool_status", "")).strip().lower()
    generation_mode = str(item.get("generation_mode", "")).strip().lower()
    return (
        type_value in {"platform", "platform_tool"}
        or pool_status in {"platform", "platform_tool"}
        or "platform" in generation_mode
        or "tool" in generation_mode
        or "viewer" in generation_mode
        or "renderer" in generation_mode
    )


def stringify_items(items: list[Any]) -> str:
    chunks: list[str] = []
    for item in items:
        if isinstance(item, (dict, list)):
            chunks.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
        else:
            chunks.append(str(item))
    return " ".join(chunks)


def validate_anchor_scope(manifest: dict[str, Any], report: GuardReport) -> None:
    require_path(manifest, "scope.research_question", report)
    require_path(manifest, "scope.target_route", report)
    require_path(manifest, "scope.output_directory", report)
    require_path(manifest, "scope.time_windows.main_window", report)
    require_path(manifest, "scope.time_windows.recent_watch_window", report)
    require_path(manifest, "scope.time_windows.mature_framework_window", report)
    require_path(manifest, "scope.candidate_boundaries.method", report)
    require_path(manifest, "scope.candidate_boundaries.platform", report)
    require_path(manifest, "scope.candidate_boundaries.reference", report)
    require_path(manifest, "scope.candidate_boundaries.non_fit", report)


def validate_operation_guide(manifest: dict[str, Any], report: GuardReport) -> None:
    require_list(manifest, "operation_guide.search_batches", report)
    require_list(manifest, "operation_guide.sources", report)
    require_list(manifest, "operation_guide.variant_axes", report)
    require_list(manifest, "operation_guide.query_axis_expansion.problem_terms", report)
    require_list(manifest, "operation_guide.query_axis_expansion.representation_terms", report)
    require_list(manifest, "operation_guide.query_axis_expansion.mechanism_terms", report)
    require_list(manifest, "operation_guide.query_axis_expansion.application_terms", report)
    require_list(manifest, "operation_guide.query_axis_expansion.source_surface_terms", report)
    require_list(manifest, "operation_guide.query_axis_expansion.negative_or_boundary_terms", report)
    require_list(manifest, "operation_guide.query_axis_expansion.cross_product_templates", report)
    require_list(manifest, "operation_guide.query_axis_expansion.narrowness_risks", report)
    require_list(manifest, "operation_guide.query_axis_expansion.final_query_axes", report)
    require_path(manifest, "operation_guide.query_axis_expansion.pre_search_review", report)
    require_list(manifest, "operation_guide.dedup_rules", report)
    require_list(manifest, "operation_guide.quality_gates", report)
    require_list(manifest, "operation_guide.completion_criteria", report)


def validate_scouting_evidence(manifest: dict[str, Any], report: GuardReport) -> None:
    require_list(manifest, "scouting_evidence.paper_searches", report)
    require_list(manifest, "scouting_evidence.repository_searches", report)
    require_list(manifest, "scouting_evidence.recent_window_checks", report)
    require_list(manifest, "scouting_evidence.mature_framework_checks", report)
    require_list(manifest, "scouting_evidence.variant_sweeps", report)
    require_list(manifest, "scouting_evidence.reverse_output_representation_sweeps", report)
    schema_version = manifest.get("schema_version", 1)
    if isinstance(schema_version, int) and schema_version >= 2:
        leads = require_list(manifest, "scouting_evidence.candidate_leads", report)
        validate_named_records(
            leads,
            report,
            "scouting_evidence.candidate_leads",
            ["name", "source", "relevance", "discovery_query"],
        )
    elif "candidate_leads" not in manifest.get("scouting_evidence", {}):
        report.warn("Schema v1 has no scouting_evidence.candidate_leads; migrate to schema v2 to enable silent-drop protection")
    negative_findings = require_path(manifest, "scouting_evidence.negative_findings", report)
    if not isinstance(negative_findings, list):
        report.error("Manifest field must be a list: scouting_evidence.negative_findings")
    if isinstance(negative_findings, list) and not negative_findings:
        report.warn("No checked-negative findings recorded; add one if any source, venue, repo, or weight search came up empty.")


def validate_frontier_omission_audit(run_root: Path, manifest: dict[str, Any], report: GuardReport) -> None:
    require_path(manifest, "frontier_omission_audit.frontier_windows.current_year", report)
    require_path(manifest, "frontier_omission_audit.frontier_windows.previous_year", report)
    require_path(manifest, "frontier_omission_audit.frontier_windows.recent_months", report)
    top_venues = require_list(manifest, "frontier_omission_audit.top_venue_sources_checked", report)
    official_checks = require_list(manifest, "frontier_omission_audit.official_source_checks", report)
    recent_queries = require_list(manifest, "frontier_omission_audit.recent_window_queries", report)
    repo_sweeps = require_list(manifest, "frontier_omission_audit.repository_created_date_sweeps", report)
    require_list(manifest, "frontier_omission_audit.source_failures_and_fallbacks", report)
    require_list(manifest, "frontier_omission_audit.missing_anchor_replay_checks", report)
    require_list(manifest, "frontier_omission_audit.negative_frontier_findings", report)
    require_path(manifest, "frontier_omission_audit.staleness_diagnosis", report)
    require_path(manifest, "frontier_omission_audit.premature_convergence_risk", report)
    require_path(manifest, "frontier_omission_audit.display_filter_plan", report)
    audit_file = require_path(manifest, "frontier_omission_audit.audit_file", report)

    evidence_text = stringify_items(top_venues + official_checks + recent_queries + repo_sweeps)
    if not re.search(r"20\d{2}", evidence_text):
        report.error("frontier_omission_audit evidence must include explicit year-scoped checks")
    official_terms = ["official", "CVF", "OpenAccess", "OpenReview", "proceedings", "README", "project", "project page", "官网", "官方"]
    if not any(term.lower() in evidence_text.lower() for term in official_terms):
        report.error("frontier_omission_audit must include official-source checks, not only aggregator/API searches")

    if isinstance(audit_file, str) and audit_file.strip():
        path = run_root / audit_file
        if not path.exists():
            report.error(f"Missing frontier omission audit file: {path}")


def validate_candidate_admission(run_root: Path, manifest: dict[str, Any], report: GuardReport) -> None:
    require_list(manifest, "candidate_admission.official_source_matrix", report)
    candidates = require_list(manifest, "candidate_admission.candidates", report)
    schema_version = manifest.get("schema_version", 1)
    if isinstance(schema_version, int) and schema_version >= 2:
        scouting_manifest = load_json(manifest_path(run_root, "scouting_evidence"), report)
        leads = (
            require_list(scouting_manifest, "scouting_evidence.candidate_leads", report)
            if scouting_manifest is not None
            else []
        )
        dispositions = require_list(manifest, "candidate_admission.scouting_dispositions", report)
        lead_map = validate_named_records(
            leads,
            report,
            "scouting_evidence.candidate_leads",
            ["name", "source", "relevance", "discovery_query"],
        )
        disposition_map = validate_named_records(
            dispositions,
            report,
            "candidate_admission.scouting_dispositions",
            ["name", "disposition", "reason"],
        )
        for key, record in disposition_map.items():
            disposition = record.get("disposition")
            if disposition not in ALLOWED_SCOUTING_DISPOSITIONS:
                report.error(
                    f"Candidate {record.get('name', key)} has unsupported scouting disposition "
                    f"'{disposition}'. Allowed: {sorted(ALLOWED_SCOUTING_DISPOSITIONS)}"
                )
        missing = sorted(lead_map[key]["name"] for key in lead_map.keys() - disposition_map.keys())
        extra = sorted(disposition_map[key]["name"] for key in disposition_map.keys() - lead_map.keys())
        if missing:
            report.error("Scouting candidate leads missing admission dispositions: " + ", ".join(missing))
        if extra:
            report.error("Admission dispositions have no matching scouting candidate lead: " + ", ".join(extra))
        candidate_names = {
            normalize_candidate_name(candidate["name"])
            for candidate in candidates
            if isinstance(candidate, dict) and isinstance(candidate.get("name"), str) and candidate["name"].strip()
        }
        for key, record in disposition_map.items():
            disposition = record.get("disposition")
            if disposition == "admit" and key not in candidate_names:
                report.error(f"Admitted scouting lead is missing from candidate_admission.candidates: {record.get('name', key)}")
            if disposition == "merge":
                merge_into = record.get("merge_into")
                if not isinstance(merge_into, str) or not merge_into.strip():
                    report.error(f"Merged scouting lead needs merge_into: {record.get('name', key)}")
                elif normalize_candidate_name(merge_into) not in candidate_names:
                    report.error(
                        f"Merged scouting lead target is missing from candidate_admission.candidates: "
                        f"{record.get('name', key)} -> {merge_into}"
                    )
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            report.error(f"candidate_admission.candidates[{index}] must be an object")
            continue
        for field in ["name", "classification", "admission_decision", "evidence_strength"]:
            if not non_empty(candidate.get(field)):
                report.error(f"Candidate {index} missing {field}")
        classification = candidate.get("classification")
        if isinstance(classification, str) and classification not in ALLOWED_CANDIDATE_TYPES:
            allowed = ", ".join(sorted(ALLOWED_CANDIDATE_TYPES))
            report.error(f"Candidate {candidate.get('name', index)} has unknown classification '{classification}'. Allowed: {allowed}")
        if classification == "platform_tool" and candidate.get("admission_decision") == "method_pool":
            report.error(f"Platform/tool candidate cannot be admitted directly to method_pool: {candidate.get('name', index)}")


def validate_metadata_consolidation(run_root: Path, manifest: dict[str, Any], report: GuardReport) -> None:
    meta_info = manifest.get("metadata_consolidation", {})
    require_path(manifest, "metadata_consolidation.markdown_filter", report)
    display_mode = require_path(manifest, "metadata_consolidation.markdown_display.mode", report)
    require_path(manifest, "metadata_consolidation.markdown_display.code_backed_gate", report)
    require_path(manifest, "metadata_consolidation.markdown_display.no_code_gate", report)
    require_path(manifest, "metadata_consolidation.markdown_display.popularity_gate", report)
    require_path(manifest, "metadata_consolidation.markdown_display.full_catalog_location", report)
    require_path(manifest, "metadata_consolidation.markdown_display.filtered_out_count", report)
    abstract_info = require_path(manifest, "metadata_consolidation.abstract_innovation", report)
    platform_paper_info = require_path(manifest, "metadata_consolidation.platform_paper_association", report)
    abstract_json_field = "abstract_innovation"
    abstract_source_field = "abstract_innovation_source"
    platform_association_field = "paper_association"
    platform_association_source_field = "paper_association_source"
    platform_association_status_field = "paper_association_status"
    allowed_platform_statuses = set(ALLOWED_PLATFORM_PAPER_ASSOCIATION_STATUSES)
    no_formal_paper_statuses = set(NO_FORMAL_PAPER_STATUSES)
    expected_columns: list[str] = []
    removed_columns: list[str] = []
    abstract_markdown_column = "摘要创新点"
    if isinstance(abstract_info, dict):
        for field in ["json_field", "source_field", "status_field", "source_policy", "missing_abstract_policy", "markdown_column", "markdown_columns", "removed_markdown_columns"]:
            if not non_empty(abstract_info.get(field)):
                report.error(f"metadata_consolidation.abstract_innovation missing {field}")
        if isinstance(abstract_info.get("json_field"), str) and abstract_info["json_field"].strip():
            abstract_json_field = abstract_info["json_field"].strip()
        if isinstance(abstract_info.get("source_field"), str) and abstract_info["source_field"].strip():
            abstract_source_field = abstract_info["source_field"].strip()
        if isinstance(abstract_info.get("markdown_column"), str) and abstract_info["markdown_column"].strip():
            abstract_markdown_column = abstract_info["markdown_column"].strip()
        if isinstance(abstract_info.get("markdown_columns"), list):
            expected_columns = [str(item).strip() for item in abstract_info["markdown_columns"] if str(item).strip()]
        if isinstance(abstract_info.get("removed_markdown_columns"), list):
            removed_columns = [str(item).strip() for item in abstract_info["removed_markdown_columns"] if str(item).strip()]
    if isinstance(platform_paper_info, dict):
        for field in ["association_field", "source_field", "status_field", "source_policy", "no_paper_claim_policy", "required_for_types", "allowed_statuses"]:
            if not non_empty(platform_paper_info.get(field)):
                report.error(f"metadata_consolidation.platform_paper_association missing {field}")
        if isinstance(platform_paper_info.get("association_field"), str) and platform_paper_info["association_field"].strip():
            platform_association_field = platform_paper_info["association_field"].strip()
        if isinstance(platform_paper_info.get("source_field"), str) and platform_paper_info["source_field"].strip():
            platform_association_source_field = platform_paper_info["source_field"].strip()
        if isinstance(platform_paper_info.get("status_field"), str) and platform_paper_info["status_field"].strip():
            platform_association_status_field = platform_paper_info["status_field"].strip()
        if isinstance(platform_paper_info.get("allowed_statuses"), list) and platform_paper_info["allowed_statuses"]:
            allowed_platform_statuses = {str(item).strip() for item in platform_paper_info["allowed_statuses"] if str(item).strip()}
        if isinstance(platform_paper_info.get("no_paper_statuses"), list) and platform_paper_info["no_paper_statuses"]:
            no_formal_paper_statuses = {str(item).strip() for item in platform_paper_info["no_paper_statuses"] if str(item).strip()}
    if isinstance(display_mode, str):
        allowed_modes = {"filtered", "full", "custom"}
        if display_mode not in allowed_modes:
            report.error(f"metadata_consolidation.markdown_display.mode must be one of {sorted(allowed_modes)}")
        if display_mode == "full" and not non_empty(meta_info.get("markdown_display", {}).get("override_reason")):
            report.error("Full metadata.md display requires metadata_consolidation.markdown_display.override_reason")
    metadata_md_name = meta_info.get("metadata_md") or "metadata.md"
    metadata_json_name = meta_info.get("metadata_json") or "metadata.json"
    metadata_md = run_root / metadata_md_name
    metadata_json = run_root / metadata_json_name
    data = load_json(metadata_json, report)
    if not metadata_md.exists():
        report.error(f"Missing file: {metadata_md}")
    if data is None:
        return

    forbidden_arrays = ["papers_methods", "repositories_projects_platforms", "candidate_papers", "candidate_repos"]
    for key in forbidden_arrays:
        if isinstance(data.get(key), list):
            report.error(f"metadata.json should use one top-level catalog array, not '{key}'")

    catalog = data.get("catalog")
    if not isinstance(catalog, list) or not catalog:
        report.error("metadata.json must contain a non-empty top-level catalog array")
        return

    names = catalog_names(catalog)
    if len(names) != len(catalog):
        report.warn("Some metadata.json catalog entries are missing unique non-empty names")

    schema_version = manifest.get("schema_version", 1)
    if isinstance(schema_version, int) and schema_version >= 2:
        admission_manifest = load_json(manifest_path(run_root, "candidate_admission"), report)
        admitted_candidates = (
            admission_manifest.get("candidate_admission", {}).get("candidates", [])
            if admission_manifest is not None
            else []
        )
        catalog_keys = {normalize_candidate_name(name) for name in names}
        missing_catalog = sorted(
            candidate["name"]
            for candidate in admitted_candidates
            if isinstance(candidate, dict)
            and isinstance(candidate.get("name"), str)
            and candidate["name"].strip()
            and candidate.get("classification") != "non_fit"
            and normalize_candidate_name(candidate["name"]) not in catalog_keys
        )
        if missing_catalog:
            report.error("Candidate admission entries missing from metadata.json catalog: " + ", ".join(missing_catalog))

    for index, item in enumerate(catalog, start=1):
        if not isinstance(item, dict):
            report.error(f"metadata.json catalog[{index}] must be an object")
            continue
        label = item.get("name", f"catalog[{index}]")
        for field in ["name", "type", "priority", "core_output"]:
            if not non_empty(item.get(field)):
                report.error(f"metadata.json entry '{label}' missing {field}")
        if not non_empty(item.get(abstract_json_field)):
            report.error(f"metadata.json entry '{label}' missing {abstract_json_field}")
        if not non_empty(item.get(abstract_source_field)):
            report.error(f"metadata.json entry '{label}' missing {abstract_source_field}")
        if is_platform_catalog_entry(item):
            for field in [platform_association_status_field, platform_association_field, platform_association_source_field]:
                if not non_empty(item.get(field)):
                    report.error(f"Platform metadata entry '{label}' missing {field}")
            status = str(item.get(platform_association_status_field, "")).strip()
            if status and status not in allowed_platform_statuses:
                allowed = ", ".join(sorted(allowed_platform_statuses))
                report.error(f"Platform metadata entry '{label}' has unsupported {platform_association_status_field}='{status}'. Allowed: {allowed}")
            abstract_text = str(item.get(abstract_json_field, ""))
            abstract_lower = abstract_text.lower()
            if "平台项无论文摘要" in abstract_text:
                report.error(f"Platform metadata entry '{label}' uses blanket no-paper wording; run repo-to-paper linkage checks instead")
            if any(phrase in abstract_lower for phrase in ["无论文摘要", "no-paper", "no paper"]) and status not in no_formal_paper_statuses:
                report.error(f"Platform metadata entry '{label}' makes a no-paper claim without a no-formal-paper checked status")
            if status in no_formal_paper_statuses:
                source_text = f"{item.get(platform_association_field, '')} {item.get(platform_association_source_field, '')}".lower()
                checked_terms = ["readme", "project", "bibtex", "arxiv", "doi", "official", "checked", "核验"]
                if not any(term in source_text for term in checked_terms):
                    report.error(f"Platform metadata entry '{label}' claims no formal paper but does not record a checked source surface")
        if not non_empty(item.get("status_notes")) and not non_empty(item.get("pool_status")):
            report.error(f"metadata.json entry '{label}' needs status_notes or pool_status")
        repo_text = " ".join(
            str(item.get(field, ""))
            for field in ["repo_project", "repository", "repo_url", "project_url"]
        )
        if "github.com" in repo_text.lower():
            for field in ["stars", "created_at"]:
                if item.get(field) in (None, "", "N/A"):
                    report.error(f"GitHub-backed entry '{label}' missing {field}")
            if item.get("stars_per_month") in (None, "", "N/A"):
                report.warn(f"GitHub-backed entry '{label}' missing stars_per_month")

    if metadata_md.exists():
        md_names = extract_markdown_table_names(metadata_md)
        if not md_names:
            report.warn("No Markdown catalog table names detected in metadata.md")
        headers = extract_markdown_table_headers(metadata_md)
        if not headers:
            report.warn("No Markdown catalog table headers detected in metadata.md")
        for header in headers:
            if abstract_markdown_column not in header:
                report.error(f"metadata.md table header missing required column: {abstract_markdown_column}")
            for removed in removed_columns:
                if removed in header:
                    report.error(f"metadata.md table header still contains removed column: {removed}")
            if expected_columns and header != expected_columns:
                report.error(f"metadata.md table header does not match required columns: {header} != {expected_columns}")
        extra_names = sorted(md_names - names)
        if extra_names:
            report.error("metadata.md displays names not present in metadata.json catalog: " + ", ".join(extra_names[:20]))

    any_stars = any(isinstance(item, dict) and item.get("stars") not in (None, "", "N/A") for item in catalog)
    if any_stars:
        scoring = data.get("popularity_scoring")
        if not isinstance(scoring, dict):
            report.error("metadata.json needs popularity_scoring when any catalog entry records stars")
        else:
            for field in ["scoring_date", "formula", "max_stars", "max_stars_per_month"]:
                if not non_empty(scoring.get(field)):
                    report.error(f"metadata.json popularity_scoring missing {field}")


def validate_analysis_notes(run_root: Path, manifest: dict[str, Any], report: GuardReport) -> None:
    notes = manifest.get("analysis_notes", {})
    files = notes.get("files", [])
    not_applicable = notes.get("not_applicable_reason")
    if not files and not non_empty(not_applicable):
        report.error("analysis_notes needs files or not_applicable_reason")
        return
    if not files:
        return
    if not isinstance(files, list):
        report.error("analysis_notes.files must be a list")
        return

    metadata_json = run_root / "metadata.json"
    data = load_json(metadata_json, report)
    catalog = data.get("catalog", []) if data else []
    names = catalog_names(catalog if isinstance(catalog, list) else [])
    registered = set(data.get("analysis_files", [])) if data and isinstance(data.get("analysis_files"), list) else set()

    for file_name in files:
        if not isinstance(file_name, str) or not file_name.strip():
            report.error("analysis_notes.files contains an empty file name")
            continue
        path = run_root / file_name
        if not path.exists():
            report.error(f"Missing analysis file: {path}")
            continue
        if file_name not in registered:
            report.warn(f"Analysis file is not registered in metadata.json analysis_files: {file_name}")
        text = path.read_text(encoding="utf-8")
        if file_name in {"method_innovation_notes.md", "technical_evolution.md"}:
            missing = sorted(name for name in names if name not in text)
            if missing:
                report.error(f"{file_name} does not mention every metadata catalog name. Missing: {', '.join(missing[:20])}")
        if file_name == "technical_evolution.md" and "FF-GS" not in text:
            report.warn("technical_evolution.md should explicitly distinguish FF-GS when relevant")


def validate_final_report(manifest: dict[str, Any], state: dict[str, Any] | None, report: GuardReport) -> None:
    require_path(manifest, "final_report.coverage_by_route", report)
    require_path(manifest, "final_report.recent_results_summary", report)
    require_path(manifest, "final_report.frontier_results_summary", report)
    require_path(manifest, "final_report.official_source_summary", report)
    require_path(manifest, "final_report.mature_framework_summary", report)
    require_list(manifest, "final_report.variant_axes_searched", report)
    require_path(manifest, "final_report.metadata_display_filter_summary", report)
    require_path(manifest, "final_report.staleness_or_saturation_diagnosis", report)
    require_list(manifest, "final_report.completion_blockers_checked", report)
    require_path(manifest, "final_report.likely_omissions", report)
    require_path(manifest, "final_report.recommended_next_phase", report)
    if not state:
        return
    for stage in STAGE_ORDER[:-1]:
        guard_status = state.get("stages", {}).get(stage, {}).get("guard_status")
        if guard_status != "pass":
            report.error(f"Cannot finalize: previous stage '{stage}' guard_status is '{guard_status}'")


def validate_collection_rule_expansion(manifest: dict[str, Any], report: GuardReport) -> None:
    require_path(manifest, "collection_rule_expansion.missed_anchor", report)
    require_path(manifest, "collection_rule_expansion.failure_diagnosis", report)
    require_list(manifest, "collection_rule_expansion.new_query_axes", report)
    require_list(manifest, "collection_rule_expansion.validation_queries", report)
    require_path(manifest, "collection_rule_expansion.classification_caution", report)


def validate_stage(run_root: Path, stage: str, state: dict[str, Any] | None, manifest: dict[str, Any], report: GuardReport) -> None:
    manifest_stage = manifest.get("stage")
    if manifest_stage != stage:
        report.error(f"Manifest stage is '{manifest_stage}', expected '{stage}'")
    if stage == "anchor_scope":
        validate_anchor_scope(manifest, report)
    elif stage == "operation_guide":
        validate_operation_guide(manifest, report)
    elif stage == "scouting_evidence":
        validate_scouting_evidence(manifest, report)
    elif stage == "frontier_omission_audit":
        validate_frontier_omission_audit(run_root, manifest, report)
    elif stage == "candidate_admission":
        validate_candidate_admission(run_root, manifest, report)
    elif stage == "metadata_consolidation":
        validate_metadata_consolidation(run_root, manifest, report)
    elif stage == "analysis_notes":
        validate_analysis_notes(run_root, manifest, report)
    elif stage == "final_report":
        validate_final_report(manifest, state, report)
    elif stage == "collection_rule_expansion":
        validate_collection_rule_expansion(manifest, report)
    else:
        allowed = ", ".join(STAGE_ORDER + OPTIONAL_STAGES)
        report.error(f"Unknown stage '{stage}'. Allowed stages: {allowed}")


def update_state(run_root: Path, stage: str, report: GuardReport) -> None:
    path = state_path(run_root)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    stage_state = state.setdefault("stages", {}).setdefault(stage, {})
    stage_state["guard_status"] = "pass" if report.passed else "fail"
    stage_state["status"] = "completed" if report.passed else "in_progress"
    stage_state["last_guard_at"] = now_iso()
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


def print_report(stage: str, report: GuardReport) -> None:
    status = "PASS" if report.passed else "FAIL"
    print(f"research-flow guard {status}: {stage}")
    for message in report.errors:
        print(f"ERROR: {message}")
    for message in report.warnings:
        print(f"WARN: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="Output directory for the research run")
    parser.add_argument("--stage", required=True, help="Stage name to validate")
    parser.add_argument("--write-state", action="store_true", help="Write pass/fail status into .research_flow/run_state.json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_root = Path(args.run).resolve()
    stage = args.stage
    report = GuardReport()
    state = load_json(state_path(run_root), report)
    manifest = load_json(manifest_path(run_root, stage), report)
    if manifest is not None:
        validate_stage(run_root, stage, state, manifest, report)
    if args.write_state:
        update_state(run_root, stage, report)
    print_report(stage, report)
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()