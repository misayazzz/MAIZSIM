"""Run a reproducible external 2D-field validation suite for drip irrigation."""

from __future__ import annotations

import argparse
import json
import math
import re
import traceback
from numbers import Real
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .drip_journal_readiness import (
    DEFAULT_THRESHOLDS,
    build_readiness_report,
)
from .hydrus_2d_comparison import (
    compare_theta_fields,
    _file_audit,
    _frame_time_attrs,
    _raw_reference_file_audits,
    _validate_reference_time_matches_manifest,
    _validate_reference_uncertainty_matches_manifest,
    read_comparison_manifest,
    read_hydrus_theta_csv,
    read_maizsim_g03_theta,
    write_comparison_outputs,
)


METRIC_SPECS = (
    ("theta_rmse", "theta_rmse_max", "max", "theta RMSE"),
    ("delta_theta_rmse", "delta_theta_rmse_max", "max", "delta-theta RMSE"),
    (
        "comparison_point_fraction",
        "comparison_point_fraction_min",
        "min",
        "point coverage",
    ),
    (
        "comparison_area_fraction",
        "comparison_area_fraction_min",
        "min",
        "area coverage",
    ),
    ("wet_iou", "wet_iou_min", "min", "wet IoU"),
    ("source_wet_iou", "source_wet_iou_min", "min", "source wet IoU"),
    ("peak_delta_distance_cm", "peak_delta_distance_cm_max", "max", "peak distance"),
    ("wet_width_abs_error_cm", "wet_width_error_cm_max", "max", "wet width error"),
    ("wet_depth_abs_error_cm", "wet_depth_error_cm_max", "max", "wet depth error"),
    (
        "delta_storage_rel_error",
        "delta_storage_rel_error_max",
        "max",
        "storage rel. error",
    ),
    (
        "theta_abs_residual_le_2sd_fraction",
        "uncertainty_within_2sd_fraction_min",
        "min",
        "theta within 2sd",
    ),
    (
        "delta_theta_abs_residual_le_2sd_fraction",
        "uncertainty_within_2sd_fraction_min",
        "min",
        "delta-theta within 2sd",
    ),
)


def main(arguments=None):
    args = _parse_args(arguments)
    report = run_external_validation_suite(
        suite_manifest=args.suite_manifest,
        output_dir=args.output_dir,
        precision_dir=args.precision_dir,
    )
    if arguments is None:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["overall_status"] == "pass" else 1


def run_external_validation_suite(
    suite_manifest,
    output_dir,
    *,
    precision_dir=None,
):
    """Run all external 2D comparisons and then the journal-readiness gate."""
    suite_path = Path(suite_manifest).expanduser().resolve()
    suite = _read_suite_manifest(suite_path)
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    precision_path = _resolve_precision_dir(suite, suite_path, precision_dir)
    thresholds = _readiness_thresholds(suite)
    case_rows = []
    successful_comparison_dirs = []
    for index, case in enumerate(suite["comparisons"], start=1):
        row = _run_case(case, index, suite_path, output_path)
        case_rows.append(row)
        if row["status"] == "pass":
            successful_comparison_dirs.append(row["output_dir"])

    cases = pd.DataFrame.from_records(case_rows)
    cases = _with_derived_metrics(cases)
    cases_path = output_path / "external_validation_cases.csv"
    cases.to_csv(cases_path, index=False)
    suite_diagnostics = _write_suite_diagnostics(cases, output_path, thresholds)
    readiness_dir = output_path / "journal_readiness"
    readiness = build_readiness_report(
        precision_dir=precision_path,
        output_dir=readiness_dir,
        external_comparison_dirs=successful_comparison_dirs,
        thresholds=thresholds,
    )
    case_status_counts = cases["status"].value_counts().to_dict()
    overall_status = _suite_status(case_status_counts, readiness["overall_status"])
    report = {
        "suite_name": str(suite.get("suite_name", suite_path.stem)),
        "overall_status": overall_status,
        "case_count": int(len(cases)),
        "case_status_counts": {
            str(key): int(value)
            for key, value in case_status_counts.items()
        },
        "suite_manifest": str(suite_path),
        "precision_dir": str(precision_path),
        "output_dir": str(output_path),
        "cases_csv": str(cases_path),
        "metric_summary_csv": suite_diagnostics["metric_summary_csv"],
        "metric_panel_figure": suite_diagnostics["metric_panel_figure"],
        "successful_comparison_dirs": successful_comparison_dirs,
        "journal_readiness_report": str(
            readiness_dir / "journal_readiness_report.json"
        ),
        "journal_readiness_status": readiness["overall_status"],
    }
    report_path = output_path / "external_validation_suite_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def _read_suite_manifest(path):
    suite = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(suite, dict):
        raise ValueError(f"Suite manifest must be a JSON object: {path}.")
    comparisons = suite.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise ValueError(
            f"Suite manifest {path} must contain a non-empty comparisons list."
        )
    return suite


