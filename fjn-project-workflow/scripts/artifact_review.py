"""Deferred artifact review records. This module never deletes artifacts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

CHECKS = {"failed", "no_future_use", "not_historical_mainline", "never_delivered",
          "no_protected_dependents", "reproducible"}
DECISIONS = {"keep", "delete_candidate", "needs_review"}
TERMINAL = {"completed", "failed", "cancelled"}


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result.astimezone(timezone.utc)


def local_file(root, value):
    if not isinstance(value, str) or not value or any(c in value for c in "*?[]"):
        raise ValueError("must name an exact project-relative file, without globs")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("must be project-relative without '..'")
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("must be an existing regular file inside the project (no symlink)")
    return path


def validate_artifact_review(root, state, run_id, review):
    """Validate prospective marks, not present permission or deletion eligibility."""
    errors = []
    run = state.get("runs", {}).get(run_id)
    if not run or run.get("status") not in TERMINAL:
        return ["artifact review requires a terminal registered run"]
    if not isinstance(review, dict):
        return ["artifact review must be an object"]
    if review.get("schema_version") != 1 or review.get("run_id") != run_id:
        errors.append("artifact review schema_version/run_id mismatch")
    if review.get("decision") not in DECISIONS:
        errors.append("decision must be keep, delete_candidate or needs_review")
    if not isinstance(review.get("reason"), str) or not review["reason"].strip():
        errors.append("artifact review needs a reason, including why failed evidence is/is not useful")
    try:
        assessed = utc(review.get("assessed_at", ""))
        due = utc(review.get("review_after", ""))
        ended = utc(run["updated_at"])
        if assessed < ended or assessed > datetime.now(timezone.utc) + timedelta(minutes=5):
            errors.append("assessed_at must be after run termination and not in the future")
        if due < assessed + timedelta(days=7):
            errors.append("review_after must be at least seven days after assessed_at")
    except (ValueError, TypeError, KeyError, AttributeError):
        errors.append("assessed_at/review_after/run.updated_at must be timezone-aware ISO timestamps")
    checks = review.get("checks", {})
    if not isinstance(checks, dict) or set(checks) != CHECKS:
        errors.append("checks must cover: " + ", ".join(sorted(CHECKS)))
        checks = {}
    for key, item in checks.items():
        if not isinstance(item, dict) or (type(item.get("value")) is not bool and item.get("value") != "unknown"):
            errors.append(f"checks.{key} needs boolean/unknown value and evidence")
        elif not isinstance(item.get("evidence"), list) or not item["evidence"] or any(
            not isinstance(x, str) or "::" not in x or not all(y.strip() for y in x.split("::", 1))
            for x in item["evidence"]
        ):
            errors.append(f"checks.{key} needs reference::claim evidence")
    candidate = state.get("candidates", {}).get(run.get("candidate_id"), {})
    if review.get("decision") == "delete_candidate":
        if any(not isinstance(checks.get(k), dict) or checks[k].get("value") is not True for k in CHECKS):
            errors.append("delete_candidate requires every value check true; unknown must remain needs_review")
        historical = any(v.get("promoted_from_candidate_id") == run.get("candidate_id")
                         or v.get("candidate_id") == run.get("candidate_id")
                         for v in state.get("versions", {}).values())
        if candidate.get("status") in {"passed", "promoted"} or historical:
            errors.append("passed/promoted/historical candidate cannot be marked delete_candidate")
    preserve = review.get("preserve", [])
    if not isinstance(preserve, list) or not preserve:
        errors.append("preserve must list permanent evidence and reproduction entry files")
        preserve = []
    for value in preserve:
        try:
            local_file(root, value)
        except ValueError as exc:
            errors.append(f"preserve {value}: {exc}")
    files = review.get("files", [])
    if not isinstance(files, list):
        errors.append("files must be a list")
        files = []
    if review.get("decision") == "delete_candidate" and not files:
        errors.append("delete_candidate needs exact files; never mark an entire experiment directory")
    run_dir = state.get("directories", {}).get(run.get("directory_id"), {}).get("path")
    seen = set()
    protected = set()
    def evidence_paths(value):
        if isinstance(value, dict):
            reference = value.get("reference")
            if isinstance(reference, str):
                path = Path(reference)
                protected.add((path if path.is_absolute() else root / path).resolve())
            for nested in value.values():
                evidence_paths(nested)
        elif isinstance(value, list):
            for nested in value:
                evidence_paths(nested)
    # Preserve registered evidence even when the assessor forgets to list it.
    for collection in ("runs", "candidates", "versions"):
        for record in state.get(collection, {}).values():
            evidence_paths(record.get("evidence", []))
            evidence_paths(record.get("acceptance_report", {}))
    for item in files:
        if not isinstance(item, dict):
            errors.append("file entry must be an object")
            continue
        value = item.get("path")
        try:
            path = local_file(root, value)
            if not run_dir or not path.resolve().is_relative_to((root / run_dir).resolve()):
                raise ValueError("candidate file must belong to this run; shared assets stay unmarked")
            if any(path.resolve() == (root / p).resolve() for p in preserve if isinstance(p, str)) or path.resolve() in seen:
                raise ValueError("file overlaps preserve list or duplicates another entry")
            if path.resolve() in protected:
                raise ValueError("registered evidence must be preserved")
            seen.add(path.resolve())
            stat = path.stat()
            if type(item.get("size_bytes")) is not int or item["size_bytes"] != stat.st_size:
                raise ValueError("size_bytes must equal current file size")
            if type(item.get("mtime_ns")) is not int or item["mtime_ns"] != stat.st_mtime_ns:
                raise ValueError("mtime_ns must equal current file identity")
            for field in ("reason", "rebuild"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ValueError(f"file needs {field}")
        except (ValueError, TypeError) as exc:
            errors.append(f"file {value}: {exc}")
    if review.get("decision") == "keep" and files:
        errors.append("keep must not contain files proposed for deletion")
    return errors


def render_artifact_reviews(state):
    lines = ["# 实验产物清理评估", "", "仅标记，不授权或执行删除。候选至少保留七天；批量清理时重新检查活动、传递依赖、文件身份和最小复现包。", "",
             "| Run | 标记 | 最早复核时间 | 候选字节 | 理由 |", "|---|---|---|---:|---|"]
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    details = []
    for run_id, run in state.get("runs", {}).items():
        if run.get("status") not in TERMINAL:
            continue
        record = run.get("artifact_review")
        if not record:
            if run.get("artifact_review_required"):
                lines.append(f"| {cell(run_id)} | 待评估 | — | 0 | 尚未登记 |")
            continue
        review = record["review"]
        size = sum(x["size_bytes"] for x in review.get("files", []))
        lines.append(f"| {cell(run_id)} | {cell(review['decision'])} | {cell(review['review_after'])} | {size} | {cell(review['reason'])} |")
        details.extend(["", f"## {cell(run_id)}", "", f"评估记录：`{cell(record['reference'])}`；保留：" + ", ".join(f"`{cell(p)}`" for p in review['preserve']), ""])
        for item in review.get("files", []):
            details.append(f"- `{cell(item['path'])}` ({item['size_bytes']} bytes): {cell(item['reason'])}; 重建：{cell(item['rebuild'])}")
    return "\n".join(lines + details) + "\n"
