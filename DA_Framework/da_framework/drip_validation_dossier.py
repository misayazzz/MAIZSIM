"""Build a reviewer-facing evidence dossier for MAIZSIM drip validation."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd


DEFAULT_IMPLEMENTATION_BASE_COMMIT = "199627a4a68e464dfd7c31d2cc65f1de26b54972"

PRECISION_ARTIFACTS = (
    "precision_validation_checks.csv",
    "precision_spatial_delta_root.csv",
    "precision_spatial_temporal_delta_root.csv",
    "precision_spatial_worst_cases.csv",
    "precision_delta_theta_root_overlay_0601.png",
    "precision_root_density_0601.png",
    "precision_delta_theta_root_timeline.png",
    "precision_root_density_timeline.png",
    "precision_spatial_delta_root_matrix.png",
    "precision_spatial_worst_case_delta_root.png",
    "precision_spatial_temporal_storage.png",
    "precision_fixed_domain_grid_refinement.png",
    "precision_centered_hydrus_curve_width.png",
    "precision_timestep_convergence.png",
    "precision_spatial_shape_metrics.png",
)

EXTERNAL_ARTIFACT_PATTERNS = (
    "*_summary.csv",
    "*_points.csv",
    "*_fields.png",
    "*_manifest.json",
    "*_audit.json",
    "*_outputs.json",
)

SUITE_ARTIFACT_KEYS = (
    "suite_manifest",
    "cases_csv",
    "metric_summary_csv",
    "metric_panel_figure",
    "journal_readiness_report",
)


def main(arguments=None):
    args = _parse_args(arguments)
    dossier = build_validation_dossier(
        readiness_report=args.readiness_report,
        output_dir=args.output_dir,
        title=args.title,
        suite_report=args.suite_report,
        implementation_base_commit=args.implementation_base_commit,
        include_implementation_history=not args.no_implementation_history,
    )
    if arguments is None:
        print(json.dumps(dossier, indent=2, ensure_ascii=False))
    return 0


def build_validation_dossier(
    readiness_report,
    output_dir,
    *,
    title=None,
    suite_report=None,
    implementation_base_commit=DEFAULT_IMPLEMENTATION_BASE_COMMIT,
    include_implementation_history=True,
):
    """Write JSON and Markdown dossiers from a journal-readiness report."""
    report_path = Path(readiness_report).expanduser().resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    checks_path = Path(report["checks_csv"])
    checks = pd.read_csv(checks_path)
    precision_dir = Path(report["precision_dir"])
    external_dirs = [Path(item) for item in report.get("external_comparison_dirs", [])]

    precision_artifacts = _precision_artifacts(precision_dir)
    external_artifacts = _external_artifacts(external_dirs)
    suite_artifacts = _suite_artifacts(_resolve_suite_report(report_path, suite_report))
    implementation_history = (
        _implementation_history(implementation_base_commit)
        if include_implementation_history
        else {"status": "not_requested"}
    )
    issue_rows = _issue_rows(checks)
    summary = {
        "overall_status": report["overall_status"],
        "status_counts": report.get("status_counts", {}),
        "precision_dir": str(precision_dir),
        "external_comparison_count": len(external_dirs),
        "thresholds": report.get("thresholds", {}),
        "blocking_checks": [
            row
            for row in issue_rows
            if row["status"] in ("fail", "missing_external_evidence")
        ],
    }
    reviewer_evidence_matrix = _reviewer_evidence_matrix(
        checks,
        summary,
        precision_artifacts,
        external_artifacts,
        suite_artifacts,
        implementation_history,
    )
    dossier = {
        "title": title or "MAIZSIM drip validation evidence dossier",
        "readiness_report": str(report_path),
        "readiness_checks_csv": str(checks_path),
        "summary": summary,
        "reviewer_evidence_matrix": reviewer_evidence_matrix,
        "precision_artifacts": precision_artifacts,
        "external_artifacts": external_artifacts,
        "suite_artifacts": suite_artifacts,
        "implementation_history": implementation_history,
        "issue_checks": issue_rows,
    }

    json_path = output_path / "drip_validation_dossier.json"
    markdown_path = output_path / "drip_validation_dossier.md"
    dossier["json_path"] = str(json_path)
    dossier["markdown_path"] = str(markdown_path)
    json_path.write_text(
        json.dumps(dossier, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown_path.write_text(_dossier_markdown(dossier), encoding="utf-8")
    return dossier


def _reviewer_evidence_matrix(
    checks,
    summary,
    precision_artifacts,
    external_artifacts,
    suite_artifacts,
    implementation_history,
):
    external_count = int(summary["external_comparison_count"])
    return [
        _implementation_matrix_row(implementation_history),
        _checks_matrix_row(
            checks,
            "Water accounting",
            "Do drip demand, source input/loss, and boundary acceptance close numerically?",
            (
                "required_precision_demand_input_pressure_residual_abs_max_mm",
                "required_precision_source_input_loss_residual_abs_max_mm",
                "required_precision_boundary_acceptance_residual_abs_max_mm",
            ),
            "Internal G05 accounting checks pass for demand, direct-source, and boundary-flow water balance.",
            "Retain these checks when external comparison runs are added.",
        ),
        _checks_matrix_row(
            checks,
            "2D spatial wetting-root evidence",
            "Do 2D water-content changes align with roots across soils, grids, and drip scenarios?",
            (
                "root_zone_spatial_record_count",
                "root_zone_spatial_soil_count",
                "root_zone_spatial_grid_count",
                "root_zone_spatial_scenario_count",
                "root_zone_positive_delta_root_overlap_fraction_min",
                "root_zone_positive_delta_root_storage_fraction_min",
                "required_precision_spatial_worst_case_count",
            ),
            (
                "Spatial delta-theta/root CSV diagnostics cover the full internal "
                "matrix; companion 2D figures include representative panels, "
                "matrix panels, and a worst-case plate to reduce cherry-picking risk."
            ),
            "External 2D field comparisons are still required for publication-grade validation.",
            artifacts=precision_artifacts,
            artifact_names=(
                "precision_delta_theta_root_overlay_0601.png",
                "precision_root_density_0601.png",
                "precision_delta_theta_root_timeline.png",
                "precision_root_density_timeline.png",
                "precision_spatial_delta_root_matrix.png",
                "precision_spatial_worst_cases.csv",
                "precision_spatial_worst_case_delta_root.png",
                "precision_spatial_shape_metrics.png",
            ),
        ),
        _checks_matrix_row(
            checks,
            "2D temporal process evidence",
            "Is the wetting-root relationship stable through time rather than only on one plate date?",
            (
                "root_zone_spatial_temporal_case_count",
                "root_zone_spatial_temporal_date_count_min",
                "root_zone_spatial_temporal_positive_storage_case_count",
                "root_zone_spatial_temporal_root_active_case_count",
                "root_zone_spatial_temporal_root_storage_fraction_min",
            ),
            (
                "Temporal CSV diagnostics cover all active cases with multi-date "
                "storage and root-overlap checks; the companion figure summarizes "
                "time-varying storage rather than every 2D field."
            ),
            "External time-series theta fields would strengthen this beyond internal evidence.",
            artifacts=precision_artifacts,
            artifact_names=(
                "precision_spatial_temporal_delta_root.csv",
                "precision_delta_theta_root_timeline.png",
                "precision_root_density_timeline.png",
                "precision_spatial_temporal_storage.png",
            ),
        ),
        _checks_matrix_row(
            checks,
            "Numerical robustness",
            "Are timestep and grid effects bounded for the drip wetting response?",
            (
                "required_precision_accepted_timestep_actual_infil_rel_error_max",
                "required_precision_accepted_timestep_hydraulic_excess_rel_error_max",
                "required_precision_fixed_domain_factor2_actual_infil_rel_error_max",
                "required_precision_fixed_domain_factor2_hydraulic_excess_abs_error_max_mm",
                "required_precision_fixed_domain_factor2_wet_width_abs_error_max_cm",
            ),
            "Timestep convergence and fixed-domain grid-refinement checks pass.",
            "External reference fields remain needed to turn robustness into independent validation.",
            artifacts=precision_artifacts,
            artifact_names=(
                "precision_fixed_domain_grid_refinement.png",
                "precision_timestep_convergence.png",
            ),
        ),
        _external_matrix_row(
            checks,
            external_count,
            external_artifacts,
            suite_artifacts,
        ),
        _external_audit_matrix_row(
            checks,
            external_count,
            external_artifacts,
        ),
    ]


def _implementation_matrix_row(implementation_history):
    dirty_count = int(implementation_history.get("dirty_worktree_entry_count", 0) or 0)
    history_available = implementation_history.get("status") == "available"
    commit_count = int(implementation_history.get("commit_count", 0) or 0)
    if not history_available or commit_count <= 0:
        status = "fail"
        remaining_gap = (
            "Implementation history could not be traced from the requested "
            "base commit."
        )
    elif dirty_count > 0:
        status = "diagnostic"
        remaining_gap = (
            f"Working tree has {dirty_count} uncommitted entries; freeze or "
            "commit the final evidence package before citing this dossier as "
            "a reproducibility record."
        )
    else:
        status = "pass"
        remaining_gap = "No implementation-history gap in this dossier."
    return _matrix_row(
        "Implementation traceability",
        "Can the drip module implementation be traced from the requested base commit?",
        status,
        (
            "Git history from the requested base commit to HEAD is indexed, "
            "including commit sequence, changed-file areas, and dirty worktree entries."
        ),
        remaining_gap,
        "implementation_history",
    )


def _checks_matrix_row(
    checks,
    criterion,
    question,
    check_names,
    evidence,
    remaining_gap,
    *,
    artifacts=None,
    artifact_names=(),
):
    statuses = [_check_status(checks, name) for name in check_names]
    missing_checks = [
        name for name, status in zip(check_names, statuses) if status == "missing"
    ]
    artifact_missing = [
        name
        for name in artifact_names
        if not _artifact_exists(artifacts or (), name)
    ]
    status = _combined_status(statuses, bool(artifact_missing))
    if missing_checks:
        remaining_gap = f"Missing readiness checks: {', '.join(missing_checks)}."
    elif artifact_missing:
        remaining_gap = f"Missing evidence artifacts: {', '.join(artifact_missing)}."
    return _matrix_row(
        criterion,
        question,
        status,
        evidence,
        remaining_gap,
        ", ".join(check_names),
    )


def _external_matrix_row(checks, external_count, external_artifacts, suite_artifacts):
    if external_count == 0:
        return _matrix_row(
            "Independent external 2D field validation",
            "Do independent HYDRUS-2D or measured 2D theta fields reproduce the MAIZSIM wetting body?",
            "missing_external_evidence",
            "No external comparison directories were supplied to the readiness gate.",
            (
                "Add multiple same-condition HYDRUS/measured 2D theta-field cases "
                "with event-relative output times, point residuals, summary "
                "metrics, figures, manifests, and audits."
            ),
            "external_2d_field_comparison_present",
        )
    statuses = [
        str(row["status"])
        for _, row in checks.iterrows()
        if str(row["check"]).startswith("external_")
    ]
    status = _combined_status(statuses, False)
    return _matrix_row(
        "Independent external 2D field validation",
        "Do independent HYDRUS-2D or measured 2D theta fields reproduce the MAIZSIM wetting body?",
        status,
        (
            f"{external_count} external comparison directories are indexed; "
            f"{len(external_artifacts)} case artifacts and {len(suite_artifacts)} suite artifacts are listed."
        ),
        "All external thresholds must pass before journal readiness can be claimed.",
        "external_* readiness checks",
    )


def _external_audit_matrix_row(checks, external_count, external_artifacts):
    if external_count == 0:
        return _matrix_row(
            "External reproducibility and audit trail",
            "Can an external validation case be rerun from archived inputs and metadata?",
            "missing_external_evidence",
            "The manifest schema and audit validators are in place, but no external case artifacts are indexed.",
            (
                "Provide non-placeholder comparison manifests, solver-coupling "
                "metadata, structured HYDRUS/measured reference provenance, "
                "HYDRUS mass-balance or measured-instrument QA metadata, "
                "audited selected times, input hashes, and raw reference "
                "hashes, outputs-index paths that match the archived artifacts, "
                "point- and "
                "reference-recomputed summary metrics, non-relaxed journal "
                "thresholds, observation uncertainty, source-connected "
                "wet-body metrics, and storage metrics."
            ),
            (
                "manifest/reference-provenance/audit/outputs-index/"
                "points-reference-recomputation/threshold-policy readiness "
                "checks"
            ),
        )
    audit_statuses = [
        str(row["status"])
        for _, row in checks.iterrows()
        if "audit" in str(row["check"])
        or "manifest" in str(row["check"])
        or "outputs_index" in str(row["check"])
        or "summary_matches_points" in str(row["check"])
        or "summary_matches_reference" in str(row["check"])
        or "threshold_policy" in str(row["check"])
        or "uncertainty" in str(row["check"])
        or "storage" in str(row["check"])
    ]
    return _matrix_row(
        "External reproducibility and audit trail",
        "Can an external validation case be rerun from archived inputs and metadata?",
        _combined_status(audit_statuses, False),
        f"{len(external_artifacts)} external artifacts are indexed for audit review.",
        (
            "All manifest, reference-provenance, uncertainty, storage, "
            "audit-hash, and outputs-index checks must pass; summary metrics "
            "must reproduce from points and audited reference fields, and "
            "journal quality thresholds must not be relaxed."
        ),
        (
            "manifest/reference-provenance/audit/outputs-index/"
            "points-reference-recomputation/threshold-policy/uncertainty/"
            "storage checks"
        ),
    )


def _matrix_row(criterion, question, status, evidence, remaining_gap, source):
    return {
        "criterion": criterion,
        "reviewer_question": question,
        "status": status,
        "evidence": evidence,
        "remaining_gap": remaining_gap,
        "source": source,
    }


def _check_status(checks, name):
    match = checks[checks["check"].astype(str) == str(name)]
    if match.empty:
        return "missing"
    return str(match.iloc[0]["status"])


def _combined_status(statuses, artifact_missing):
    normalized = [str(status) for status in statuses]
    if artifact_missing or "fail" in normalized or "missing" in normalized:
        return "fail"
    if "missing_external_evidence" in normalized:
        return "missing_external_evidence"
    if "review" in normalized or "diagnostic" in normalized:
        return "diagnostic"
    return "pass"


def _artifact_exists(artifacts, name):
    for item in artifacts:
        if str(item["name"]) == str(name):
            return bool(item["exists"])
    return False


def _implementation_history(base_commit):
    repo = Path(__file__).resolve().parents[2]
    try:
        head_commit = _git(repo, "rev-parse", "HEAD")
        commits_text = _git(
            repo,
            "log",
            "--reverse",
            "--pretty=format:%H%x1f%h%x1f%s",
            f"{base_commit}..HEAD",
        )
        changed_files_text = _git(
            repo,
            "diff",
            "--name-only",
            f"{base_commit}..HEAD",
        )
        dirty_text = _git(repo, "status", "--short")
    except Exception as exc:
        return {
            "status": "unavailable",
            "base_commit": str(base_commit),
            "error": str(exc),
        }

    commits = []
    for line in commits_text.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        commit, short_commit, subject = parts
        commits.append(
            {
                "commit": commit,
                "short_commit": short_commit,
                "subject": subject,
            }
        )
    changed_files = [
        line.strip()
        for line in changed_files_text.splitlines()
        if line.strip()
    ]
    dirty_entries = [
        line.rstrip()
        for line in dirty_text.splitlines()
        if line.strip()
    ]
    return {
        "status": "available",
        "base_commit": str(base_commit),
        "head_commit": head_commit,
        "commit_count": len(commits),
        "commits": commits,
        "changed_file_count": len(changed_files),
        "changed_files_by_area": _changed_files_by_area(changed_files),
        "dirty_worktree_entry_count": len(dirty_entries),
        "dirty_worktree_entries": dirty_entries,
    }


def _git(repo, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _changed_files_by_area(changed_files):
    areas = {}
    for path in changed_files:
        area = _implementation_area(path)
        areas[area] = areas.get(area, 0) + 1
    return [
        {"area": area, "file_count": count}
        for area, count in sorted(areas.items())
    ]


def _implementation_area(path):
    normalized = str(path).replace("\\", "/")
    if normalized.startswith("Soil Source/"):
        return "soil-water Fortran implementation"
    if normalized.startswith("Crop source/"):
        return "crop/root Fortran coupling"
    if normalized.startswith("DA_Framework/da_framework/"):
        return "Python validation and evidence tools"
    if normalized.startswith("DA_Framework/tests/"):
        return "automated validation tests"
    if normalized.startswith("DA_Framework/examples/"):
        return "validation examples and manifests"
    return "other project files"


def _precision_artifacts(precision_dir):
    artifacts = []
    for name in PRECISION_ARTIFACTS:
        path = precision_dir / name
        artifacts.append(_artifact_row(name, path, "precision"))
    return artifacts


def _external_artifacts(external_dirs):
    artifacts = []
    for directory in external_dirs:
        for pattern in EXTERNAL_ARTIFACT_PATTERNS:
            for path in sorted(directory.glob(pattern)):
                artifacts.append(_artifact_row(path.name, path, directory.name))
    return artifacts


def _resolve_suite_report(readiness_report_path, suite_report):
    if suite_report not in (None, ""):
        return Path(suite_report).expanduser().resolve()
    inferred = readiness_report_path.parent.parent / "external_validation_suite_report.json"
    if inferred.is_file():
        return inferred
    return None


def _suite_artifacts(suite_report_path):
    if suite_report_path is None:
        return []
    artifacts = [_artifact_row(suite_report_path.name, suite_report_path, "suite")]
    if not suite_report_path.is_file():
        return artifacts
    suite = json.loads(suite_report_path.read_text(encoding="utf-8"))
    for key in SUITE_ARTIFACT_KEYS:
        value = suite.get(key)
        if value in (None, ""):
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = suite_report_path.parent / path
        artifacts.append(_artifact_row(path.name, path.resolve(), "suite"))
    return artifacts


def _artifact_row(name, path, group):
    exists = path.is_file()
    return {
        "group": str(group),
        "name": str(name),
        "path": str(path),
        "exists": bool(exists),
        "size_bytes": int(path.stat().st_size) if exists else 0,
    }


def _issue_rows(checks):
    statuses = {"fail", "missing_external_evidence", "diagnostic"}
    rows = []
    for _, row in checks.iterrows():
        status = str(row["status"])
        if status in statuses:
            rows.append(
                {
                    "check": str(row["check"]),
                    "value": "" if pd.isna(row["value"]) else str(row["value"]),
                    "status": status,
                    "detail": str(row["detail"]),
                    "source": "" if pd.isna(row["source"]) else str(row["source"]),
                }
            )
    return rows


def _dossier_markdown(dossier):
    summary = dossier["summary"]
    lines = [
        f"# {dossier['title']}",
        "",
        "## Readiness Summary",
        "",
        f"- Overall status: `{summary['overall_status']}`",
        f"- External comparison count: `{summary['external_comparison_count']}`",
        f"- Readiness report: `{dossier['readiness_report']}`",
        f"- Readiness checks CSV: `{dossier['readiness_checks_csv']}`",
        "",
        "Status counts:",
        "",
    ]
    for status, count in sorted(summary["status_counts"].items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(
        [
            "",
            "## Reviewer Evidence Matrix",
            "",
        ]
    )
    lines.extend(_reviewer_matrix_table(dossier["reviewer_evidence_matrix"]))
    lines.extend(
        [
            "",
            "## Implementation History",
            "",
        ]
    )
    lines.extend(_implementation_markdown(dossier["implementation_history"]))
    lines.extend(
        [
            "",
            "## Blocking Or Diagnostic Checks",
            "",
        ]
    )
    if dossier["issue_checks"]:
        lines.extend(_checks_table(dossier["issue_checks"]))
    else:
        lines.append("No fail, missing, or diagnostic checks were reported.")
    lines.extend(
        [
            "",
            "## Precision Evidence Artifacts",
            "",
        ]
    )
    lines.extend(_artifacts_table(dossier["precision_artifacts"]))
    lines.extend(
        [
            "",
            "## External 2D Field Evidence Artifacts",
            "",
        ]
    )
    if dossier["external_artifacts"]:
        lines.extend(_artifacts_table(dossier["external_artifacts"]))
    else:
        lines.append("No external HYDRUS or measured 2D field artifacts were indexed.")
    lines.extend(
        [
            "",
            "## External Suite Evidence Artifacts",
            "",
        ]
    )
    if dossier["suite_artifacts"]:
        lines.extend(_artifacts_table(dossier["suite_artifacts"]))
    else:
        lines.append("No external validation suite-level artifacts were indexed.")
    lines.extend(
        [
            "",
            "## Interpretation Guardrail",
            "",
            (
                "Do not claim journal readiness unless the readiness status is `pass`. "
                "A `missing_external_evidence` or `fail` status means the current "
                "evidence package is incomplete for top-journal drip validation."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _implementation_markdown(history):
    status = history.get("status", "unavailable")
    if status == "not_requested":
        return ["Implementation history indexing was not requested."]
    if status != "available":
        return [
            "Implementation history could not be indexed.",
            "",
            f"- Base commit: `{history.get('base_commit', '')}`",
            f"- Error: `{history.get('error', '')}`",
        ]
    lines = [
        f"- Base commit: `{history['base_commit']}`",
        f"- Head commit: `{history['head_commit']}`",
        f"- Commit count in range: `{history['commit_count']}`",
        f"- Changed file count in committed range: `{history['changed_file_count']}`",
        f"- Dirty worktree entries: `{history['dirty_worktree_entry_count']}`",
        "",
        "Changed files by area:",
        "",
    ]
    for item in history["changed_files_by_area"]:
        lines.append(f"- `{item['area']}`: `{item['file_count']}` files")
    lines.extend(
        [
            "",
            "Commit sequence:",
            "",
            "| Commit | Subject |",
            "| --- | --- |",
        ]
    )
    for commit in history["commits"]:
        lines.append(
            f"| `{_md_cell(commit['short_commit'])}` | {_md_cell(commit['subject'])} |"
        )
    if history["dirty_worktree_entries"]:
        lines.extend(
            [
                "",
                "Uncommitted worktree entries at dossier generation time:",
                "",
                "| Entry |",
                "| --- |",
            ]
        )
        for entry in history["dirty_worktree_entries"]:
            lines.append(f"| `{_md_cell(entry)}` |")
    return lines


def _reviewer_matrix_table(rows):
    lines = [
        "| Criterion | Status | Reviewer question | Evidence | Remaining gap |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(row["criterion"]),
                    _md_cell(row["status"]),
                    _md_cell(row["reviewer_question"]),
                    _md_cell(row["evidence"]),
                    _md_cell(row["remaining_gap"]),
                ]
            )
            + " |"
        )
    return lines


def _checks_table(rows):
    lines = [
        "| Check | Status | Value | Detail | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(row["check"]),
                    _md_cell(row["status"]),
                    _md_cell(row["value"]),
                    _md_cell(row["detail"]),
                    _md_cell(row["source"]),
                ]
            )
            + " |"
        )
    return lines


def _artifacts_table(rows):
    lines = [
        "| Group | Artifact | Exists | Size bytes | Path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(row["group"]),
                    _md_cell(row["name"]),
                    _md_cell(str(row["exists"])),
                    _md_cell(str(row["size_bytes"])),
                    _md_cell(row["path"]),
                ]
            )
            + " |"
        )
    return lines


def _md_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _parse_args(arguments):
    parser = argparse.ArgumentParser(
        description=(
            "Build a reviewer-facing JSON/Markdown evidence dossier from a "
            "MAIZSIM drip journal-readiness report."
        ),
    )
    parser.add_argument("--readiness-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--title",
        default="MAIZSIM drip validation evidence dossier",
    )
    parser.add_argument(
        "--suite-report",
        help=(
            "Optional external_validation_suite_report.json to index suite-level "
            "cases, aggregate metrics, and aggregate figures."
        ),
    )
    parser.add_argument(
        "--implementation-base-commit",
        default=DEFAULT_IMPLEMENTATION_BASE_COMMIT,
        help=(
            "Base commit used to index the drip implementation history. Defaults "
            "to the user-requested drip-module starting commit."
        ),
    )
    parser.add_argument(
        "--no-implementation-history",
        action="store_true",
        help="Skip git implementation-history indexing in the dossier.",
    )
    return parser.parse_args(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