def _resolve_precision_dir(suite, suite_path, precision_dir):
    raw_value = precision_dir if precision_dir is not None else suite.get("precision_dir")
    if raw_value in (None, ""):
        raise ValueError(
            "External validation suite requires a precision validation directory "
            "from drip_precision_validation.py."
        )
    path = _resolve_path(raw_value, suite_path)
    if not path.is_dir():
        raise ValueError(f"Precision validation directory not found: {path}.")
    return path


def _readiness_thresholds(suite):
    thresholds = dict(DEFAULT_THRESHOLDS)
    overrides = suite.get("readiness_thresholds", {})
    if not isinstance(overrides, dict):
        raise ValueError("readiness_thresholds must be a JSON object when present.")
    unknown = sorted(set(overrides) - set(DEFAULT_THRESHOLDS))
    if unknown:
        raise ValueError(f"Unknown readiness threshold(s): {unknown}.")
    thresholds.update({key: float(value) for key, value in overrides.items()})
    return thresholds


def _run_case(case, index, suite_path, output_path):
    case_name = _case_name(case, index)
    case_output = output_path / "comparisons" / _safe_name(case_name)
    case_output.mkdir(parents=True, exist_ok=True)
    try:
        comparison_outputs, metrics = _run_case_checked(
            case,
            suite_path,
            case_output,
            case_name,
        )
    except Exception as exc:  # pragma: no cover - trace is asserted indirectly.
        return {
            "case": case_name,
            "status": "fail",
            "output_dir": str(case_output),
            "summary_csv": "",
            "points_csv": "",
            "figure": "",
            "manifest_json": "",
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
        }
    return {
        "case": case_name,
        "status": "pass",
        "output_dir": str(case_output),
        "summary_csv": comparison_outputs["summary_csv"],
        "points_csv": comparison_outputs["points_csv"],
        "figure": comparison_outputs["figure"],
        "manifest_json": comparison_outputs.get("comparison_manifest_json", ""),
        "theta_rmse": metrics.get("theta_rmse", ""),
        "delta_theta_rmse": metrics.get("delta_theta_rmse", ""),
        "wet_iou": metrics.get("wet_iou", ""),
        "source_wet_iou": metrics.get("source_wet_iou", ""),
        "peak_delta_distance_cm": metrics.get("peak_delta_distance_cm", ""),
        **_serializable_metrics(metrics),
        "error": "",
        "traceback": "",
    }


def _run_case_checked(case, suite_path, case_output, case_name):
    _require_case_keys(case, case_name)
    manifest_path = _resolve_path(case["comparison_manifest"], suite_path)
    comparison_manifest = read_comparison_manifest(manifest_path)
    hydrus_path = _resolve_path(case["hydrus_csv"], suite_path)
    maizsim_path = _resolve_path(case["maizsim_g03"], suite_path)
    hydrus_baseline_path = _resolve_path(case["hydrus_baseline_csv"], suite_path)
    maizsim_baseline_path = _resolve_path(case["maizsim_baseline_g03"], suite_path)
    hydrus = read_hydrus_theta_csv(hydrus_path)
    maizsim = read_maizsim_g03_theta(
        maizsim_path,
        case.get("date"),
        case.get("maizsim_date_time"),
    )
    hydrus_baseline = read_hydrus_theta_csv(hydrus_baseline_path)
    _validate_reference_time_matches_manifest(
        comparison_manifest,
        hydrus,
        hydrus_path,
    )
    _validate_reference_uncertainty_matches_manifest(
        comparison_manifest,
        hydrus,
        hydrus_path,
    )
    _validate_reference_uncertainty_matches_manifest(
        comparison_manifest,
        hydrus_baseline,
        hydrus_baseline_path,
    )
    maizsim_baseline = read_maizsim_g03_theta(
        maizsim_baseline_path,
        case.get("date"),
        case.get("maizsim_date_time"),
    )
    drip_x_cm = _case_value_or_manifest(case, comparison_manifest, "drip_x_cm")
    drip_source_left_cm = _case_value_or_manifest(
        case,
        comparison_manifest,
        "drip_source_left_cm",
    )
    drip_source_right_cm = _case_value_or_manifest(
        case,
        comparison_manifest,
        "drip_source_right_cm",
    )
    comparison = compare_theta_fields(
        maizsim,
        hydrus,
        maizsim_baseline=maizsim_baseline,
        hydrus_baseline=hydrus_baseline,
        wet_delta_threshold=float(case.get("wet_delta_threshold", 0.005)),
        drip_x_cm=drip_x_cm,
        drip_source_left_cm=drip_source_left_cm,
        drip_source_right_cm=drip_source_right_cm,
    )
    prefix = _safe_name(str(case.get("prefix", case_name)))
    audit_context = {
        "case_id": case_name,
        "input_files": {
            "maizsim_g03": _file_audit(maizsim_path),
            "hydrus_csv": _file_audit(hydrus_path),
            "maizsim_baseline_g03": _file_audit(maizsim_baseline_path),
            "hydrus_baseline_csv": _file_audit(hydrus_baseline_path),
            "comparison_manifest": _file_audit(manifest_path),
        },
        "selected_times": {
            "maizsim": _frame_time_attrs(maizsim),
            "maizsim_baseline": _frame_time_attrs(maizsim_baseline),
            "hydrus": _frame_time_attrs(hydrus),
            "hydrus_baseline": _frame_time_attrs(hydrus_baseline),
        },
        "parameters": {
            "date": case.get("date"),
            "maizsim_date_time": case.get("maizsim_date_time"),
            "wet_delta_threshold": float(case.get("wet_delta_threshold", 0.005)),
            "interpolation": "matplotlib.tri.LinearTriInterpolator",
        },
        "raw_reference_files": _raw_reference_file_audits(comparison_manifest),
    }
    outputs = write_comparison_outputs(
        comparison,
        case_output,
        prefix=prefix,
        drip_x_cm=drip_x_cm,
        drip_source_left_cm=drip_source_left_cm,
        drip_source_right_cm=drip_source_right_cm,
        comparison_manifest=comparison_manifest,
        audit_context=audit_context,
    )
    return outputs, comparison.metrics


