"""Build a journal-readiness gate for MAIZSIM drip validation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
import pandas as pd

from .hydrus_2d_comparison import read_comparison_manifest, read_hydrus_theta_csv


REQUIRED_PRECISION_CHECKS = (
    "case_count",
    "spatial_active_case_count",
    "demand_input_pressure_residual_abs_max_mm",
    "source_input_loss_residual_abs_max_mm",
    "boundary_acceptance_residual_abs_max_mm",
    "direct_source_bypass_case_count",
    "wet_width_limit_violations",
    "short_width_error_abs_max_cm",
    "centered_hydrus_curve_width_error_abs_max_cm",
    "centered_hydrus_curve_width_error_rel_abs_max",
    "accepted_timestep_actual_infil_rel_error_max",
    "accepted_timestep_hydraulic_excess_rel_error_max",
    "fixed_domain_grid_refinement_factor_count",
    "fixed_domain_factor2_actual_infil_rel_error_max",
    "fixed_domain_factor2_hydraulic_excess_abs_error_max_mm",
    "fixed_domain_factor2_wet_width_abs_error_max_cm",
    "spatial_positive_delta_records",
    "spatial_peak_offset_abs_max_cm",
    "spatial_positive_area_records",
    "spatial_positive_storage_records",
    "spatial_root_storage_fraction_records",
    "spatial_root_weighted_delta_records",
    "spatial_worst_case_count",
    "spatial_temporal_case_count",
    "spatial_temporal_date_count_min",
    "spatial_temporal_positive_storage_cases",
    "spatial_temporal_root_active_case_count",
    "spatial_temporal_root_storage_fraction_min",
)

REQUIRED_PRECISION_FIGURES = (
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

MIN_FIGURE_PIXEL_WIDTH = 600
MIN_FIGURE_PIXEL_HEIGHT = 400
MIN_FIGURE_PIXEL_RANGE = 0.01
JOURNAL_REJECTED_EVIDENCE_TERMS = (
    "unit-test",
    "unit test",
    "test suite",
    "fixture writer",
    "fixture export",
    "fixture mesh",
    "fixture grid",
    "fixture-v",
    "in-memory",
    "dummy",
    "mock",
)

DEFAULT_THRESHOLDS = {
    "external_case_count_min": 3.0,
    "external_soil_parameter_set_count_min": 3.0,
    "external_irrigation_event_setting_count_min": 2.0,
    "external_output_time_count_min": 2.0,
    "external_soil_ks_ratio_min": 5.0,
    "external_emitter_rate_ratio_min": 1.5,
    "external_event_duration_span_h_min": 2.0,
    "external_output_time_span_h_min": 2.0,
    "root_spatial_record_count_min": 36.0,
    "root_spatial_soil_count_min": 3.0,
    "root_spatial_grid_count_min": 3.0,
    "root_spatial_scenario_count_min": 4.0,
    "root_spatial_temporal_case_count_min": 36.0,
    "root_spatial_temporal_date_count_min": 7.0,
    "root_weighted_delta_theta_min": 0.0,
    "root_overlap_fraction_min": 0.5,
    "root_area_fraction_min": 0.5,
    "root_positive_storage_cm2_min": 0.1,
    "root_storage_fraction_min": 0.95,
    "root_temporal_positive_storage_cm2_min": 0.1,
    "root_temporal_storage_fraction_min": 0.95,
    "theta_rmse_max": 0.03,
    "delta_theta_rmse_max": 0.025,
    "wet_iou_min": 0.65,
    "source_wet_iou_min": 0.65,
    "require_source_wet_metrics": 1.0,
    "peak_delta_distance_cm_max": 5.0,
    "wet_width_error_cm_max": 5.0,
    "wet_depth_error_cm_max": 8.0,
    "delta_storage_rel_error_max": 0.10,
    "require_storage_metrics": 1.0,
    "point_count_min": 20.0,
    "comparison_point_fraction_min": 0.95,
    "comparison_area_fraction_min": 0.95,
    "uncertainty_within_2sd_fraction_min": 0.80,
    "require_uncertainty_metrics": 1.0,
}

JOURNAL_PROTECTED_THRESHOLDS = (
    "external_case_count_min",
    "external_soil_parameter_set_count_min",
    "external_irrigation_event_setting_count_min",
    "external_output_time_count_min",
    "external_soil_ks_ratio_min",
    "external_emitter_rate_ratio_min",
    "external_event_duration_span_h_min",
    "external_output_time_span_h_min",
    "root_spatial_record_count_min",
    "root_spatial_soil_count_min",
    "root_spatial_grid_count_min",
    "root_spatial_scenario_count_min",
    "root_spatial_temporal_case_count_min",
    "root_spatial_temporal_date_count_min",
    "root_weighted_delta_theta_min",
    "root_overlap_fraction_min",
    "root_area_fraction_min",
    "root_positive_storage_cm2_min",
    "root_storage_fraction_min",
    "root_temporal_positive_storage_cm2_min",
    "root_temporal_storage_fraction_min",
    "theta_rmse_max",
    "delta_theta_rmse_max",
    "wet_iou_min",
    "source_wet_iou_min",
    "require_source_wet_metrics",
    "peak_delta_distance_cm_max",
    "wet_width_error_cm_max",
    "wet_depth_error_cm_max",
    "delta_storage_rel_error_max",
    "require_storage_metrics",
    "point_count_min",
    "comparison_point_fraction_min",
    "comparison_area_fraction_min",
    "uncertainty_within_2sd_fraction_min",
    "require_uncertainty_metrics",
)

RAW_REFERENCE_EVENT_ROLE_TOKENS = (
    "event",
    "output",
    "post",
    "irrigated",
)

RAW_REFERENCE_BASELINE_ROLE_TOKENS = (
    "baseline",
    "initial",
    "pre_event",
    "pre-event",
    "no_drip",
    "without_drip",
)


def main(arguments=None):
    args = _parse_args(arguments)
    thresholds = _thresholds_from_args(args)
    result = build_readiness_report(
        precision_dir=args.precision_dir,
        output_dir=args.output_dir,
        external_comparison_dirs=args.external_comparison_dir,
        thresholds=thresholds,
    )
    if arguments is None:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["overall_status"] == "pass" else 1


def build_readiness_report(
    precision_dir,
    output_dir,
    external_comparison_dirs=None,
    thresholds=None,
):
    """Write journal-readiness CSV/JSON summaries and return the JSON data."""
    precision_path = Path(precision_dir).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    thresholds = _merge_thresholds(thresholds)

    rows = []
    rows.append(_threshold_policy_check(thresholds))
    rows.extend(_precision_checks(precision_path))
    rows.extend(_precision_figure_checks(precision_path))
    rows.extend(_root_zone_evidence_checks(precision_path, thresholds))
    comparison_dirs = [
        Path(item).expanduser().resolve()
        for item in (external_comparison_dirs or ())
    ]
    rows.extend(_external_comparison_checks(comparison_dirs, thresholds))

    checks = pd.DataFrame.from_records(rows)
    checks_path = output_path / "journal_readiness_checks.csv"
    checks.to_csv(checks_path, index=False)
    status_counts = checks["status"].value_counts().to_dict()
    overall_status = _overall_status(checks)
    report = {
        "overall_status": overall_status,
        "status_counts": {str(key): int(value) for key, value in status_counts.items()},
        "precision_dir": str(precision_path),
        "external_comparison_dirs": [str(path) for path in comparison_dirs],
        "thresholds": thresholds,
        "checks_csv": str(checks_path),
        "required_external_evidence": (
            "Multiple HYDRUS or measured 2D theta-field comparison cases with "
            "diverse soil hydraulic parameters and irrigation event settings, "
            "multiple time-matched event-relative output times, same-condition "
            "independent-validation manifests with structured reference "
            "provenance, HYDRUS mass-balance or measured-instrument QA "
            "metadata, event and baseline raw reference file hashes, point "
            "residuals, figures, and audit JSON files are required before "
            "journal readiness can be marked pass."
        ),
    }
    report_path = output_path / "journal_readiness_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def _precision_checks(precision_dir):
    checks_path = precision_dir / "precision_validation_checks.csv"
    if not checks_path.is_file():
        return [
            _row(
                "precision_checks_present",
                0,
                "fail",
                f"Missing precision validation checks: {checks_path}",
                checks_path,
            )
        ]
    checks = pd.read_csv(checks_path)
    rows = [
        _row(
            "precision_checks_present",
            1,
            "pass",
            "Found precision validation checks.",
            checks_path,
        )
    ]
    fail_count = int((checks["status"].astype(str) == "fail").sum())
    rows.append(
        _row(
            "precision_fail_count",
            fail_count,
            "pass" if fail_count == 0 else "fail",
            "Internal precision validation checks must have no fail rows.",
            checks_path,
        )
    )
    check_by_name = {
        str(row["check"]): str(row["status"])
        for _, row in checks.iterrows()
    }
    for check_name in REQUIRED_PRECISION_CHECKS:
        status = check_by_name.get(check_name)
        rows.append(
            _row(
                f"required_precision_{check_name}",
                1 if status == "pass" else 0,
                "pass" if status == "pass" else "fail",
                f"Required precision check {check_name!r} must be pass.",
                checks_path,
            )
        )
    return rows


def _precision_figure_checks(precision_dir):
    rows = []
    for name in REQUIRED_PRECISION_FIGURES:
        path = precision_dir / name
        audit = _figure_pixel_audit(path)
        quality = _figure_quality(audit)
        rows.append(
            _row(
                f"precision_figure_{path.stem}",
                _figure_quality_value(audit),
                "pass" if quality["ok"] else "fail",
                (
                    f"Required visual evidence figure {name} must exist, be "
                    "readable, contain visible pixel variation, and satisfy "
                    "minimum journal-review resolution."
                    + _figure_quality_detail(quality)
                ),
                path,
            )
        )
    return rows


def _figure_pixel_audit(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0:
        return _empty_figure_audit()
    try:
        image = mpimg.imread(path)
    except Exception:
        return _empty_figure_audit()
    values = np.asarray(image, dtype=float)
    if values.ndim == 3 and values.shape[2] >= 3:
        values = values[:, :, :3]
    if values.size == 0 or not np.isfinite(values).any():
        return _empty_figure_audit()
    pixel_range = float(np.nanmax(values) - np.nanmin(values))
    return {
        "readable": True,
        "nonblank": pixel_range >= MIN_FIGURE_PIXEL_RANGE,
        "pixel_range": pixel_range,
        "pixel_height": int(values.shape[0]),
        "pixel_width": int(values.shape[1]) if values.ndim >= 2 else 0,
    }


def _empty_figure_audit():
    return {
        "readable": False,
        "nonblank": False,
        "pixel_range": 0.0,
        "pixel_height": 0,
        "pixel_width": 0,
    }


def _figure_quality(audit):
    width = int(audit.get("pixel_width", 0) or 0)
    height = int(audit.get("pixel_height", 0) or 0)
    pixel_range = float(audit.get("pixel_range", 0.0) or 0.0)
    problems = []
    if audit.get("readable") is not True:
        problems.append("not readable")
    if audit.get("nonblank") is not True:
        problems.append(
            f"pixel range {pixel_range:.4g} < {MIN_FIGURE_PIXEL_RANGE:g}"
        )
    if width < MIN_FIGURE_PIXEL_WIDTH or height < MIN_FIGURE_PIXEL_HEIGHT:
        problems.append(
            f"resolution {width}x{height} < "
            f"{MIN_FIGURE_PIXEL_WIDTH}x{MIN_FIGURE_PIXEL_HEIGHT}"
        )
    return {
        "ok": not problems,
        "problems": problems,
        "width": width,
        "height": height,
        "pixel_range": pixel_range,
    }


def _figure_quality_value(audit):
    return (
        f"{int(audit.get('pixel_width', 0) or 0)}x"
        f"{int(audit.get('pixel_height', 0) or 0)};"
        f"range={float(audit.get('pixel_range', 0.0) or 0.0):.6g}"
    )


def _figure_quality_detail(quality):
    if quality["ok"]:
        return (
            f" Figure audit: {quality['width']}x{quality['height']} px, "
            f"pixel_range={quality['pixel_range']:.4g}."
        )
    return " Figure audit problems: " + "; ".join(quality["problems"]) + "."


def _root_zone_evidence_checks(precision_dir, thresholds):
    spatial_path = precision_dir / "precision_spatial_delta_root.csv"
    if not spatial_path.is_file():
        return [
            _row(
                "root_zone_spatial_delta_root_present",
                0,
                "fail",
                "Root-zone 2D delta-theta/root-density evidence CSV is required.",
                spatial_path,
            )
        ]
    spatial = pd.read_csv(spatial_path)
    rows = [
        _row(
            "root_zone_spatial_delta_root_present",
            1,
            "pass",
            "Found root-zone 2D delta-theta/root-density evidence CSV.",
            spatial_path,
        ),
        _row(
            "root_zone_spatial_record_count",
            len(spatial),
            "pass"
            if len(spatial) >= thresholds["root_spatial_record_count_min"]
            else "fail",
            "Root-zone 2D evidence should cover multiple soil/case records.",
            spatial_path,
        ),
    ]
    rows.append(
        _root_zone_distinct_count_check(
            spatial,
            spatial_path,
            "soil",
            thresholds["root_spatial_soil_count_min"],
            "Root-zone 2D evidence should cover multiple soils.",
        )
    )
    rows.append(
        _root_zone_distinct_count_check(
            spatial,
            spatial_path,
            "grid",
            thresholds["root_spatial_grid_count_min"],
            "Root-zone 2D evidence should cover grid-width sensitivity cases.",
        )
    )
    rows.append(
        _root_zone_distinct_count_check(
            spatial,
            spatial_path,
            "scenario",
            thresholds["root_spatial_scenario_count_min"],
            "Root-zone 2D evidence should cover multiple drip scenarios.",
        )
    )
    rows.append(
        _root_zone_min_check(
            spatial,
            spatial_path,
            "root_weighted_delta_theta",
            thresholds["root_weighted_delta_theta_min"],
            strict=True,
            failure_status="diagnostic",
            detail=(
                "Root-density-weighted delta theta is reported as a diagnostic; "
                "low-flow cases can be offset by simulated root uptake."
            ),
        )
    )
    rows.append(
        _root_zone_min_check(
            spatial,
            spatial_path,
            "positive_delta_root_overlap_fraction",
            thresholds["root_overlap_fraction_min"],
            detail=(
                "Positive wetting nodes should overlap the simulated root zone "
                "substantially."
            ),
        )
    )
    rows.append(
        _root_zone_min_check(
            spatial,
            spatial_path,
            "positive_delta_root_area_fraction",
            thresholds["root_area_fraction_min"],
            detail=(
                "Positive wetting area should overlap the simulated root-zone "
                "area substantially."
            ),
        )
    )
    rows.append(
        _root_zone_min_check(
            spatial,
            spatial_path,
            "positive_delta_storage_cm2",
            thresholds["root_positive_storage_cm2_min"],
            strict=True,
            detail=(
                "Area-integrated positive delta-theta storage should be "
                "non-trivial in root-zone evidence cases."
            ),
        )
    )
    rows.append(
        _root_zone_min_check(
            spatial,
            spatial_path,
            "positive_delta_root_storage_fraction",
            thresholds["root_storage_fraction_min"],
            detail=(
                "Positive area-integrated wetting storage should overlap the "
                "simulated root zone."
            ),
        )
    )
    rows.extend(_root_zone_temporal_evidence_checks(precision_dir, thresholds))
    return rows


def _root_zone_temporal_evidence_checks(precision_dir, thresholds):
    temporal_path = precision_dir / "precision_spatial_temporal_delta_root.csv"
    if not temporal_path.is_file():
        return [
            _row(
                "root_zone_spatial_temporal_delta_root_present",
                0,
                "fail",
                "Temporal 2D delta-theta/root-density evidence CSV is required.",
                temporal_path,
            )
        ]
    temporal = pd.read_csv(temporal_path)
    rows = [
        _row(
            "root_zone_spatial_temporal_delta_root_present",
            1,
            "pass",
            "Found temporal 2D delta-theta/root-density evidence CSV.",
            temporal_path,
        )
    ]
    required_columns = (
        "case",
        "date",
        "root_area_cm2",
        "positive_delta_storage_cm2",
        "positive_delta_root_storage_fraction",
    )
    missing = [column for column in required_columns if column not in temporal.columns]
    if missing:
        rows.append(
            _row(
                "root_zone_spatial_temporal_required_columns",
                "",
                "fail",
                f"Temporal 2D evidence CSV is missing columns: {missing}.",
                temporal_path,
            )
        )
        return rows
    storage = pd.to_numeric(
        temporal["positive_delta_storage_cm2"],
        errors="coerce",
    )
    root_area = pd.to_numeric(
        temporal["root_area_cm2"],
        errors="coerce",
    )
    root_fraction = pd.to_numeric(
        temporal["positive_delta_root_storage_fraction"],
        errors="coerce",
    )
    if storage.isna().any() or root_area.isna().any() or root_fraction.isna().any():
        rows.append(
            _row(
                "root_zone_spatial_temporal_numeric_columns",
                "",
                "fail",
                "Temporal storage evidence columns must be numeric.",
                temporal_path,
            )
        )
        return rows
    case_count = int(temporal["case"].astype(str).nunique()) if not temporal.empty else 0
    date_count_min = (
        int(temporal.groupby("case")["date"].nunique().min())
        if not temporal.empty
        else 0
    )
    storage_by_case = storage.groupby(temporal["case"].astype(str)).max()
    positive_case_count = int(
        (
            storage_by_case
            > thresholds["root_temporal_positive_storage_cm2_min"]
        ).sum()
    )
    positive = storage > thresholds["root_temporal_positive_storage_cm2_min"]
    root_active = root_area > 0.0
    root_active_case_count = int(
        temporal.loc[root_active, "case"].astype(str).nunique()
    )
    positive_root_active = positive & root_active
    root_fraction_min = (
        float(root_fraction[positive_root_active].min())
        if positive_root_active.any()
        else 0.0
    )
    rows.extend(
        [
            _row(
                "root_zone_spatial_temporal_case_count",
                case_count,
                "pass"
                if case_count >= thresholds["root_spatial_temporal_case_count_min"]
                else "fail",
                "Temporal 2D evidence should cover every active regression case.",
                temporal_path,
            ),
            _row(
                "root_zone_spatial_temporal_date_count_min",
                date_count_min,
                "pass"
                if date_count_min >= thresholds["root_spatial_temporal_date_count_min"]
                else "fail",
                "Temporal 2D evidence should cover multiple dates per case.",
                temporal_path,
            ),
            _row(
                "root_zone_spatial_temporal_positive_storage_case_count",
                positive_case_count,
                "pass" if positive_case_count == case_count else "fail",
                (
                    "Every temporal 2D case should contain at least one "
                    "non-trivial positive storage date."
                ),
                temporal_path,
            ),
            _row(
                "root_zone_spatial_temporal_root_active_case_count",
                root_active_case_count,
                "pass" if root_active_case_count == case_count else "fail",
                (
                    "Temporal root-density evidence should include at least "
                    "one root-active date for every active drip case."
                ),
                temporal_path,
            ),
            _row(
                "root_zone_spatial_temporal_root_storage_fraction_min",
                root_fraction_min,
                "pass"
                if root_fraction_min >= thresholds["root_temporal_storage_fraction_min"]
                else "fail",
                (
                    "Positive temporal wetting storage should overlap the "
                    "simulated root zone."
                ),
                temporal_path,
            ),
        ]
    )
    return rows


def _root_zone_distinct_count_check(
    spatial,
    spatial_path,
    column,
    threshold,
    detail,
):
    check = f"root_zone_spatial_{column}_count"
    if column not in spatial.columns:
        return _row(
            check,
            "",
            "fail",
            f"Root-zone 2D evidence CSV must include a {column} column.",
            spatial_path,
        )
    count = int(spatial[column].astype(str).nunique())
    return _row(
        check,
        count,
        "pass" if count >= threshold else "fail",
        detail,
        spatial_path,
    )


def _root_zone_min_check(
    spatial,
    spatial_path,
    column,
    threshold,
    *,
    strict=False,
    failure_status="fail",
    detail,
):
    if column not in spatial.columns:
        return _row(
            f"root_zone_{column}_min",
            "",
            "fail",
            f"Root-zone 2D evidence CSV must include {column!r}.",
            spatial_path,
        )
    values = pd.to_numeric(spatial[column], errors="coerce")
    if values.isna().any():
        return _row(
            f"root_zone_{column}_min",
            "",
            "fail",
            f"Root-zone 2D evidence column {column!r} must be numeric.",
            spatial_path,
        )
    value = float(values.min())
    passed = value > threshold if strict else value >= threshold
    return _row(
        f"root_zone_{column}_min",
        value,
        "pass" if passed else failure_status,
        detail,
        spatial_path,
    )


def _external_comparison_checks(comparison_dirs, thresholds):
    if not comparison_dirs:
        return [
            _row(
                "external_2d_field_comparison_present",
                0,
                "missing_external_evidence",
                (
                    "No HYDRUS/measured 2D theta-field comparison directory was "
                    "provided, so journal readiness cannot be claimed."
                ),
                "",
            )
        ]
    case_count = len(comparison_dirs)
    rows = [
        _row(
            "external_2d_field_comparison_case_count",
            case_count,
            "pass"
            if case_count >= thresholds["external_case_count_min"]
            else "fail",
            (
                "External validation should include multiple independent "
                "HYDRUS/measured 2D field comparison cases."
            ),
            "",
        )
    ]
    rows.extend(_external_manifest_diversity_checks(comparison_dirs, thresholds))
    for comparison_dir in comparison_dirs:
        rows.extend(_one_external_comparison_checks(comparison_dir, thresholds))
    return rows


def _external_manifest_diversity_checks(comparison_dirs, thresholds):
    manifests = []
    for comparison_dir in comparison_dirs:
        manifest_path = _find_exactly_one(comparison_dir, "*_manifest.json")
        if manifest_path is None:
            continue
        try:
            manifests.append(read_comparison_manifest(manifest_path))
        except Exception:
            continue
    soil_count = _manifest_diversity_count(manifests, "soil_hydraulic_parameters")
    event_count = len(
        {
            _canonical_json(
                {
                    "emitter_rate_l_h": manifest.get("emitter_rate_l_h"),
                    "applied_volume_l": manifest.get("applied_volume_l"),
                    "event_duration_h": manifest.get("event_duration_h"),
                }
            )
            for manifest in manifests
        }
    )
    output_time_count = _manifest_numeric_diversity_count(
        manifests,
        "event_relative_time_h",
    )
    reference_case_id_count = _manifest_nested_diversity_count(
        manifests,
        ("reference_identity", "reference_case_id"),
    )
    validation_dataset_id_count = _manifest_nested_diversity_count(
        manifests,
        ("independence_proof", "validation_dataset_id"),
    )
    ks_ratio = _numeric_ratio(
        _manifest_nested_numeric_values(
            manifests,
            ("soil_hydraulic_parameters", "ks_cm_h"),
        )
    )
    emitter_rate_ratio = _numeric_ratio(
        _manifest_numeric_values(manifests, "emitter_rate_l_h")
    )
    event_duration_span = _numeric_span(
        _manifest_numeric_values(manifests, "event_duration_h")
    )
    output_time_span = _numeric_span(
        _manifest_numeric_values(manifests, "event_relative_time_h")
    )
    case_count = len(comparison_dirs)
    return [
        _row(
            "external_soil_parameter_set_count",
            soil_count,
            "pass"
            if soil_count >= thresholds["external_soil_parameter_set_count_min"]
            else "fail",
            (
                "External validation should cover multiple independent soil "
                "hydraulic parameter sets."
            ),
            "",
        ),
        _row(
            "external_irrigation_event_setting_count",
            event_count,
            "pass"
            if event_count
            >= thresholds["external_irrigation_event_setting_count_min"]
            else "fail",
            (
                "External validation should cover more than one drip irrigation "
                "rate/volume/duration setting."
            ),
            "",
        ),
        _row(
            "external_output_time_count",
            output_time_count,
            "pass"
            if output_time_count >= thresholds["external_output_time_count_min"]
            else "fail",
            (
                "External validation should include more than one output time "
                "measured as event-relative hours, so the 2D wetting process "
                "is tested beyond a single snapshot."
            ),
            "",
        ),
        _row(
            "external_reference_case_id_unique_count",
            reference_case_id_count,
            "pass" if reference_case_id_count == case_count else "fail",
            (
                "External validation should not duplicate the same reference "
                "case identifier across comparison directories."
            ),
            "",
        ),
        _row(
            "external_validation_dataset_id_unique_count",
            validation_dataset_id_count,
            "pass" if validation_dataset_id_count == case_count else "fail",
            (
                "External validation should not reuse a validation dataset ID "
                "as multiple independent comparison cases."
            ),
            "",
        ),
        _row(
            "external_soil_ks_ratio",
            ks_ratio,
            "pass" if ks_ratio >= thresholds["external_soil_ks_ratio_min"] else "fail",
            (
                "External soil hydraulic parameter diversity should include "
                "a substantive saturated-conductivity spread, not only tiny "
                "numeric perturbations."
            ),
            "",
        ),
        _row(
            "external_emitter_rate_ratio",
            emitter_rate_ratio,
            "pass"
            if emitter_rate_ratio >= thresholds["external_emitter_rate_ratio_min"]
            else "fail",
            (
                "External irrigation events should include a substantive "
                "low/high emitter-rate spread."
            ),
            "",
        ),
        _row(
            "external_event_duration_span_h",
            event_duration_span,
            "pass"
            if event_duration_span
            >= thresholds["external_event_duration_span_h_min"]
            else "fail",
            (
                "External irrigation events should include a substantive "
                "duration spread in hours."
            ),
            "",
        ),
        _row(
            "external_output_time_span_h",
            output_time_span,
            "pass"
            if output_time_span >= thresholds["external_output_time_span_h_min"]
            else "fail",
            (
                "External validation should span early and later "
                "event-relative output times rather than only nearby snapshots."
            ),
            "",
        ),
    ]


def _one_external_comparison_checks(comparison_dir, thresholds):
    artifacts = _external_artifacts(comparison_dir)
    rows = _external_artifact_checks(comparison_dir, artifacts)
    manifest_path = artifacts["manifest"]
    if manifest_path is not None:
        rows.extend(_external_manifest_content_checks(comparison_dir, manifest_path))
    outputs_path = artifacts["outputs"]
    if outputs_path is not None:
        rows.append(_external_outputs_content_check(comparison_dir, outputs_path))
    audit_path = artifacts["audit"]
    if audit_path is not None:
        rows.append(_external_audit_content_check(comparison_dir, audit_path))
    summary_path = artifacts["summary"]
    if summary_path is None:
        return rows
    summary = pd.read_csv(summary_path)
    if summary.empty:
        rows.append(
            _row(
                f"external_summary_nonempty::{comparison_dir.name}",
                0,
                "fail",
                "External comparison summary CSV is empty.",
                summary_path,
            )
        )
        return rows
    rows.append(
        _row(
            f"external_summary_single_row::{comparison_dir.name}",
            len(summary),
            "pass" if len(summary) == 1 else "fail",
            "External comparison summary CSV must contain exactly one metrics row.",
            summary_path,
        )
    )
    metrics = summary.iloc[0].to_dict()
    points_path = artifacts["points"]
    if points_path is not None:
        rows.extend(
            _external_points_content_checks(
                comparison_dir,
                points_path,
                metrics,
                thresholds,
                manifest_path,
            )
        )
        if audit_path is not None:
            rows.extend(
                _external_reference_coverage_checks(
                    comparison_dir,
                    points_path,
                    audit_path,
                    metrics,
                )
            )
            rows.extend(
                _external_reference_point_value_checks(
                    comparison_dir,
                    points_path,
                    audit_path,
                )
            )
    rows.extend(
        [
            _max_check(
                comparison_dir,
                summary_path,
                metrics,
                "point_count",
                thresholds["point_count_min"],
                greater_is_better=True,
                detail="External field comparison should contain enough points for a 2D field claim.",
            ),
            _max_check(
                comparison_dir,
                summary_path,
                metrics,
                "comparison_point_fraction",
                thresholds["comparison_point_fraction_min"],
                greater_is_better=True,
                detail=(
                    "External comparison should retain nearly all reference "
                    "field points after spatial interpolation."
                ),
            ),
            _max_check(
                comparison_dir,
                summary_path,
                metrics,
                "comparison_area_fraction",
                thresholds["comparison_area_fraction_min"],
                greater_is_better=True,
                detail=(
                    "External comparison should cover nearly all reference "
                    "field area after spatial interpolation."
                ),
            ),
            _max_check(
                comparison_dir,
                summary_path,
                metrics,
                "theta_rmse",
                thresholds["theta_rmse_max"],
                detail="Absolute theta RMSE should remain within the journal-readiness gate.",
            ),
            _max_check(
                comparison_dir,
                summary_path,
                metrics,
                "delta_theta_rmse",
                thresholds["delta_theta_rmse_max"],
                detail="Delta-theta RMSE should remain within the journal-readiness gate.",
            ),
            _max_check(
                comparison_dir,
                summary_path,
                metrics,
                "wet_iou",
                thresholds["wet_iou_min"],
                greater_is_better=True,
                detail="HYDRUS/measured and MAIZSIM wetted bodies should overlap strongly.",
            ),
            _max_check(
                comparison_dir,
                summary_path,
                metrics,
                "peak_delta_distance_cm",
                thresholds["peak_delta_distance_cm_max"],
                detail="Peak wetting locations should be close.",
            ),
        ]
    )
    rows.extend(_shape_difference_checks(comparison_dir, summary_path, metrics, thresholds))
    rows.extend(_optional_source_wet_check(comparison_dir, summary_path, metrics, thresholds))
    rows.extend(_optional_storage_check(comparison_dir, summary_path, metrics, thresholds))
    rows.extend(_optional_uncertainty_checks(comparison_dir, summary_path, metrics, thresholds))
    return rows


def _external_artifacts(comparison_dir):
    return {
        "summary": _find_exactly_one(comparison_dir, "*_summary.csv"),
        "points": _find_exactly_one(comparison_dir, "*_points.csv"),
        "figure": _find_exactly_one(comparison_dir, "*_fields.png"),
        "outputs": _find_exactly_one(comparison_dir, "*_outputs.json"),
        "manifest": _find_exactly_one(comparison_dir, "*_manifest.json"),
        "audit": _find_exactly_one(comparison_dir, "*_audit.json"),
    }


def _external_artifact_checks(comparison_dir, artifacts):
    rows = []
    required = (
        ("summary", "summary CSV"),
        ("points", "point-level residual CSV"),
        ("figure", "2D comparison figure"),
        ("outputs", "outputs index JSON"),
        ("manifest", "same-condition manifest JSON"),
        ("audit", "comparison audit JSON"),
    )
    for key, label in required:
        matches = _find_matches(comparison_dir, _artifact_pattern(key))
        path = artifacts[key]
        if len(matches) == 1:
            rows.append(
                _row(
                    f"external_{key}_present::{comparison_dir.name}",
                    1,
                    "pass",
                    f"External comparison must include exactly one {label}.",
                    path,
                )
            )
        else:
            rows.append(
                _row(
                    f"external_{key}_present::{comparison_dir.name}",
                    len(matches),
                    "fail",
                    (
                        f"External comparison must include exactly one {label}; "
                        f"found {len(matches)}."
                    ),
                    comparison_dir,
                )
            )
    figure_path = artifacts["figure"]
    if figure_path is not None:
        rows.append(_external_figure_nonblank_check(comparison_dir, figure_path))
    return rows


def _artifact_pattern(key):
    return {
        "summary": "*_summary.csv",
        "points": "*_points.csv",
        "figure": "*_fields.png",
        "outputs": "*_outputs.json",
        "manifest": "*_manifest.json",
        "audit": "*_audit.json",
    }[key]


def _external_figure_nonblank_check(comparison_dir, figure_path):
    audit = _figure_pixel_audit(figure_path)
    quality = _figure_quality(audit)
    return _row(
        f"external_figure_nonblank::{comparison_dir.name}",
        _figure_quality_value(audit),
        "pass" if quality["ok"] else "fail",
        (
            "External 2D comparison figure must be readable, nonblank, "
            "and large enough for visual wetting-body review."
            + _figure_quality_detail(quality)
        ),
        figure_path,
    )


def _external_manifest_content_checks(comparison_dir, manifest_path):
    try:
        manifest = read_comparison_manifest(manifest_path)
    except Exception as exc:
        return [
            _row(
                f"external_manifest_valid::{comparison_dir.name}",
                0,
                "fail",
                f"Same-condition manifest is invalid: {exc}",
                manifest_path,
            )
        ]
    return [
        _row(
            f"external_manifest_valid::{comparison_dir.name}",
            1,
            "pass",
            "Same-condition manifest contains all required metadata keys.",
            manifest_path,
        ),
        _external_manifest_journal_evidence_check(
            comparison_dir,
            manifest_path,
            manifest,
        ),
    ]


def _external_manifest_journal_evidence_check(
    comparison_dir,
    manifest_path,
    manifest,
):
    matches = _journal_rejected_evidence_matches(manifest)
    if matches:
        examples = "; ".join(
            f"{path} contains {term!r}" for path, term, _ in matches[:5]
        )
        if len(matches) > 5:
            examples += f"; {len(matches) - 5} more"
        return _row(
            f"external_manifest_journal_evidence::{comparison_dir.name}",
            0,
            "fail",
            (
                "Journal-readiness evidence must not be described as a "
                "unit-test, fixture export, dummy, or mock dataset: "
                f"{examples}."
            ),
            manifest_path,
        )
    return _row(
        f"external_manifest_journal_evidence::{comparison_dir.name}",
        1,
        "pass",
        (
            "Same-condition manifest does not describe the reference evidence "
            "as unit-test, fixture export, dummy, or mock data."
        ),
        manifest_path,
    )


def _journal_rejected_evidence_matches(value, path="manifest"):
    if isinstance(value, dict):
        matches = []
        for key, item in value.items():
            matches.extend(
                _journal_rejected_evidence_matches(item, f"{path}.{key}")
            )
        return matches
    if isinstance(value, list):
        matches = []
        for index, item in enumerate(value):
            matches.extend(
                _journal_rejected_evidence_matches(item, f"{path}[{index}]")
            )
        return matches
    if not isinstance(value, str):
        return []
    normalized = " ".join(value.strip().casefold().split())
    return [
        (path, term, value)
        for term in JOURNAL_REJECTED_EVIDENCE_TERMS
        if term in normalized
    ]


def _external_outputs_content_check(comparison_dir, outputs_path):
    required = {
        "summary_csv": "summary",
        "points_csv": "points",
        "figure": "figure",
        "comparison_manifest_json": "manifest",
        "audit_json": "audit",
    }
    try:
        outputs = json.loads(Path(outputs_path).read_text(encoding="utf-8"))
    except Exception as exc:
        return _row(
            f"external_outputs_index_valid::{comparison_dir.name}",
            0,
            "fail",
            f"External outputs index is not readable JSON: {exc}",
            outputs_path,
        )
    if not isinstance(outputs, dict):
        return _row(
            f"external_outputs_index_valid::{comparison_dir.name}",
            0,
            "fail",
            "External outputs index must be a JSON object.",
            outputs_path,
        )
    missing = [key for key in required if not outputs.get(key)]
    if missing:
        return _row(
            f"external_outputs_index_valid::{comparison_dir.name}",
            0,
            "fail",
            f"External outputs index is missing keys: {missing}.",
            outputs_path,
        )
    mismatches = _external_outputs_index_mismatches(
        comparison_dir,
        outputs_path,
        outputs,
        required,
    )
    if mismatches:
        return _row(
            f"external_outputs_index_valid::{comparison_dir.name}",
            0,
            "fail",
            "External outputs index paths do not match the indexed artifacts: "
            + "; ".join(mismatches),
            outputs_path,
        )
    return _row(
        f"external_outputs_index_valid::{comparison_dir.name}",
        1,
        "pass",
        (
            "External outputs index records summary, points, figure, manifest, "
            "and audit paths that match the indexed artifacts."
        ),
        outputs_path,
    )


def _external_outputs_index_mismatches(
    comparison_dir,
    outputs_path,
    outputs,
    required,
):
    artifacts = _external_artifacts(comparison_dir)
    mismatches = []
    for output_key, artifact_key in required.items():
        indexed = _resolve_output_index_path(outputs[output_key], outputs_path)
        expected = artifacts[artifact_key]
        if expected is None:
            mismatches.append(f"{output_key} artifact is missing")
            continue
        if not indexed.is_file():
            mismatches.append(f"{output_key} file is missing")
            continue
        if indexed.resolve() != Path(expected).resolve():
            mismatches.append(f"{output_key} points to {indexed}")
    return mismatches


def _resolve_output_index_path(value, outputs_path):
    path = Path(str(value))
    if not path.is_absolute():
        path = Path(outputs_path).parent / path
    return path.expanduser()


def _external_audit_content_check(comparison_dir, audit_path):
    required_top_level = (
        "inputs",
        "selected_times",
        "comparison",
        "artifacts",
        "raw_reference_files",
    )
    required_inputs = (
        "maizsim_g03",
        "hydrus_csv",
        "maizsim_baseline_g03",
        "hydrus_baseline_csv",
        "comparison_manifest",
    )
    required_artifacts = (
        "summary_csv",
        "points_csv",
        "figure",
        "comparison_manifest_json",
    )
    try:
        audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    except Exception as exc:
        return _row(
            f"external_audit_valid::{comparison_dir.name}",
            0,
            "fail",
            f"External comparison audit is not readable JSON: {exc}",
            audit_path,
        )
    if not isinstance(audit, dict):
        return _row(
            f"external_audit_valid::{comparison_dir.name}",
            0,
            "fail",
            "External comparison audit must be a JSON object.",
            audit_path,
        )
    missing_top = [key for key in required_top_level if key not in audit]
    inputs = audit.get("inputs", {})
    input_mismatches = _external_audit_file_mismatches(inputs, required_inputs)
    artifacts = audit.get("artifacts", {})
    missing_artifacts = [
        key
        for key in required_artifacts
        if not isinstance(artifacts, dict) or key not in artifacts
    ]
    figure_audit = artifacts.get("figure", {}) if isinstance(artifacts, dict) else {}
    figure_audit_problems = _audit_figure_quality_mismatches(figure_audit)
    raw_reference_mismatches = _external_audit_raw_reference_mismatches(
        audit.get("raw_reference_files", [])
    )
    time_mismatches = _external_audit_time_mismatches(audit)
    if (
        missing_top
        or input_mismatches
        or raw_reference_mismatches
        or time_mismatches
        or missing_artifacts
        or figure_audit_problems
    ):
        return _row(
            f"external_audit_valid::{comparison_dir.name}",
            0,
            "fail",
            (
                "External comparison audit must include inputs, comparison, "
                "input hashes, raw reference hashes, artifact hashes, and a "
                "journal-quality figure check."
                + (
                    " Input audit problems: " + "; ".join(input_mismatches)
                    if input_mismatches
                    else ""
                )
                + (
                    " Raw reference audit problems: "
                    + "; ".join(raw_reference_mismatches)
                    if raw_reference_mismatches
                    else ""
                )
                + (
                    " Time audit problems: " + "; ".join(time_mismatches)
                    if time_mismatches
                    else ""
                )
                + (
                    " Figure audit problems: " + "; ".join(figure_audit_problems)
                    if figure_audit_problems
                    else ""
                )
            ),
            audit_path,
        )
    mismatches = _external_audit_artifact_mismatches(comparison_dir, artifacts)
    if mismatches:
        return _row(
            f"external_audit_valid::{comparison_dir.name}",
            0,
            "fail",
            "External comparison audit artifact hashes do not match current files: "
            + "; ".join(mismatches),
            audit_path,
        )
    return _row(
        f"external_audit_valid::{comparison_dir.name}",
        1,
        "pass",
        (
            "External comparison audit records reproducible input hashes, "
            "raw reference hashes, selected times, parameters, artifacts, "
            "and journal-quality figure QA."
        ),
        audit_path,
    )


def _audit_figure_quality_mismatches(record):
    if not isinstance(record, dict):
        return ["figure audit entry is not an object"]
    required = ("nonblank", "pixel_width", "pixel_height")
    missing = [field for field in required if field not in record]
    if missing:
        return [f"figure audit {field}" for field in missing]
    audit = {
        "readable": True,
        "nonblank": bool(record.get("nonblank")),
        "pixel_width": record.get("pixel_width", 0),
        "pixel_height": record.get("pixel_height", 0),
        "pixel_range": record.get("pixel_range", MIN_FIGURE_PIXEL_RANGE),
    }
    return _figure_quality(audit)["problems"]


def _external_audit_time_mismatches(audit):
    selected_times = audit.get("selected_times", {})
    if not isinstance(selected_times, dict):
        return ["selected_times is not an object"]
    required_sections = (
        "hydrus",
        "hydrus_baseline",
        "maizsim",
        "maizsim_baseline",
    )
    mismatches = [
        f"selected_times.{section} is missing or not an object"
        for section in required_sections
        if not isinstance(selected_times.get(section), dict)
    ]
    inputs = audit.get("inputs", {})
    manifest_record = (
        inputs.get("comparison_manifest", {}) if isinstance(inputs, dict) else {}
    )
    manifest_path = manifest_record.get("path")
    if not manifest_path:
        mismatches.append("comparison_manifest path is missing for selected time audit")
        return mismatches
    try:
        manifest = read_comparison_manifest(manifest_path)
        event_time = float(manifest["event_relative_time_h"])
    except Exception as exc:
        mismatches.append(f"selected_time_h comparison is not reproducible: {exc}")
        return mismatches
    hydrus_time = selected_times.get("hydrus", {})
    hydrus_baseline_time = selected_times.get("hydrus_baseline", {})
    mismatches.extend(
        _selected_time_h_mismatches(
            hydrus_time,
            expected=event_time,
            label="hydrus",
        )
    )
    mismatches.extend(
        _selected_time_h_mismatches(
            hydrus_baseline_time,
            expected=0.0,
            label="hydrus_baseline",
        )
    )
    maizsim_time = selected_times.get("maizsim", {})
    if isinstance(maizsim_time, dict) and maizsim_time.get("selected_time_h") not in (
        None,
        "",
    ):
        mismatches.extend(
            _selected_time_h_mismatches(
                maizsim_time,
                expected=event_time,
                label="maizsim",
            )
        )
    maizsim_baseline_time = selected_times.get("maizsim_baseline", {})
    if isinstance(maizsim_baseline_time, dict) and maizsim_baseline_time.get(
        "selected_time_h"
    ) not in (None, ""):
        mismatches.extend(
            _selected_time_h_mismatches(
                maizsim_baseline_time,
                expected=0.0,
                label="maizsim_baseline",
            )
        )
    return mismatches


def _selected_time_h_mismatches(record, *, expected, label):
    if not isinstance(record, dict):
        return []
    selected_time = record.get("selected_time_h")
    if selected_time in (None, ""):
        return [f"{label} selected_time_h is missing"]
    try:
        selected = float(selected_time)
    except (TypeError, ValueError):
        return [f"{label} selected_time_h is not numeric"]
    if not np.isclose(selected, float(expected), rtol=0.0, atol=1.0e-9):
        return [
            (
                f"{label} selected_time_h must match "
                f"{float(expected):g} event-relative hours"
            )
        ]
    return []


def _external_audit_raw_reference_mismatches(records):
    if not isinstance(records, list) or not records:
        return ["raw_reference_files audit is missing or empty"]
    mismatches = []
    roles = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            mismatches.append(f"raw_reference_files[{index}] is not an object")
            continue
        for field in ("role", "path_or_uri", "size_bytes", "sha256"):
            if record.get(field) in (None, ""):
                mismatches.append(f"raw_reference_files[{index}] {field}")
        roles.append(str(record.get("role", "")))
        sha = str(record.get("sha256", "")).strip().casefold()
        if len(sha) != 64 or any(character not in "0123456789abcdef" for character in sha):
            mismatches.append(f"raw_reference_files[{index}] sha256")
        path = str(record.get("path_or_uri", "")).strip()
        required_theta_role = _raw_reference_record_requires_local_file(
            record.get("role", "")
        )
        if not path:
            continue
        if _reference_path_is_uri(path):
            if required_theta_role:
                mismatches.append(
                    (
                        f"raw_reference_files[{index}] local file is required "
                        "for event/baseline theta-field evidence"
                    )
                )
            continue
        file_path = Path(path)
        if not file_path.is_file():
            mismatches.append(f"raw_reference_files[{index}] file is missing")
            continue
        actual = _file_audit(file_path)
        if str(record.get("size_bytes")) != str(actual["size_bytes"]):
            mismatches.append(f"raw_reference_files[{index}] size_bytes")
        if sha != str(actual["sha256"]):
            mismatches.append(f"raw_reference_files[{index}] sha256")
    if not _has_raw_reference_role(
        roles,
        RAW_REFERENCE_EVENT_ROLE_TOKENS,
        exclude_tokens=RAW_REFERENCE_BASELINE_ROLE_TOKENS,
    ):
        mismatches.append("raw_reference_files event/output theta-field role")
    if not _has_raw_reference_role(roles, RAW_REFERENCE_BASELINE_ROLE_TOKENS):
        mismatches.append("raw_reference_files baseline/pre-event theta-field role")
    return mismatches


def _raw_reference_record_requires_local_file(role):
    return _has_raw_reference_role(
        [role],
        RAW_REFERENCE_EVENT_ROLE_TOKENS,
        exclude_tokens=RAW_REFERENCE_BASELINE_ROLE_TOKENS,
    ) or _has_raw_reference_role([role], RAW_REFERENCE_BASELINE_ROLE_TOKENS)


def _has_raw_reference_role(roles, tokens, *, exclude_tokens=()):
    for role in roles:
        normalized = str(role).strip().casefold().replace("-", "_").replace(" ", "_")
        if any(token.replace("-", "_") in normalized for token in exclude_tokens):
            continue
        if any(token.replace("-", "_") in normalized for token in tokens):
            return True
    return False


def _reference_path_is_uri(path):
    return "://" in path or path.startswith("doi:")


def _external_audit_file_mismatches(audit_files, required_keys):
    if not isinstance(audit_files, dict) or not audit_files:
        return ["input file audit is missing or empty"]
    mismatches = []
    for audit_key in required_keys:
        recorded = audit_files.get(audit_key)
        if not isinstance(recorded, dict):
            mismatches.append(f"{audit_key} audit entry is missing")
            continue
        path = recorded.get("path")
        if not path:
            mismatches.append(f"{audit_key} path")
            continue
        file_path = Path(path)
        if not file_path.is_file():
            mismatches.append(f"{audit_key} file is missing")
            continue
        actual = _file_audit(file_path)
        for field in ("size_bytes", "sha256"):
            if str(recorded.get(field)) != str(actual[field]):
                mismatches.append(f"{audit_key} {field}")
    return mismatches


def _external_audit_artifact_mismatches(comparison_dir, audit_artifacts):
    artifact_paths = _external_artifacts(comparison_dir)
    expected = {
        "summary_csv": artifact_paths["summary"],
        "points_csv": artifact_paths["points"],
        "figure": artifact_paths["figure"],
        "comparison_manifest_json": artifact_paths["manifest"],
    }
    mismatches = []
    for audit_key, path in expected.items():
        recorded = audit_artifacts.get(audit_key, {})
        if not isinstance(recorded, dict):
            mismatches.append(f"{audit_key} audit entry is not an object")
            continue
        if path is None:
            mismatches.append(f"{audit_key} file is missing")
            continue
        actual = _file_audit(path)
        for field in ("size_bytes", "sha256"):
            if str(recorded.get(field)) != str(actual[field]):
                mismatches.append(f"{audit_key} {field}")
    return mismatches


def _file_audit(path):
    file_path = Path(path)
    return {
        "size_bytes": int(file_path.stat().st_size),
        "sha256": _sha256(file_path),
    }


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _external_points_content_checks(
    comparison_dir,
    points_path,
    metrics,
    thresholds,
    manifest_path=None,
):
    try:
        points = pd.read_csv(points_path)
    except Exception as exc:
        return [
            _row(
                f"external_points_readable::{comparison_dir.name}",
                0,
                "fail",
                f"External points CSV is not readable: {exc}",
                points_path,
            )
        ]
    rows = [
        _row(
            f"external_points_nonempty::{comparison_dir.name}",
            len(points),
            "pass" if len(points) > 0 else "fail",
            "External points CSV must contain point-level comparison records.",
            points_path,
        )
    ]
    rows.append(
        _required_points_columns_check(
            comparison_dir,
            points_path,
            points,
            (
                "x_cm",
                "depth_cm",
                "area_cm2",
                "hydrus_theta",
                "maizsim_theta",
                "theta_residual",
            ),
            "core_columns_present",
            "Point-level theta comparison columns are required.",
        )
    )
    if "area_cm2" in points.columns:
        rows.append(
            _points_positive_numeric_column_check(
                comparison_dir,
                points_path,
                points,
                "area_cm2",
            )
        )
    if "delta_theta_rmse" in metrics:
        rows.append(
            _required_points_columns_check(
                comparison_dir,
                points_path,
                points,
                (
                    "hydrus_delta_theta",
                    "maizsim_delta_theta",
                    "delta_theta_residual",
                ),
                "delta_columns_present",
                "Point-level delta-theta columns are required.",
            )
        )
    if "point_count" in metrics:
        expected = int(round(_metric(metrics, "point_count")))
        rows.append(
            _row(
                f"external_points_count_matches_summary::{comparison_dir.name}",
                len(points),
                "pass" if len(points) == expected else "fail",
                "Point-level record count must match the summary point_count metric.",
                points_path,
            )
        )
    rows.extend(
        _points_residual_identity_checks(comparison_dir, points_path, points)
    )
    if manifest_path is not None:
        rows.append(
            _external_points_theta_bounds_check(
                comparison_dir,
                points_path,
                points,
                manifest_path,
            )
        )
    rows.extend(
        _external_summary_recomputation_checks(
            comparison_dir,
            points_path,
            points,
            metrics,
        )
    )
    if thresholds["require_source_wet_metrics"] >= 0.5:
        rows.append(
            _required_points_columns_check(
                comparison_dir,
                points_path,
                points,
                ("hydrus_source_wet", "maizsim_source_wet"),
                "source_wet_columns_present",
                "Point-level source-connected wet-body masks are required.",
            )
        )
    if thresholds["require_storage_metrics"] >= 0.5:
        rows.append(
            _required_points_columns_check(
                comparison_dir,
                points_path,
                points,
                ("axisym_volume_cm3", "hydrus_delta_theta", "maizsim_delta_theta"),
                "storage_columns_present",
                "Point-level volume and delta-theta columns are required for storage checks.",
            )
        )
    if thresholds["require_uncertainty_metrics"] >= 0.5:
        rows.append(
            _required_points_columns_check(
                comparison_dir,
                points_path,
                points,
                ("hydrus_theta_sd", "hydrus_delta_theta_sd"),
                "uncertainty_columns_present",
                "Point-level theta uncertainty columns are required.",
            )
        )
    return rows


def _external_points_theta_bounds_check(
    comparison_dir,
    points_path,
    points,
    manifest_path,
):
    try:
        manifest = read_comparison_manifest(manifest_path)
        parameters = manifest["soil_hydraulic_parameters"]
        theta_r = float(parameters["theta_r"])
        theta_s = float(parameters["theta_s"])
    except Exception as exc:
        return _row(
            f"external_points_theta_physical_bounds::{comparison_dir.name}",
            "",
            "fail",
            (
                "Point-level theta physical bounds cannot be checked from the "
                f"same-condition manifest: {exc}"
            ),
            manifest_path,
        )
    if (
        not np.isfinite(theta_r)
        or not np.isfinite(theta_s)
        or theta_r < 0.0
        or theta_s <= theta_r
        or theta_s > 1.0
    ):
        return _row(
            f"external_points_theta_physical_bounds::{comparison_dir.name}",
            "",
            "fail",
            (
                "Manifest soil_hydraulic_parameters must define a physical "
                "0 <= theta_r < theta_s <= 1 bound for external theta fields."
            ),
            manifest_path,
        )
    violations = {}
    for column in ("hydrus_theta", "maizsim_theta"):
        if column not in points.columns:
            violations[column] = "missing"
            continue
        values = _numeric_series(points, column)
        if values is None:
            violations[column] = "non-finite"
            continue
        outside = (values < theta_r - 1.0e-9) | (values > theta_s + 1.0e-9)
        count = int(outside.sum())
        if count > 0:
            violations[column] = count
    violation_count = sum(
        value if isinstance(value, int) else 1 for value in violations.values()
    )
    detail = (
        "Point-level HYDRUS/reference and MAIZSIM theta values must lie within "
        "the soil water-content bounds recorded in the same-condition manifest "
        f"(theta_r={theta_r:g}, theta_s={theta_s:g})."
    )
    if violations:
        detail += " Violations: " + ", ".join(
            f"{column}={value}" for column, value in violations.items()
        )
    return _row(
        f"external_points_theta_physical_bounds::{comparison_dir.name}",
        violation_count,
        "pass" if violation_count == 0 else "fail",
        detail,
        points_path,
    )


def _external_summary_recomputation_checks(
    comparison_dir,
    points_path,
    points,
    metrics,
):
    recomputed = _recompute_external_point_metrics(points)
    checks = (
        "point_count",
        "theta_mae",
        "theta_rmse",
        "theta_bias",
        "theta_corr",
        "hydrus_theta_min",
        "hydrus_theta_max",
        "maizsim_theta_min",
        "maizsim_theta_max",
        "delta_theta_mae",
        "delta_theta_rmse",
        "delta_theta_bias",
        "wet_iou",
        "hydrus_wet_area_cm2",
        "maizsim_wet_area_cm2",
        "wet_intersection_area_cm2",
        "wet_union_area_cm2",
        "hydrus_wet_width_cm",
        "maizsim_wet_width_cm",
        "hydrus_wet_depth_cm",
        "maizsim_wet_depth_cm",
        "peak_delta_distance_cm",
        "source_wet_iou",
        "hydrus_source_wet_area_cm2",
        "maizsim_source_wet_area_cm2",
        "source_wet_intersection_area_cm2",
        "source_wet_union_area_cm2",
        "hydrus_source_wet_width_cm",
        "maizsim_source_wet_width_cm",
        "hydrus_source_wet_depth_cm",
        "maizsim_source_wet_depth_cm",
        "hydrus_delta_storage_cm3",
        "maizsim_delta_storage_cm3",
        "delta_storage_residual_cm3",
        "hydrus_delta_storage_l",
        "maizsim_delta_storage_l",
        "delta_storage_residual_l",
        "delta_theta_volume_rmse",
        "theta_uncertainty_point_count",
        "theta_normalized_rmse",
        "theta_abs_residual_le_2sd_fraction",
        "delta_theta_uncertainty_point_count",
        "delta_theta_normalized_rmse",
        "delta_theta_abs_residual_le_2sd_fraction",
    )
    rows = []
    for metric_name in checks:
        if metric_name not in metrics:
            continue
        if metric_name not in recomputed:
            rows.append(
                _row(
                    (
                        "external_summary_matches_points_"
                        f"{metric_name}::{comparison_dir.name}"
                    ),
                    "",
                    "fail",
                    (
                        f"Summary metric {metric_name!r} cannot be recomputed "
                        "from the point-level CSV because required point columns "
                        "are missing or invalid."
                    ),
                    points_path,
                )
            )
            continue
        reported = _metric(metrics, metric_name)
        expected = float(recomputed[metric_name])
        difference = reported - expected
        rows.append(
            _row(
                (
                    "external_summary_matches_points_"
                    f"{metric_name}::{comparison_dir.name}"
                ),
                difference,
                "pass" if _summary_metric_close(reported, expected) else "fail",
                (
                    f"Summary metric {metric_name!r} must be reproducible from "
                    "the point-level comparison CSV."
                ),
                points_path,
            )
        )
    return rows


def _external_reference_coverage_checks(
    comparison_dir,
    points_path,
    audit_path,
    metrics,
):
    checks = (
        "hydrus_reference_point_count",
        "comparison_point_count",
        "dropped_reference_point_count",
        "comparison_point_fraction",
        "hydrus_reference_area_cm2",
        "comparison_area_cm2",
        "dropped_reference_area_cm2",
        "comparison_area_fraction",
        "hydrus_x_span_cm",
        "hydrus_depth_span_cm",
        "comparison_x_span_cm",
        "comparison_depth_span_cm",
    )
    active_checks = [metric_name for metric_name in checks if metric_name in metrics]
    if not active_checks:
        return []
    try:
        audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
        hydrus_path = _audited_input_file_path(audit, "hydrus_csv", audit_path)
        reference = read_hydrus_theta_csv(hydrus_path)
        points = pd.read_csv(points_path)
        recomputed = _recompute_reference_coverage_metrics(reference, points)
    except Exception as exc:
        return _external_reference_coverage_failure_rows(
            comparison_dir,
            active_checks,
            (
                "External coverage metrics cannot be recomputed from the "
                f"audited HYDRUS reference CSV and point-level CSV: {exc}"
            ),
            audit_path,
        )
    rows = []
    for metric_name in active_checks:
        if metric_name not in recomputed:
            rows.append(
                _row(
                    (
                        "external_summary_matches_reference_"
                        f"{metric_name}::{comparison_dir.name}"
                    ),
                    "",
                    "fail",
                    (
                        f"Summary coverage metric {metric_name!r} cannot be "
                        "recomputed from the audited HYDRUS reference CSV and "
                        "point-level CSV because required coverage data are "
                        "missing or invalid."
                    ),
                    points_path,
                )
            )
            continue
        reported = _metric(metrics, metric_name)
        expected = float(recomputed[metric_name])
        difference = reported - expected
        rows.append(
            _row(
                (
                    "external_summary_matches_reference_"
                    f"{metric_name}::{comparison_dir.name}"
                ),
                difference,
                "pass" if _summary_metric_close(reported, expected) else "fail",
                (
                    f"Summary coverage metric {metric_name!r} must be "
                    "reproducible from the audited HYDRUS reference CSV and "
                    "point-level comparison CSV."
                ),
                points_path,
            )
        )
    return rows


def _external_reference_point_value_checks(comparison_dir, points_path, audit_path):
    check_names = (
        "hydrus_theta",
        "hydrus_delta_theta",
        "hydrus_delta_theta_sd",
    )
    try:
        audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
        hydrus_path = _audited_input_file_path(audit, "hydrus_csv", audit_path)
        hydrus_baseline_path = _audited_input_file_path(
            audit,
            "hydrus_baseline_csv",
            audit_path,
        )
        reference = read_hydrus_theta_csv(hydrus_path)
        baseline = read_hydrus_theta_csv(hydrus_baseline_path)
        points = pd.read_csv(points_path)
        differences = _reference_point_value_differences(
            points,
            reference,
            baseline,
        )
    except Exception as exc:
        return [
            _row(
                f"external_points_match_reference_{check_name}::{comparison_dir.name}",
                "",
                "fail",
                (
                    "External point-level reference values cannot be recomputed "
                    "from audited event and baseline reference CSV files: "
                    f"{exc}"
                ),
                audit_path,
            )
            for check_name in check_names
        ]
    rows = []
    for check_name in check_names:
        if check_name not in differences:
            continue
        difference = float(differences[check_name])
        rows.append(
            _row(
                f"external_points_match_reference_{check_name}::{comparison_dir.name}",
                difference,
                "pass" if difference <= 1.0e-9 else "fail",
                (
                    f"Point-level {check_name} must match values recomputed "
                    "from audited event and baseline reference fields."
                ),
                points_path,
            )
        )
    return rows


def _reference_point_value_differences(points, reference, baseline):
    if not _has_columns(points, ("x_cm", "depth_cm", "hydrus_theta")):
        raise ValueError("Point CSV must include x_cm, depth_cm, and hydrus_theta.")
    if "hydrus_delta_theta" not in points.columns:
        raise ValueError("Point CSV must include hydrus_delta_theta.")
    point_values = _coordinate_values(
        points,
        ("hydrus_theta", "hydrus_delta_theta", "hydrus_delta_theta_sd"),
        require_all=False,
        source="point-level CSV",
    )
    reference_values = _coordinate_values(
        reference,
        ("theta", "theta_sd"),
        require_all=False,
        source="event reference CSV",
    ).rename(columns={"theta": "reference_theta", "theta_sd": "reference_theta_sd"})
    baseline_values = _coordinate_values(
        baseline,
        ("theta", "theta_sd"),
        require_all=False,
        source="baseline reference CSV",
    ).rename(columns={"theta": "baseline_theta", "theta_sd": "baseline_theta_sd"})
    merged = point_values.merge(
        reference_values,
        on=["_x_key", "_depth_key"],
        how="left",
        validate="one_to_one",
    )
    merged = merged.merge(
        baseline_values,
        on=["_x_key", "_depth_key"],
        how="left",
        validate="one_to_one",
    )
    required = ("reference_theta", "baseline_theta")
    missing_reference = merged[list(required)].isna().any(axis=1)
    if missing_reference.any():
        raise ValueError(
            "Point CSV contains coordinates that are not present in both audited "
            "event and baseline reference fields."
        )
    differences = {
        "hydrus_theta": _max_abs_difference(
            merged["hydrus_theta"],
            merged["reference_theta"],
        ),
        "hydrus_delta_theta": _max_abs_difference(
            merged["hydrus_delta_theta"],
            merged["reference_theta"] - merged["baseline_theta"],
        ),
    }
    sd_columns = (
        "hydrus_delta_theta_sd",
        "reference_theta_sd",
        "baseline_theta_sd",
    )
    if all(column in merged.columns for column in sd_columns):
        expected_sd = np.sqrt(
            merged["reference_theta_sd"] ** 2 + merged["baseline_theta_sd"] ** 2
        )
        differences["hydrus_delta_theta_sd"] = _max_abs_difference(
            merged["hydrus_delta_theta_sd"],
            expected_sd,
        )
    return differences


def _coordinate_values(frame, value_columns, *, require_all, source):
    required = ("x_cm", "depth_cm")
    missing_required = [column for column in required if column not in frame.columns]
    if missing_required:
        raise ValueError(f"{source} is missing coordinate columns: {missing_required}.")
    selected_columns = [
        column
        for column in value_columns
        if column in frame.columns
    ]
    if require_all:
        missing_values = [column for column in value_columns if column not in frame.columns]
        if missing_values:
            raise ValueError(f"{source} is missing value columns: {missing_values}.")
    if not selected_columns:
        raise ValueError(f"{source} has no requested value columns.")
    values = frame[list(required) + selected_columns].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any():
        raise ValueError(f"{source} contains non-numeric coordinate or value data.")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError(f"{source} contains non-finite coordinate or value data.")
    values = values.copy()
    values["_x_key"] = values["x_cm"].round(9)
    values["_depth_key"] = values["depth_cm"].round(9)
    duplicate = values.duplicated(subset=["_x_key", "_depth_key"])
    if duplicate.any():
        raise ValueError(f"{source} contains duplicate x_cm/depth_cm coordinates.")
    return values[["_x_key", "_depth_key"] + selected_columns]


def _max_abs_difference(left, right):
    left_values = pd.to_numeric(left, errors="coerce").to_numpy(dtype=float)
    right_values = pd.to_numeric(right, errors="coerce").to_numpy(dtype=float)
    difference = np.abs(left_values - right_values)
    if len(difference) == 0 or not np.isfinite(difference).all():
        return float("inf")
    return float(difference.max())


def _audited_input_file_path(audit, audit_key, audit_path):
    if not isinstance(audit, dict):
        raise ValueError("Audit must be a JSON object.")
    inputs = audit.get("inputs", {})
    if not isinstance(inputs, dict):
        raise ValueError("Audit inputs must be a JSON object.")
    record = inputs.get(audit_key)
    if not isinstance(record, dict):
        raise ValueError(f"Audit input {audit_key!r} is missing.")
    path = record.get("path")
    if not path:
        raise ValueError(f"Audit input {audit_key!r} has no path.")
    file_path = Path(str(path))
    if not file_path.is_absolute():
        file_path = Path(audit_path).parent / file_path
    return file_path.expanduser()


def _external_reference_coverage_failure_rows(
    comparison_dir,
    active_checks,
    detail,
    source,
):
    return [
        _row(
            (
                "external_summary_matches_reference_"
                f"{metric_name}::{comparison_dir.name}"
            ),
            "",
            "fail",
            detail,
            source,
        )
        for metric_name in active_checks
    ]


def _recompute_reference_coverage_metrics(reference, points):
    hydrus_count = float(len(reference))
    comparison_count = float(len(points))
    metrics = {
        "hydrus_reference_point_count": hydrus_count,
        "comparison_point_count": comparison_count,
    }
    reference_x = _numeric_series(reference, "x_cm")
    reference_depth = _numeric_series(reference, "depth_cm")
    points_x = _numeric_series(points, "x_cm") if "x_cm" in points else None
    points_depth = _numeric_series(points, "depth_cm") if "depth_cm" in points else None
    if reference_x is not None:
        metrics["hydrus_x_span_cm"] = _points_span(reference_x)
    if reference_depth is not None:
        metrics["hydrus_depth_span_cm"] = _points_span(reference_depth)
    if points_x is not None:
        metrics["comparison_x_span_cm"] = _points_span(points_x)
    if points_depth is not None:
        metrics["comparison_depth_span_cm"] = _points_span(points_depth)
    if hydrus_count > 0.0:
        metrics["dropped_reference_point_count"] = hydrus_count - comparison_count
        metrics["comparison_point_fraction"] = comparison_count / hydrus_count
    reference_weights = _positive_numeric_series(reference, "area_cm2")
    point_weights = (
        _positive_numeric_series(points, "area_cm2") if "area_cm2" in points else None
    )
    if (
        reference_weights is not None
        and point_weights is not None
        and len(reference_weights) > 0
        and len(point_weights) > 0
    ):
        hydrus_area = float(reference_weights.sum())
        comparison_area = float(point_weights.sum())
        if hydrus_area > 0.0:
            metrics.update(
                {
                    "hydrus_reference_area_cm2": hydrus_area,
                    "comparison_area_cm2": comparison_area,
                    "dropped_reference_area_cm2": hydrus_area - comparison_area,
                    "comparison_area_fraction": comparison_area / hydrus_area,
                }
            )
    return metrics


def _recompute_external_point_metrics(points):
    metrics = {}
    if not _has_columns(points, ("area_cm2",)):
        return metrics
    weights = _positive_numeric_series(points, "area_cm2")
    if weights is None or len(weights) == 0 or float(weights.sum()) <= 0.0:
        return metrics
    metrics["point_count"] = float(len(points))
    if _has_columns(points, ("theta_residual",)):
        residual = _numeric_series(points, "theta_residual")
        if residual is not None:
            metrics["theta_mae"] = _weighted_mae(residual, weights)
            metrics["theta_rmse"] = _weighted_rmse(residual, weights)
            metrics["theta_bias"] = _weighted_mean(residual, weights)
    if _has_columns(points, ("hydrus_theta", "maizsim_theta")):
        hydrus_theta = _numeric_series(points, "hydrus_theta")
        maizsim_theta = _numeric_series(points, "maizsim_theta")
        if hydrus_theta is not None and maizsim_theta is not None:
            metrics["theta_corr"] = _correlation(hydrus_theta, maizsim_theta)
            metrics["hydrus_theta_min"] = float(hydrus_theta.min())
            metrics["hydrus_theta_max"] = float(hydrus_theta.max())
            metrics["maizsim_theta_min"] = float(maizsim_theta.min())
            metrics["maizsim_theta_max"] = float(maizsim_theta.max())
    if _has_columns(points, ("delta_theta_residual",)):
        residual = _numeric_series(points, "delta_theta_residual")
        if residual is not None:
            metrics["delta_theta_mae"] = _weighted_mae(residual, weights)
            metrics["delta_theta_rmse"] = _weighted_rmse(residual, weights)
            metrics["delta_theta_bias"] = _weighted_mean(residual, weights)
    metrics.update(
        _recompute_wet_body_metrics(
            points,
            weights,
            "hydrus_wet",
            "maizsim_wet",
            prefix="wet",
        )
    )
    metrics.update(
        _recompute_wet_body_metrics(
            points,
            weights,
            "hydrus_source_wet",
            "maizsim_source_wet",
            prefix="source_wet",
        )
    )
    if _has_columns(
        points,
        ("axisym_volume_cm3", "hydrus_delta_theta", "maizsim_delta_theta"),
    ):
        volumes = _numeric_series(points, "axisym_volume_cm3")
        hydrus_delta = _numeric_series(points, "hydrus_delta_theta")
        maizsim_delta = _numeric_series(points, "maizsim_delta_theta")
        if (
            volumes is not None
            and hydrus_delta is not None
            and maizsim_delta is not None
            and (volumes > 0.0).all()
        ):
            hydrus_storage = float((hydrus_delta * volumes).sum())
            maizsim_storage = float((maizsim_delta * volumes).sum())
            residual = maizsim_delta - hydrus_delta
            metrics["hydrus_delta_storage_cm3"] = hydrus_storage
            metrics["maizsim_delta_storage_cm3"] = maizsim_storage
            metrics["delta_storage_residual_cm3"] = maizsim_storage - hydrus_storage
            metrics["hydrus_delta_storage_l"] = hydrus_storage / 1000.0
            metrics["maizsim_delta_storage_l"] = maizsim_storage / 1000.0
            metrics["delta_storage_residual_l"] = (
                maizsim_storage - hydrus_storage
            ) / 1000.0
            metrics["delta_theta_volume_rmse"] = _weighted_rmse(residual, volumes)
    metrics.update(
        _recompute_uncertainty_metrics(
            points,
            residual_column="theta_residual",
            sd_column="hydrus_theta_sd",
            prefix="theta",
        )
    )
    metrics.update(
        _recompute_uncertainty_metrics(
            points,
            residual_column="delta_theta_residual",
            sd_column="hydrus_delta_theta_sd",
            prefix="delta_theta",
        )
    )
    if _has_columns(points, ("hydrus_delta_theta", "maizsim_delta_theta")):
        metrics["peak_delta_distance_cm"] = _points_peak_delta_distance(points)
    return metrics


def _recompute_wet_body_metrics(
    points,
    weights,
    hydrus_column,
    maizsim_column,
    *,
    prefix,
):
    if not _has_columns(points, (hydrus_column, maizsim_column, "x_cm", "depth_cm")):
        return {}
    hydrus_wet = _bool_series(points[hydrus_column])
    maizsim_wet = _bool_series(points[maizsim_column])
    if hydrus_wet is None or maizsim_wet is None:
        return {}
    union = hydrus_wet | maizsim_wet
    intersection = hydrus_wet & maizsim_wet
    union_area = float(weights[union].sum())
    if prefix == "wet":
        metric_names = {
            "iou": "wet_iou",
            "hydrus_area": "hydrus_wet_area_cm2",
            "maizsim_area": "maizsim_wet_area_cm2",
            "intersection_area": "wet_intersection_area_cm2",
            "union_area": "wet_union_area_cm2",
            "hydrus_width": "hydrus_wet_width_cm",
            "maizsim_width": "maizsim_wet_width_cm",
            "hydrus_depth": "hydrus_wet_depth_cm",
            "maizsim_depth": "maizsim_wet_depth_cm",
        }
    else:
        metric_names = {
            "iou": "source_wet_iou",
            "hydrus_area": "hydrus_source_wet_area_cm2",
            "maizsim_area": "maizsim_source_wet_area_cm2",
            "intersection_area": "source_wet_intersection_area_cm2",
            "union_area": "source_wet_union_area_cm2",
            "hydrus_width": "hydrus_source_wet_width_cm",
            "maizsim_width": "maizsim_source_wet_width_cm",
            "hydrus_depth": "hydrus_source_wet_depth_cm",
            "maizsim_depth": "maizsim_source_wet_depth_cm",
        }
    return {
        metric_names["hydrus_area"]: float(weights[hydrus_wet].sum()),
        metric_names["maizsim_area"]: float(weights[maizsim_wet].sum()),
        metric_names["intersection_area"]: float(weights[intersection].sum()),
        metric_names["union_area"]: union_area,
        metric_names["iou"]: float(weights[intersection].sum() / union_area)
        if union_area > 0.0
        else 0.0,
        metric_names["hydrus_width"]: _points_span(points.loc[hydrus_wet, "x_cm"]),
        metric_names["maizsim_width"]: _points_span(points.loc[maizsim_wet, "x_cm"]),
        metric_names["hydrus_depth"]: _points_max_or_zero(
            points.loc[hydrus_wet, "depth_cm"]
        ),
        metric_names["maizsim_depth"]: _points_max_or_zero(
            points.loc[maizsim_wet, "depth_cm"]
        ),
    }


def _recompute_uncertainty_metrics(points, *, residual_column, sd_column, prefix):
    if not _has_columns(points, (residual_column, sd_column, "area_cm2")):
        return {}
    values = points[[residual_column, sd_column, "area_cm2"]].apply(
        pd.to_numeric,
        errors="coerce",
    )
    values = values.dropna()
    values = values[(values[sd_column] > 0.0) & (values["area_cm2"] > 0.0)]
    if values.empty:
        return {}
    within = values[residual_column].abs() <= 2.0 * values[sd_column]
    weights = values["area_cm2"].to_numpy(dtype=float)
    normalized = values[residual_column].to_numpy(dtype=float) / values[
        sd_column
    ].to_numpy(dtype=float)
    return {
        f"{prefix}_uncertainty_point_count": float(len(values)),
        f"{prefix}_normalized_rmse": float(
            np.sqrt(np.average(normalized * normalized, weights=weights))
        ),
        f"{prefix}_abs_residual_le_2sd_fraction": float(
            np.average(
                within.astype(float),
                weights=weights,
            )
        )
    }


def _points_peak_delta_distance(points):
    hydrus_delta = _numeric_series(points, "hydrus_delta_theta")
    maizsim_delta = _numeric_series(points, "maizsim_delta_theta")
    if hydrus_delta is None or maizsim_delta is None:
        return 0.0
    coordinates = points[["x_cm", "depth_cm"]].apply(pd.to_numeric, errors="coerce")
    valid = (
        hydrus_delta.notna()
        & maizsim_delta.notna()
        & coordinates["x_cm"].notna()
        & coordinates["depth_cm"].notna()
    )
    if not valid.any():
        return 0.0
    hydrus_delta = hydrus_delta.loc[valid]
    maizsim_delta = maizsim_delta.loc[valid]
    coordinates = coordinates.loc[valid]
    hydrus_max = float(hydrus_delta.max())
    maizsim_max = float(maizsim_delta.max())
    hydrus_tol = max(1.0e-9, abs(hydrus_max) * 1.0e-6)
    maizsim_tol = max(1.0e-9, abs(maizsim_max) * 1.0e-6)
    hydrus_peaks = coordinates.loc[
        hydrus_delta >= hydrus_max - hydrus_tol,
        ["x_cm", "depth_cm"],
    ].to_numpy(dtype=float)
    maizsim_peaks = coordinates.loc[
        maizsim_delta >= maizsim_max - maizsim_tol,
        ["x_cm", "depth_cm"],
    ].to_numpy(dtype=float)
    if len(hydrus_peaks) == 0 or len(maizsim_peaks) == 0:
        return 0.0
    distances = []
    for point in maizsim_peaks:
        delta = hydrus_peaks - point
        distances.append(float(np.min(np.hypot(delta[:, 0], delta[:, 1]))))
    return float(min(distances))


def _has_columns(frame, columns):
    return all(column in frame.columns for column in columns)


def _numeric_series(frame, column):
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any():
        return None
    values = values.astype(float)
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        return None
    return values


def _positive_numeric_series(frame, column):
    values = _numeric_series(frame, column)
    if values is None or (values <= 0.0).any():
        return None
    return values


def _bool_series(values):
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    text = values.astype(str).str.strip().str.lower()
    if text.isin(("true", "false", "1", "0")).all():
        return text.isin(("true", "1"))
    return None


def _weighted_rmse(values, weights):
    return float(np.sqrt(np.average(values * values, weights=weights)))


def _weighted_mae(values, weights):
    return float(np.average(np.abs(values), weights=weights))


def _weighted_mean(values, weights):
    return float(np.average(values, weights=weights))


def _correlation(left, right):
    if len(left) < 2:
        return 0.0
    left_values = left.to_numpy(dtype=float)
    right_values = right.to_numpy(dtype=float)
    if np.allclose(left_values, left_values[0]) or np.allclose(
        right_values,
        right_values[0],
    ):
        return 0.0
    return float(np.corrcoef(left_values, right_values)[0, 1])


def _points_span(values):
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return 0.0
    return float(numeric.max() - numeric.min())


def _points_max_or_zero(values):
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return 0.0
    return float(numeric.max())


def _summary_metric_close(left, right):
    return abs(float(left) - float(right)) <= max(1.0e-9, 1.0e-6 * abs(float(right)))


def _points_residual_identity_checks(comparison_dir, points_path, points):
    checks = (
        (
            "theta_residual_identity",
            "theta_residual",
            "maizsim_theta",
            "hydrus_theta",
        ),
        (
            "delta_theta_residual_identity",
            "delta_theta_residual",
            "maizsim_delta_theta",
            "hydrus_delta_theta",
        ),
    )
    rows = []
    for check_name, residual_name, left_name, right_name in checks:
        columns = (residual_name, left_name, right_name)
        if any(column not in points.columns for column in columns):
            continue
        residual = pd.to_numeric(points[residual_name], errors="coerce")
        left = pd.to_numeric(points[left_name], errors="coerce")
        right = pd.to_numeric(points[right_name], errors="coerce")
        difference = (residual - (left - right)).abs().max()
        value = float(difference) if pd.notna(difference) else float("inf")
        rows.append(
            _row(
                f"external_points_{check_name}::{comparison_dir.name}",
                value,
                "pass" if value <= 1.0e-9 else "fail",
                "Point-level residuals must match their source theta columns.",
                points_path,
            )
        )
    return rows


def _points_positive_numeric_column_check(comparison_dir, points_path, points, column):
    values = _positive_numeric_series(points, column)
    valid = values is not None and len(values) == len(points)
    return _row(
        f"external_points_{column}_positive::{comparison_dir.name}",
        len(points) if valid else 0,
        "pass" if valid else "fail",
        f"Point-level {column} values must be finite and strictly positive.",
        points_path,
    )


def _required_points_columns_check(
    comparison_dir,
    points_path,
    points,
    columns,
    check_name,
    detail,
):
    missing = [column for column in columns if column not in points.columns]
    if missing:
        return _row(
            f"external_points_{check_name}::{comparison_dir.name}",
            0,
            "fail",
            f"{detail} Missing: {', '.join(missing)}.",
            points_path,
        )
    return _row(
        f"external_points_{check_name}::{comparison_dir.name}",
        1,
        "pass",
        detail,
        points_path,
    )


def _shape_difference_checks(comparison_dir, summary_path, metrics, thresholds):
    return [
        _difference_check(
            comparison_dir,
            summary_path,
            metrics,
            "wet_width_error_cm",
            "maizsim_wet_width_cm",
            "hydrus_wet_width_cm",
            thresholds["wet_width_error_cm_max"],
            "Wetted width difference should remain within the journal-readiness gate.",
        ),
        _difference_check(
            comparison_dir,
            summary_path,
            metrics,
            "wet_depth_error_cm",
            "maizsim_wet_depth_cm",
            "hydrus_wet_depth_cm",
            thresholds["wet_depth_error_cm_max"],
            "Wetted depth difference should remain within the journal-readiness gate.",
        ),
    ]


def _difference_check(
    comparison_dir,
    summary_path,
    metrics,
    check_name,
    left_name,
    right_name,
    threshold,
    detail,
):
    missing = [name for name in (left_name, right_name) if name not in metrics]
    if missing:
        return _row(
            f"external_{check_name}::{comparison_dir.name}",
            "",
            "fail",
            f"Missing required external comparison metric(s): {', '.join(missing)}.",
            summary_path,
        )
    difference = _metric(metrics, left_name) - _metric(metrics, right_name)
    return _row(
        f"external_{check_name}::{comparison_dir.name}",
        difference,
        "pass" if abs(difference) <= threshold else "fail",
        detail,
        summary_path,
    )


def _optional_source_wet_check(comparison_dir, summary_path, metrics, thresholds):
    if "source_wet_iou" not in metrics:
        required = thresholds["require_source_wet_metrics"] >= 0.5
        return [
            _row(
                f"external_source_wet_iou_present::{comparison_dir.name}",
                0,
                "fail" if required else "diagnostic",
                "Source-connected wet-body IoU is absent; provide drip-source annotation for a stricter field check.",
                summary_path,
            )
        ]
    value = _metric(metrics, "source_wet_iou")
    return [
        _row(
            f"external_source_wet_iou::{comparison_dir.name}",
            value,
            "pass" if value >= thresholds["source_wet_iou_min"] else "fail",
            "Source-connected wetted bodies should overlap strongly.",
            summary_path,
        )
    ]


def _optional_storage_check(comparison_dir, summary_path, metrics, thresholds):
    required = ("delta_storage_residual_l", "hydrus_delta_storage_l")
    if any(name not in metrics for name in required):
        required_gate = thresholds["require_storage_metrics"] >= 0.5
        return [
            _row(
                f"external_storage_metrics_present::{comparison_dir.name}",
                0,
                "fail" if required_gate else "diagnostic",
                "Storage residual metrics are absent; include volumes for an axisymmetric or volume-weighted check.",
                summary_path,
            )
        ]
    residual = abs(_metric(metrics, "delta_storage_residual_l"))
    hydrus_storage = abs(_metric(metrics, "hydrus_delta_storage_l"))
    relative = residual / max(hydrus_storage, 1.0e-9)
    return [
        _row(
            f"external_delta_storage_rel_error::{comparison_dir.name}",
            relative,
            "pass" if relative <= thresholds["delta_storage_rel_error_max"] else "fail",
            "Delta-water-storage residual should remain within 10% when volume metrics are available.",
            summary_path,
        )
    ]


def _optional_uncertainty_checks(comparison_dir, summary_path, metrics, thresholds):
    metric_names = (
        "theta_abs_residual_le_2sd_fraction",
        "delta_theta_abs_residual_le_2sd_fraction",
    )
    present = [name for name in metric_names if name in metrics]
    missing = [name for name in metric_names if name not in metrics]
    required = thresholds["require_uncertainty_metrics"] >= 0.5
    if not present:
        return [
            _row(
                f"external_observation_uncertainty_metrics_present::{comparison_dir.name}",
                0,
                "fail" if required else "diagnostic",
                (
                    "Observation uncertainty metrics are absent; include theta_sd "
                    "or theta_std columns for measured 2D water-content fields."
                ),
                summary_path,
            )
        ]
    if missing and required:
        return [
            _row(
                f"external_observation_uncertainty_metrics_complete::{comparison_dir.name}",
                0,
                "fail",
                f"Missing required uncertainty metric(s): {', '.join(missing)}.",
                summary_path,
            )
        ]
    rows = []
    for name in present:
        value = _metric(metrics, name)
        rows.append(
            _row(
                f"external_{name}::{comparison_dir.name}",
                value,
                "pass"
                if value >= thresholds["uncertainty_within_2sd_fraction_min"]
                else "fail",
                (
                    "A large fraction of residuals should fall within the "
                    "reported observational uncertainty envelope."
                ),
                summary_path,
            )
        )
    return rows


def _max_check(
    comparison_dir,
    summary_path,
    metrics,
    metric_name,
    threshold,
    *,
    greater_is_better=False,
    detail,
):
    if metric_name not in metrics:
        return _row(
            f"external_{metric_name}::{comparison_dir.name}",
            "",
            "fail",
            f"Missing required external comparison metric {metric_name!r}.",
            summary_path,
        )
    value = _metric(metrics, metric_name)
    if greater_is_better:
        status = "pass" if value >= threshold else "fail"
    else:
        status = "pass" if abs(value) <= threshold else "fail"
    return _row(
        f"external_{metric_name}::{comparison_dir.name}",
        value,
        status,
        detail,
        summary_path,
    )


def _metric(metrics, name):
    value = pd.to_numeric(pd.Series([metrics[name]]), errors="raise").iloc[0]
    return float(value)


def _manifest_diversity_count(manifests, key):
    return len({_canonical_json(manifest.get(key)) for manifest in manifests})


def _manifest_nested_diversity_count(manifests, keys):
    return len(
        {
            _canonical_json(_nested_manifest_value(manifest, keys))
            for manifest in manifests
        }
    )


def _nested_manifest_value(manifest, keys):
    value = manifest
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _manifest_numeric_diversity_count(manifests, key):
    return len({round(float(manifest.get(key)), 9) for manifest in manifests})


def _manifest_numeric_values(manifests, key):
    values = []
    for manifest in manifests:
        value = _finite_positive_float_or_none(manifest.get(key))
        if value is not None:
            values.append(value)
    return values


def _manifest_nested_numeric_values(manifests, keys):
    values = []
    for manifest in manifests:
        value = _finite_positive_float_or_none(_nested_manifest_value(manifest, keys))
        if value is not None:
            values.append(value)
    return values


def _finite_positive_float_or_none(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric) or numeric <= 0.0:
        return None
    return numeric


def _numeric_ratio(values):
    if len(values) < 2:
        return 0.0
    minimum = min(values)
    if minimum <= 0.0:
        return 0.0
    return float(max(values) / minimum)


def _numeric_span(values):
    if len(values) < 2:
        return 0.0
    return float(max(values) - min(values))


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _find_exactly_one(directory, pattern):
    matches = _find_matches(directory, pattern)
    return matches[0] if len(matches) == 1 else None


def _find_matches(directory, pattern):
    return sorted(Path(directory).glob(pattern))


def _row(check, value, status, detail, source):
    return {
        "check": check,
        "value": value,
        "status": status,
        "detail": detail,
        "source": str(source),
    }


def _overall_status(checks):
    statuses = set(checks["status"].astype(str))
    if "fail" in statuses:
        return "fail"
    if "missing_external_evidence" in statuses:
        return "missing_external_evidence"
    return "pass"


def _merge_thresholds(overrides):
    thresholds = dict(DEFAULT_THRESHOLDS)
    if overrides is not None:
        thresholds.update({key: float(value) for key, value in overrides.items()})
    return thresholds


def _threshold_policy_check(thresholds):
    relaxed = _relaxed_journal_thresholds(thresholds)
    return _row(
        "journal_threshold_policy",
        float(len(relaxed)),
        "pass" if not relaxed else "fail",
        (
            "Journal-readiness quality and evidence-scale thresholds must "
            "not be weaker than the default gate; relaxed threshold(s): "
            f"{', '.join(relaxed)}."
            if relaxed
            else (
                "Journal-readiness quality and evidence-scale thresholds are "
                "at least as strict as the default gate."
            )
        ),
        "",
    )


def _relaxed_journal_thresholds(thresholds):
    relaxed = []
    for key in JOURNAL_PROTECTED_THRESHOLDS:
        value = float(thresholds.get(key, DEFAULT_THRESHOLDS[key]))
        default = float(DEFAULT_THRESHOLDS[key])
        if _threshold_is_relaxed(key, value, default):
            relaxed.append(f"{key}={value:g} default={default:g}")
    return relaxed


def _threshold_is_relaxed(key, value, default):
    if key.endswith("_max"):
        return value > default
    if key.endswith("_min") or key.startswith("require_"):
        return value < default
    raise ValueError(f"Threshold {key!r} has no journal policy direction.")


def _parse_args(arguments):
    parser = argparse.ArgumentParser(
        description="Build a journal-readiness gate for MAIZSIM drip evidence.",
    )
    parser.add_argument("--precision-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--external-comparison-dir",
        action="append",
        default=[],
        help=(
            "Directory produced by hydrus_2d_comparison.py. Repeat for multiple "
            "HYDRUS or measured 2D field comparisons."
        ),
    )
    parser.add_argument(
        "--external-case-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["external_case_count_min"],
    )
    parser.add_argument(
        "--external-soil-parameter-set-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["external_soil_parameter_set_count_min"],
    )
    parser.add_argument(
        "--external-irrigation-event-setting-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["external_irrigation_event_setting_count_min"],
    )
    parser.add_argument(
        "--external-output-time-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["external_output_time_count_min"],
    )
    parser.add_argument(
        "--external-soil-ks-ratio-min",
        type=float,
        default=DEFAULT_THRESHOLDS["external_soil_ks_ratio_min"],
    )
    parser.add_argument(
        "--external-emitter-rate-ratio-min",
        type=float,
        default=DEFAULT_THRESHOLDS["external_emitter_rate_ratio_min"],
    )
    parser.add_argument(
        "--external-event-duration-span-h-min",
        type=float,
        default=DEFAULT_THRESHOLDS["external_event_duration_span_h_min"],
    )
    parser.add_argument(
        "--external-output-time-span-h-min",
        type=float,
        default=DEFAULT_THRESHOLDS["external_output_time_span_h_min"],
    )
    parser.add_argument(
        "--root-spatial-record-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_spatial_record_count_min"],
    )
    parser.add_argument(
        "--root-spatial-soil-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_spatial_soil_count_min"],
    )
    parser.add_argument(
        "--root-spatial-grid-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_spatial_grid_count_min"],
    )
    parser.add_argument(
        "--root-spatial-scenario-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_spatial_scenario_count_min"],
    )
    parser.add_argument(
        "--root-spatial-temporal-case-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_spatial_temporal_case_count_min"],
    )
    parser.add_argument(
        "--root-spatial-temporal-date-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_spatial_temporal_date_count_min"],
    )
    parser.add_argument(
        "--root-weighted-delta-theta-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_weighted_delta_theta_min"],
    )
    parser.add_argument(
        "--root-overlap-fraction-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_overlap_fraction_min"],
    )
    parser.add_argument(
        "--root-area-fraction-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_area_fraction_min"],
    )
    parser.add_argument(
        "--root-positive-storage-cm2-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_positive_storage_cm2_min"],
    )
    parser.add_argument(
        "--root-storage-fraction-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_storage_fraction_min"],
    )
    parser.add_argument(
        "--root-temporal-positive-storage-cm2-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_temporal_positive_storage_cm2_min"],
    )
    parser.add_argument(
        "--root-temporal-storage-fraction-min",
        type=float,
        default=DEFAULT_THRESHOLDS["root_temporal_storage_fraction_min"],
    )
    parser.add_argument(
        "--theta-rmse-max",
        type=float,
        default=DEFAULT_THRESHOLDS["theta_rmse_max"],
    )
    parser.add_argument(
        "--delta-theta-rmse-max",
        type=float,
        default=DEFAULT_THRESHOLDS["delta_theta_rmse_max"],
    )
    parser.add_argument(
        "--wet-iou-min",
        type=float,
        default=DEFAULT_THRESHOLDS["wet_iou_min"],
    )
    parser.add_argument(
        "--source-wet-iou-min",
        type=float,
        default=DEFAULT_THRESHOLDS["source_wet_iou_min"],
    )
    parser.add_argument(
        "--require-source-wet-metrics",
        type=float,
        default=DEFAULT_THRESHOLDS["require_source_wet_metrics"],
        help="Use 1 to fail when source-connected wet-body metrics are absent.",
    )
    parser.add_argument(
        "--peak-delta-distance-cm-max",
        type=float,
        default=DEFAULT_THRESHOLDS["peak_delta_distance_cm_max"],
    )
    parser.add_argument(
        "--wet-width-error-cm-max",
        type=float,
        default=DEFAULT_THRESHOLDS["wet_width_error_cm_max"],
    )
    parser.add_argument(
        "--wet-depth-error-cm-max",
        type=float,
        default=DEFAULT_THRESHOLDS["wet_depth_error_cm_max"],
    )
    parser.add_argument(
        "--delta-storage-rel-error-max",
        type=float,
        default=DEFAULT_THRESHOLDS["delta_storage_rel_error_max"],
    )
    parser.add_argument(
        "--require-storage-metrics",
        type=float,
        default=DEFAULT_THRESHOLDS["require_storage_metrics"],
        help="Use 1 to fail when volume/storage metrics are absent.",
    )
    parser.add_argument(
        "--point-count-min",
        type=float,
        default=DEFAULT_THRESHOLDS["point_count_min"],
    )
    parser.add_argument(
        "--comparison-point-fraction-min",
        type=float,
        default=DEFAULT_THRESHOLDS["comparison_point_fraction_min"],
    )
    parser.add_argument(
        "--comparison-area-fraction-min",
        type=float,
        default=DEFAULT_THRESHOLDS["comparison_area_fraction_min"],
    )
    parser.add_argument(
        "--uncertainty-within-2sd-fraction-min",
        type=float,
        default=DEFAULT_THRESHOLDS["uncertainty_within_2sd_fraction_min"],
    )
    parser.add_argument(
        "--require-uncertainty-metrics",
        type=float,
        default=DEFAULT_THRESHOLDS["require_uncertainty_metrics"],
        help="Use 1 to fail when observation uncertainty metrics are absent.",
    )
    return parser.parse_args(arguments)


def _thresholds_from_args(args):
    return {
        "external_case_count_min": args.external_case_count_min,
        "external_soil_parameter_set_count_min": (
            args.external_soil_parameter_set_count_min
        ),
        "external_irrigation_event_setting_count_min": (
            args.external_irrigation_event_setting_count_min
        ),
        "external_output_time_count_min": args.external_output_time_count_min,
        "external_soil_ks_ratio_min": args.external_soil_ks_ratio_min,
        "external_emitter_rate_ratio_min": args.external_emitter_rate_ratio_min,
        "external_event_duration_span_h_min": (
            args.external_event_duration_span_h_min
        ),
        "external_output_time_span_h_min": args.external_output_time_span_h_min,
        "root_spatial_record_count_min": args.root_spatial_record_count_min,
        "root_spatial_soil_count_min": args.root_spatial_soil_count_min,
        "root_spatial_grid_count_min": args.root_spatial_grid_count_min,
        "root_spatial_scenario_count_min": args.root_spatial_scenario_count_min,
        "root_spatial_temporal_case_count_min": (
            args.root_spatial_temporal_case_count_min
        ),
        "root_spatial_temporal_date_count_min": (
            args.root_spatial_temporal_date_count_min
        ),
        "root_weighted_delta_theta_min": args.root_weighted_delta_theta_min,
        "root_overlap_fraction_min": args.root_overlap_fraction_min,
        "root_area_fraction_min": args.root_area_fraction_min,
        "root_positive_storage_cm2_min": args.root_positive_storage_cm2_min,
        "root_storage_fraction_min": args.root_storage_fraction_min,
        "root_temporal_positive_storage_cm2_min": (
            args.root_temporal_positive_storage_cm2_min
        ),
        "root_temporal_storage_fraction_min": args.root_temporal_storage_fraction_min,
        "theta_rmse_max": args.theta_rmse_max,
        "delta_theta_rmse_max": args.delta_theta_rmse_max,
        "wet_iou_min": args.wet_iou_min,
        "source_wet_iou_min": args.source_wet_iou_min,
        "require_source_wet_metrics": args.require_source_wet_metrics,
        "peak_delta_distance_cm_max": args.peak_delta_distance_cm_max,
        "wet_width_error_cm_max": args.wet_width_error_cm_max,
        "wet_depth_error_cm_max": args.wet_depth_error_cm_max,
        "delta_storage_rel_error_max": args.delta_storage_rel_error_max,
        "require_storage_metrics": args.require_storage_metrics,
        "point_count_min": args.point_count_min,
        "comparison_point_fraction_min": args.comparison_point_fraction_min,
        "comparison_area_fraction_min": args.comparison_area_fraction_min,
        "uncertainty_within_2sd_fraction_min": (
            args.uncertainty_within_2sd_fraction_min
        ),
        "require_uncertainty_metrics": args.require_uncertainty_metrics,
    }


if __name__ == "__main__":
    raise SystemExit(main())
