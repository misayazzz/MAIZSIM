"""Strict acceptance checks for HYDRUS-aligned drip wetting bodies."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
import pandas as pd


REQUIRED_SUMMARY_COLUMNS = (
    "hydrus_project",
    "wet_iou",
    "source_wet_iou",
    "hydrus_wet_width_cm",
    "maizsim_wet_width_cm",
    "hydrus_wet_depth_cm",
    "maizsim_wet_depth_cm",
    "delta_storage_residual_l",
    "peak_delta_distance_cm",
    "delta_theta_volume_rmse",
    "g05_boundary_input_closure_residual_mm",
    "g05_boundary_acceptance_residual_mm",
)


@dataclass(frozen=True)
class Goal3Thresholds:
    """Acceptance thresholds for fine HYDRUS 2D wetting-body comparison."""

    min_wet_iou: float = 0.90
    min_source_wet_iou: float = 0.90
    max_width_error_cm: float = 1.0
    max_depth_error_cm: float = 3.0
    max_storage_abs_residual_l: float = 0.4
    max_peak_delta_distance_cm: float = 1.0
    max_delta_theta_volume_rmse: float = 0.006
    max_g05_closure_mm: float = 0.01
    min_png_std: float = 0.001
    min_red_marker_pixels: int = 20


def evaluate_summary(summary_csv, figure=None, thresholds=None):
    """Return row-wise pass/fail checks for one aligned-validation summary."""
    summary_path = Path(summary_csv)
    thresholds = thresholds or Goal3Thresholds()
    frame = pd.read_csv(summary_path)
    case = _case_name(frame, summary_path)
    rows = []

    if len(frame) != 1:
        _add_check(
            rows,
            case,
            "summary_row_count",
            len(frame),
            "1",
            False,
            "Each HYDRUS-aligned summary must contain exactly one case row.",
        )
        return pd.DataFrame(rows)

    row = frame.iloc[0]
    missing = [column for column in REQUIRED_SUMMARY_COLUMNS if column not in frame.columns]
    _add_check(
        rows,
        case,
        "required_summary_columns",
        len(REQUIRED_SUMMARY_COLUMNS) - len(missing),
        f"{len(REQUIRED_SUMMARY_COLUMNS)} required columns",
        not missing,
        "Missing columns: " + ", ".join(missing) if missing else "",
    )
    if missing:
        return pd.DataFrame(rows)

    _numeric_min_check(
        rows,
        case,
        "wet_iou",
        row,
        "wet_iou",
        thresholds.min_wet_iou,
        "Whole wetting-body overlap should be high.",
    )
    _numeric_min_check(
        rows,
        case,
        "source_wet_iou",
        row,
        "source_wet_iou",
        thresholds.min_source_wet_iou,
        "Connected source wetting-body overlap should be high.",
    )
    _paired_abs_error_check(
        rows,
        case,
        "wet_width_error_cm",
        row,
        "maizsim_wet_width_cm",
        "hydrus_wet_width_cm",
        thresholds.max_width_error_cm,
        "Wetted radial width should match the HYDRUS 2D field.",
    )
    _paired_abs_error_check(
        rows,
        case,
        "wet_depth_error_cm",
        row,
        "maizsim_wet_depth_cm",
        "hydrus_wet_depth_cm",
        thresholds.max_depth_error_cm,
        "Wetted depth should match the HYDRUS 2D field.",
    )
    _numeric_abs_max_check(
        rows,
        case,
        "delta_storage_abs_residual_l",
        row,
        "delta_storage_residual_l",
        thresholds.max_storage_abs_residual_l,
        "Storage error should be small enough for shape agreement to be meaningful.",
    )
    _numeric_abs_max_check(
        rows,
        case,
        "peak_delta_distance_cm",
        row,
        "peak_delta_distance_cm",
        thresholds.max_peak_delta_distance_cm,
        "The strongest wetting increment should occur near the HYDRUS peak.",
    )
    _numeric_abs_max_check(
        rows,
        case,
        "delta_theta_volume_rmse",
        row,
        "delta_theta_volume_rmse",
        thresholds.max_delta_theta_volume_rmse,
        "Volume-weighted delta-theta error should remain small.",
    )
    _numeric_abs_max_check(
        rows,
        case,
        "g05_boundary_input_closure_residual_mm",
        row,
        "g05_boundary_input_closure_residual_mm",
        thresholds.max_g05_closure_mm,
        "Drip input must close against pressure loss and accepted infiltration.",
    )
    _numeric_abs_max_check(
        rows,
        case,
        "g05_boundary_acceptance_residual_mm",
        row,
        "g05_boundary_acceptance_residual_mm",
        thresholds.max_g05_closure_mm,
        "Accepted infiltration and hydraulic excess must close.",
    )

    figure_path = Path(figure) if figure is not None else _default_figure_path(summary_path)
    rows.extend(_evaluate_png(figure_path, case, thresholds))
    return pd.DataFrame(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check whether HYDRUS-aligned drip comparisons meet strict goal-3 acceptance."
    )
    parser.add_argument(
        "--summary",
        action="append",
        required=True,
        help="Aligned validation summary CSV. Repeat for multiple cases.",
    )
    parser.add_argument(
        "--figure",
        action="append",
        help="Aligned fields PNG matching --summary order. Defaults to *_aligned_fields.png.",
    )
    parser.add_argument("--output-csv", required=True, help="Path for acceptance check CSV.")
    parser.add_argument("--min-wet-iou", type=float, default=0.90)
    parser.add_argument("--min-source-wet-iou", type=float, default=0.90)
    parser.add_argument("--max-width-error-cm", type=float, default=1.0)
    parser.add_argument("--max-depth-error-cm", type=float, default=3.0)
    parser.add_argument("--max-storage-abs-residual-l", type=float, default=0.4)
    parser.add_argument("--max-peak-delta-distance-cm", type=float, default=1.0)
    parser.add_argument("--max-delta-theta-volume-rmse", type=float, default=0.006)
    parser.add_argument("--max-g05-closure-mm", type=float, default=0.01)
    parser.add_argument("--min-png-std", type=float, default=0.001)
    parser.add_argument("--min-red-marker-pixels", type=int, default=20)
    args = parser.parse_args(argv)

    figures = args.figure or []
    if figures and len(figures) != len(args.summary):
        raise SystemExit("--figure must be omitted or provided once per --summary.")

    thresholds = Goal3Thresholds(
        min_wet_iou=args.min_wet_iou,
        min_source_wet_iou=args.min_source_wet_iou,
        max_width_error_cm=args.max_width_error_cm,
        max_depth_error_cm=args.max_depth_error_cm,
        max_storage_abs_residual_l=args.max_storage_abs_residual_l,
        max_peak_delta_distance_cm=args.max_peak_delta_distance_cm,
        max_delta_theta_volume_rmse=args.max_delta_theta_volume_rmse,
        max_g05_closure_mm=args.max_g05_closure_mm,
        min_png_std=args.min_png_std,
        min_red_marker_pixels=args.min_red_marker_pixels,
    )

    outputs = []
    for index, summary_csv in enumerate(args.summary):
        figure = figures[index] if figures else None
        outputs.append(evaluate_summary(summary_csv, figure=figure, thresholds=thresholds))
    checks = pd.concat(outputs, ignore_index=True)

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    checks.to_csv(output_csv, index=False)
    counts = checks["status"].value_counts().to_dict()
    print(f"Wrote {output_csv}")
    print(f"Status counts: {counts}")
    return 1 if (checks["status"] == "fail").any() else 0


def _case_name(frame, path):
    if "hydrus_project" in frame.columns and not frame.empty:
        value = frame.iloc[0]["hydrus_project"]
        if pd.notna(value):
            return str(value)
    return path.stem


def _default_figure_path(summary_path):
    name = summary_path.name.replace(
        "_aligned_validation_summary.csv",
        "_aligned_fields.png",
    )
    if name == summary_path.name:
        name = summary_path.with_suffix(".png").name
    return summary_path.with_name(name)


def _add_check(rows, case, check, value, threshold, passed, detail):
    rows.append(
        {
            "case": case,
            "check": check,
            "value": value,
            "threshold": threshold,
            "status": "pass" if bool(passed) else "fail",
            "detail": detail,
        }
    )


def _numeric_value(row, column):
    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
    return float(value) if pd.notna(value) else np.nan


def _numeric_min_check(rows, case, check, row, column, threshold, detail):
    value = _numeric_value(row, column)
    _add_check(
        rows,
        case,
        check,
        value,
        f">= {threshold:g}",
        np.isfinite(value) and value >= threshold,
        detail,
    )


def _numeric_abs_max_check(rows, case, check, row, column, threshold, detail):
    value = _numeric_value(row, column)
    _add_check(
        rows,
        case,
        check,
        abs(value) if np.isfinite(value) else value,
        f"<= {threshold:g}",
        np.isfinite(value) and abs(value) <= threshold,
        detail,
    )


def _paired_abs_error_check(
    rows,
    case,
    check,
    row,
    model_column,
    reference_column,
    threshold,
    detail,
):
    model = _numeric_value(row, model_column)
    reference = _numeric_value(row, reference_column)
    error = abs(model - reference) if np.isfinite(model) and np.isfinite(reference) else np.nan
    _add_check(
        rows,
        case,
        check,
        error,
        f"<= {threshold:g}",
        np.isfinite(error) and error <= threshold,
        detail,
    )


def _evaluate_png(path, case, thresholds):
    rows = []
    if not path.exists():
        _add_check(
            rows,
            case,
            "aligned_fields_png_exists",
            str(path),
            "existing PNG",
            False,
            "The 2D comparison image must exist for visual inspection.",
        )
        return rows

    image = mpimg.imread(path)
    rgb = np.asarray(image[..., :3], dtype=float)
    if rgb.size and float(np.nanmax(rgb)) > 1.0:
        rgb = rgb / 255.0
    std = float(np.nanstd(rgb))
    _add_check(
        rows,
        case,
        "aligned_fields_png_nonblank",
        std,
        f">= {thresholds.min_png_std:g}",
        np.isfinite(std) and std >= thresholds.min_png_std,
        "The 2D comparison image should not be blank or nearly uniform.",
    )

    red_mask = (
        (rgb[..., 0] > 0.55)
        & (rgb[..., 1] < 0.45)
        & (rgb[..., 2] < 0.45)
        & (rgb[..., 0] > rgb[..., 1] + 0.15)
        & (rgb[..., 0] > rgb[..., 2] + 0.15)
    )
    red_pixels = int(np.count_nonzero(red_mask))
    _add_check(
        rows,
        case,
        "aligned_fields_png_drip_marker",
        red_pixels,
        f">= {thresholds.min_red_marker_pixels:d} red pixels",
        red_pixels >= thresholds.min_red_marker_pixels,
        "The figure should visibly mark the drip emitter/source region in red.",
    )
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