def _require_case_keys(case, case_name):
    required = (
        "maizsim_g03",
        "hydrus_csv",
        "maizsim_baseline_g03",
        "hydrus_baseline_csv",
        "comparison_manifest",
    )
    missing = [key for key in required if case.get(key) in (None, "")]
    if missing:
        raise ValueError(f"Comparison case {case_name!r} is missing {missing}.")


def _case_value_or_manifest(case, manifest, key):
    if key in case and case[key] is not None:
        return case[key]
    return manifest.get(key)


def _case_name(case, index):
    name = case.get("name") or case.get("case") or f"case_{index:03d}"
    return str(name)


def _safe_name(name):
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name).strip())
    return clean.strip("._") or "case"


def _resolve_path(value, suite_path):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(suite_path).parent / path
    return path.resolve()


def _suite_status(case_status_counts, readiness_status):
    if int(case_status_counts.get("fail", 0)) > 0:
        return "fail"
    if readiness_status != "pass":
        return readiness_status
    return "pass"


def _serializable_metrics(metrics):
    row = {}
    for key, value in metrics.items():
        if isinstance(value, Real):
            value = float(value)
            row[key] = value if math.isfinite(value) else ""
        elif value is None:
            row[key] = ""
        else:
            row[key] = value
    return row


def _with_derived_metrics(cases):
    cases = cases.copy()
    _add_abs_difference(
        cases,
        "wet_width_abs_error_cm",
        "maizsim_wet_width_cm",
        "hydrus_wet_width_cm",
    )
    _add_abs_difference(
        cases,
        "wet_depth_abs_error_cm",
        "maizsim_wet_depth_cm",
        "hydrus_wet_depth_cm",
    )
    _add_relative_storage_error(cases)
    return cases


def _add_abs_difference(cases, output_name, left_name, right_name):
    if left_name not in cases.columns or right_name not in cases.columns:
        return
    left = pd.to_numeric(cases[left_name], errors="coerce")
    right = pd.to_numeric(cases[right_name], errors="coerce")
    cases[output_name] = (left - right).abs()


def _add_relative_storage_error(cases):
    required = ("delta_storage_residual_l", "hydrus_delta_storage_l")
    if any(name not in cases.columns for name in required):
        return
    residual = pd.to_numeric(cases["delta_storage_residual_l"], errors="coerce").abs()
    hydrus_storage = pd.to_numeric(cases["hydrus_delta_storage_l"], errors="coerce").abs()
    cases["delta_storage_rel_error"] = residual / hydrus_storage.clip(lower=1.0e-9)


def _write_suite_diagnostics(cases, output_path, thresholds):
    summary = _metric_summary(cases, thresholds)
    summary_path = output_path / "external_validation_metric_summary.csv"
    summary.to_csv(summary_path, index=False)

    figure_path = output_path / "external_validation_metric_panel.png"
    metric_panel = ""
    if _plot_metric_panel(cases, thresholds, figure_path):
        metric_panel = str(figure_path)
    return {
        "metric_summary_csv": str(summary_path),
        "metric_panel_figure": metric_panel,
    }


def _metric_summary(cases, thresholds):
    successful = cases[cases["status"] == "pass"].copy()
    rows = []
    for metric_name, threshold_name, direction, label in METRIC_SPECS:
        if metric_name not in successful.columns:
            continue
        values = pd.to_numeric(successful[metric_name], errors="coerce").dropna()
        if values.empty:
            continue
        threshold = float(thresholds[threshold_name])
        if direction == "min":
            within_gate = values >= threshold
        else:
            within_gate = values <= threshold
        rows.append(
            {
                "metric": metric_name,
                "label": label,
                "case_count": int(len(values)),
                "mean": float(values.mean()),
                "median": float(values.median()),
                "min": float(values.min()),
                "max": float(values.max()),
                "threshold": threshold,
                "gate": direction,
                "pass_fraction": float(within_gate.mean()),
            }
        )
    return pd.DataFrame.from_records(rows)


def _plot_metric_panel(cases, thresholds, figure_path):
    successful = cases[cases["status"] == "pass"].copy()
    if successful.empty:
        return False
    figure_data = _plot_groups(successful)
    if not any(group for group in figure_data):
        return False

    fig, axes = plt.subplots(2, 2, figsize=(8.0, 6.2), constrained_layout=True)
    for ax, title, group in zip(
        axes.ravel(),
        (
            "Field residuals",
            "Wetted-body overlap",
            "Shape and storage errors",
            "Observation uncertainty",
        ),
        figure_data,
    ):
        _plot_metric_group(ax, successful, group, thresholds)
        ax.set_title(title, fontsize=9)
    fig.savefig(figure_path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    return True


def _plot_groups(cases):
    return (
        _available_metrics(cases, ("theta_rmse", "delta_theta_rmse")),
        _available_metrics(
            cases,
            (
                "wet_iou",
                "source_wet_iou",
                "comparison_point_fraction",
                "comparison_area_fraction",
            ),
        ),
        _available_metrics(
            cases,
            (
                "peak_delta_distance_cm",
                "wet_width_abs_error_cm",
                "wet_depth_abs_error_cm",
                "delta_storage_rel_error",
            ),
        ),
        _available_metrics(
            cases,
            (
                "theta_abs_residual_le_2sd_fraction",
                "delta_theta_abs_residual_le_2sd_fraction",
            ),
        ),
    )


def _available_metrics(cases, metric_names):
    names = []
    for name in metric_names:
        if name not in cases.columns:
            continue
        values = pd.to_numeric(cases[name], errors="coerce").dropna()
        if not values.empty:
            names.append(name)
    return names


def _plot_metric_group(ax, cases, metric_names, thresholds):
    if not metric_names:
        ax.text(0.5, 0.5, "not reported", ha="center", va="center", fontsize=8)
        ax.set_axis_off()
        return
    x_values = list(range(len(cases)))
    case_labels = list(cases["case"].astype(str))
    for index, metric_name in enumerate(metric_names):
        spec = _metric_spec(metric_name)
        values = pd.to_numeric(cases[metric_name], errors="coerce")
        x_offset = (index - (len(metric_names) - 1) / 2.0) * 0.16
        xs = [x + x_offset for x in x_values]
        ax.scatter(xs, values, s=14, label=spec["label"])
        threshold = thresholds[spec["threshold_name"]]
        ax.axhline(
            threshold,
            color=f"C{index}",
            linestyle="--",
            linewidth=0.7,
            alpha=0.65,
        )
    ax.set_xticks(x_values)
    ax.set_xticklabels(case_labels, rotation=35, ha="right", fontsize=6)
    ax.tick_params(axis="y", labelsize=7)
    ax.grid(True, axis="y", color="#d9d9d9", linewidth=0.5)
    ax.legend(fontsize=6, frameon=False)


def _metric_spec(metric_name):
    for name, threshold_name, direction, label in METRIC_SPECS:
        if name == metric_name:
            return {
                "threshold_name": threshold_name,
                "direction": direction,
                "label": label,
            }
    raise KeyError(metric_name)


def _parse_args(arguments):
    parser = argparse.ArgumentParser(
        description=(
            "Run a batch of external HYDRUS/measured 2D theta-field "
            "comparisons and build the MAIZSIM drip journal-readiness report."
        ),
    )
    parser.add_argument("--suite-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--precision-dir",
        help=(
            "Override the precision_dir recorded in the suite manifest. "
            "The directory must contain precision_validation_checks.csv."
        ),
    )
    return parser.parse_args(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
