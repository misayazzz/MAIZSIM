from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
import pandas as pd

from .drip_regression import (
    BASE_RUN_RELATIVE,
    DEFAULT_GRIDS,
    DEFAULT_SOILS,
    EXECUTABLE_NAME,
    DripScenario,
    RegressionCase,
    grid_surface_widths,
    prepare_regression_case,
    read_g05,
    validate_case_output,
    _grid_layout,
)
from .drip_validation import parse_drip_file
from .hydrus_drip_calibration import (
    HYDRUS_SURFACE_DRIP_WIDTH_CURVES_CM,
    calibrated_drip_wet_width_max_cm,
    hydrus_surface_drip_width_cm,
)
from .model_runner import run_model


REPO = Path(__file__).resolve().parents[2]
REGRESSION_ROOT = REPO / "tmp" / "codex_drip_regression_precision"
SHORT_ROOT = REPO / "tmp" / "codex_precision_drip_short_runs"
OUT_DIR = REPO / "tmp" / "codex_precision_drip_validation"
DRIP_MARKER_COLOR = "#d62828"
TOP_DEPTH_CM = 60.0
DATE_FOR_PLATE = "06/01/2007"


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 7,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.8,
        "legend.frameon": False,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.minor.visible": False,
        "ytick.minor.visible": False,
    }
)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHORT_ROOT.mkdir(parents=True, exist_ok=True)

    case_matrix = _build_case_matrix()
    case_matrix.to_csv(OUT_DIR / "precision_case_matrix.csv", index=False)

    curve_targets = _build_hydrus_curve_targets()
    curve_targets.to_csv(OUT_DIR / "precision_hydrus_curve_width.csv", index=False)

    surface_coverage = _build_surface_partial_coverage()
    surface_coverage.to_csv(
        OUT_DIR / "precision_surface_partial_coverage.csv",
        index=False,
    )

    curve_matrix = _run_hydrus_curve_cases()
    curve_matrix.to_csv(
        OUT_DIR / "precision_hydrus_curve_model_width.csv",
        index=False,
    )

    short_matrix = curve_matrix[curve_matrix["elapsed_hours"] == 2.0].copy()
    short_matrix.to_csv(OUT_DIR / "precision_short_hydrus_width.csv", index=False)

    spatial = _build_spatial_diagnostics()
    spatial.to_csv(OUT_DIR / "precision_spatial_delta_root.csv", index=False)

    pressure = _build_pressure_diagnostics()
    pressure.to_csv(OUT_DIR / "precision_pressure_width_diagnostics.csv", index=False)

    checks = _build_checks(
        case_matrix,
        curve_targets,
        curve_matrix,
        short_matrix,
        spatial,
        pressure,
        surface_coverage,
    )
    checks.to_csv(OUT_DIR / "precision_validation_checks.csv", index=False)

    _plot_case_widths(case_matrix)
    _plot_curve_widths(curve_targets, curve_matrix)
    _plot_short_widths(short_matrix)
    _plot_delta_root_plate()
    _plot_spatial_shape_metrics(spatial)

    outputs = {
        "csv": [
            str(OUT_DIR / "precision_case_matrix.csv"),
            str(OUT_DIR / "precision_hydrus_curve_width.csv"),
            str(OUT_DIR / "precision_surface_partial_coverage.csv"),
            str(OUT_DIR / "precision_hydrus_curve_model_width.csv"),
            str(OUT_DIR / "precision_short_hydrus_width.csv"),
            str(OUT_DIR / "precision_spatial_delta_root.csv"),
            str(OUT_DIR / "precision_pressure_width_diagnostics.csv"),
            str(OUT_DIR / "precision_validation_checks.csv"),
        ],
        "figures": [
            str(OUT_DIR / "precision_case_widths.png"),
            str(OUT_DIR / "precision_hydrus_curve_width.png"),
            str(OUT_DIR / "precision_short_hydrus_width.png"),
            str(OUT_DIR / "precision_delta_theta_root_overlay_0601.png"),
            str(OUT_DIR / "precision_spatial_shape_metrics.png"),
        ],
    }
    (OUT_DIR / "precision_validation_outputs.json").write_text(
        json.dumps(outputs, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(outputs, indent=2))


def _build_case_matrix():
    rows = []
    for case_dir in sorted(REGRESSION_ROOT.iterdir()):
        if not case_dir.is_dir() or "__" not in case_dir.name:
            continue
        soil, grid, scenario = _split_case(case_dir.name)
        g05 = _read_g05(case_dir / "LOAM2D.G05")
        if scenario == "baseline":
            width_limit = 0.0
            spread_modes = ()
        else:
            schedule = parse_drip_file(case_dir / "LOAM2D.drp")
            width_limit = max(
                [event.wet_width_max_cm for event in schedule.events],
                default=0.0,
            )
            spread_modes = tuple(sorted({event.spread_mode for event in schedule.events}))
        active = g05[g05["DripDemand"] > 1.0e-9]
        width_max = float(g05["DripWetWidthMax"].max())
        rows.append(
            {
                "case": case_dir.name,
                "soil": soil,
                "grid": grid,
                "scenario": scenario,
                "spread_modes": " ".join(str(mode) for mode in spread_modes),
                "drip_input_mm": float(g05["DripInput"].sum()),
                "drip_demand_mm": float(g05["DripDemand"].sum()),
                "drip_pressure_loss_mm": float(g05["DripPressureLoss"].sum()),
                "drip_hydraulic_excess_mm": float(g05["DripHydraulicExcess"].sum()),
                "runoff_mm": float(g05["Runoff"].sum()),
                "wet_nodes_max": float(g05["DripWetNodesMax"].max()),
                "wet_width_mean_cm": float(active["DripWetWidthMean"].mean()) if not active.empty else 0.0,
                "wet_width_max_cm": width_max,
                "wet_width_limit_cm": width_limit,
                "wet_width_to_limit": width_max / width_limit if width_limit > 0.0 else 0.0,
                "demand_input_loss_residual_mm": float(
                    g05["DripDemand"].sum()
                    - g05["DripInput"].sum()
                    - g05["DripPressureLoss"].sum()
                ),
            }
        )
    return pd.DataFrame.from_records(rows)


def _build_hydrus_curve_targets():
    rows = []
    soils = [soil for soil in DEFAULT_SOILS if soil.name in ("sandy_loam", "loam")]
    grids = [
        grid
        for grid in DEFAULT_GRIDS
        if grid.name in ("narrow_x075", "base_x100", "wide_x125")
    ]
    for soil in soils:
        for grid in grids:
            width_limit = calibrated_drip_wet_width_max_cm(soil.name)
            for elapsed_hours in _hydrus_curve_hours(soil.name):
                grid_path = (
                    REGRESSION_ROOT
                    / f"{soil.name}__{grid.name}__baseline"
                    / "LOAM2D.grd"
                )
                widths, _ = grid_surface_widths(grid_path)
                target_width = hydrus_surface_drip_width_cm(
                    soil.name,
                    elapsed_hours,
                    width_limit,
                )
                coverage = _partial_coverage_at_target(
                    grid_path,
                    center_node=7,
                    target_width=target_width,
                )
                complete_segment_width = _discrete_width_at_or_below_target(
                    grid_path,
                    center_node=7,
                    target_width=target_width,
                )
                rows.append(
                    {
                        "soil": soil.name,
                        "grid": grid.name,
                        "elapsed_hours": elapsed_hours,
                        "center_width_cm": widths[7],
                        "target_left_cm": coverage["target_left_cm"],
                        "target_right_cm": coverage["target_right_cm"],
                        "surface_left_cm": coverage["surface_left_cm"],
                        "surface_right_cm": coverage["surface_right_cm"],
                        "hydrus_target_width_cm": target_width,
                        "domain_clipped_target_width_cm": coverage[
                            "domain_clipped_target_width_cm"
                        ],
                        "complete_segment_width_cm": complete_segment_width,
                        "partial_covered_width_cm": coverage[
                            "partial_covered_width_cm"
                        ],
                        "discrete_target_width_cm": coverage[
                            "partial_covered_width_cm"
                        ],
                        "domain_clip_loss_cm": coverage["domain_clip_loss_cm"],
                        "segment_quantization_error_cm": coverage[
                            "segment_quantization_error_cm"
                        ],
                        "partial_active_nodes": coverage["partial_active_nodes"],
                        "partial_edge_nodes": coverage["partial_edge_nodes"],
                        "target_not_expressible_cm": (
                            target_width - coverage["partial_covered_width_cm"]
                        ),
                        "complete_segment_not_expressible_cm": (
                            target_width - complete_segment_width
                        ),
                    }
                )
    return pd.DataFrame.from_records(rows)


def _build_surface_partial_coverage():
    rows = []
    soils = [soil for soil in DEFAULT_SOILS if soil.name in ("sandy_loam", "loam")]
    grids = [
        grid
        for grid in DEFAULT_GRIDS
        if grid.name in ("narrow_x075", "base_x100", "wide_x125")
    ]
    for soil in soils:
        for grid in grids:
            width_limit = calibrated_drip_wet_width_max_cm(soil.name)
            grid_path = (
                REGRESSION_ROOT
                / f"{soil.name}__{grid.name}__baseline"
                / "LOAM2D.grd"
            )
            for elapsed_hours in _hydrus_curve_hours(soil.name):
                target_width = hydrus_surface_drip_width_cm(
                    soil.name,
                    elapsed_hours,
                    width_limit,
                )
                coverage = _partial_coverage_at_target(
                    grid_path,
                    center_node=7,
                    target_width=target_width,
                )
                for segment in coverage["segments"]:
                    rows.append(
                        {
                            "soil": soil.name,
                            "grid": grid.name,
                            "elapsed_hours": elapsed_hours,
                            "node": segment["node"],
                            "x_cm": segment["x"],
                            "segment_left_cm": segment["segment_left"],
                            "segment_right_cm": segment["segment_right"],
                            "segment_width_cm": segment["width"],
                            "covered_width_cm": segment["covered_width"],
                            "covered_fraction": segment["covered_fraction"],
                            "node_weight": segment["node_weight"],
                            "flux_fraction": segment["flux_fraction"],
                        }
                    )
    return pd.DataFrame.from_records(rows)


def _run_hydrus_curve_cases():
    rows = []
    soils = [soil for soil in DEFAULT_SOILS if soil.name in ("sandy_loam", "loam")]
    grids = [
        grid
        for grid in DEFAULT_GRIDS
        if grid.name in ("narrow_x075", "base_x100", "wide_x125")
    ]
    for soil in soils:
        for grid in grids:
            width_limit = calibrated_drip_wet_width_max_cm(soil.name)
            for elapsed_hours in _model_curve_hours(soil.name):
                slug = _duration_slug(elapsed_hours)
                event_stop_hours = elapsed_hours + 0.005
                scenario = DripScenario(
                    name=f"hydrus_{slug}h_single",
                    event_line=(
                        "'05/01/2007' 0.0 "
                        f"'05/01/2007' {event_stop_hours:g} 0.08 1 "
                        f"0 0 1 0 0 {width_limit:g} 1"
                    ),
                    node_line=" 7",
                )
                run_dir = SHORT_ROOT / f"{soil.name}__{grid.name}__{scenario.name}"
                case = RegressionCase(
                    name=run_dir.name,
                    soil=soil,
                    grid=grid,
                    scenario=scenario,
                    run_dir=run_dir,
                )
                _prepare_short_case(case)
                _run_case_if_needed(case)
                metric = validate_case_output(case)
                g05 = _read_g05(run_dir / "LOAM2D.G05")
                widths, _ = grid_surface_widths(run_dir / "LOAM2D.grd")
                target_width = hydrus_surface_drip_width_cm(
                    soil.name,
                    elapsed_hours,
                    width_limit,
                )
                coverage = _partial_coverage_at_target(
                    run_dir / "LOAM2D.grd",
                    center_node=7,
                    target_width=target_width,
                )
                complete_segment_width = _discrete_width_at_or_below_target(
                    run_dir / "LOAM2D.grd",
                    center_node=7,
                    target_width=target_width,
                )
                rows.append(
                    {
                        "case": case.name,
                        "soil": soil.name,
                        "grid": grid.name,
                        "elapsed_hours": elapsed_hours,
                        "event_stop_hours": event_stop_hours,
                        "center_width_cm": widths[7],
                        "target_left_cm": coverage["target_left_cm"],
                        "target_right_cm": coverage["target_right_cm"],
                        "surface_left_cm": coverage["surface_left_cm"],
                        "surface_right_cm": coverage["surface_right_cm"],
                        "hydrus_target_width_cm": target_width,
                        "domain_clipped_target_width_cm": coverage[
                            "domain_clipped_target_width_cm"
                        ],
                        "complete_segment_width_cm": complete_segment_width,
                        "partial_covered_width_cm": coverage[
                            "partial_covered_width_cm"
                        ],
                        "discrete_target_width_cm": coverage[
                            "partial_covered_width_cm"
                        ],
                        "actual_wet_width_max_cm": metric.drip_wet_width_max_cm,
                        "actual_wet_nodes_max": metric.drip_wet_nodes_max,
                        "width_error_vs_discrete_cm": (
                            metric.drip_wet_width_max_cm
                            - coverage["partial_covered_width_cm"]
                        ),
                        "domain_clip_loss_cm": coverage["domain_clip_loss_cm"],
                        "segment_quantization_error_cm": coverage[
                            "segment_quantization_error_cm"
                        ],
                        "partial_active_nodes": coverage["partial_active_nodes"],
                        "partial_edge_nodes": coverage["partial_edge_nodes"],
                        "target_not_expressible_cm": (
                            target_width - coverage["partial_covered_width_cm"]
                        ),
                        "complete_segment_not_expressible_cm": (
                            target_width - complete_segment_width
                        ),
                        "drip_input_mm": metric.drip_sum_mm,
                        "drip_demand_mm": metric.drip_demand_sum_mm,
                        "drip_hydraulic_excess_mm": metric.drip_hydraulic_excess_sum_mm,
                        "active_output_rows": int((g05["DripDemand"] > 0.0).sum()),
                    }
                )
    return pd.DataFrame.from_records(rows)


def _prepare_short_case(case):
    if case.run_dir.exists():
        shutil.rmtree(case.run_dir)
    prepare_regression_case(
        REPO / BASE_RUN_RELATIVE,
        REPO / "build" / "maizsim" / "x64" / "Release",
        case,
    )
    _write_short_time_file(case.run_dir / "LOAM2D.tim")


def _run_case_if_needed(case):
    result = run_model(
        case.run_dir,
        executable=EXECUTABLE_NAME,
        timeout_seconds=180,
    )
    if not result.success:
        raise RuntimeError(result.message)


def _write_short_time_file(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if "'04/28/2007'" in line and "'07/04/2007'" in line:
            lines[index] = "'04/28/2007'   0.0001        0.0000001     1.3           0.3          '05/03/2007'"
        elif line.strip() == "1             0":
            lines[index] = " 1             1 "
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _hydrus_curve_hours(soil_name):
    curve = HYDRUS_SURFACE_DRIP_WIDTH_CURVES_CM[str(soil_name)]
    return tuple(time for time, _ in curve if time > 0.0)


def _model_curve_hours(soil_name):
    return tuple(time for time in _hydrus_curve_hours(soil_name) if time >= 0.5)


def _duration_slug(elapsed_hours):
    return f"{elapsed_hours:g}".replace(".", "p")


def _build_spatial_diagnostics():
    rows = []
    for soil in ("clay_loam", "loam", "sandy_loam"):
        baseline = REGRESSION_ROOT / f"{soil}__base_x100__baseline"
        drip = REGRESSION_ROOT / f"{soil}__base_x100__long_high_single"
        baseline_g03 = _read_g03(baseline / "LOAM2D.G03")
        drip_g03 = _read_g03(drip / "LOAM2D.G03")
        root_g04 = _read_g04(drip / "LOAM2D.G04")
        node_x, _ = _grid_node_xy(drip / "LOAM2D.grd", 7)
        frame = _delta_root_frame(baseline_g03, drip_g03, root_g04, DATE_FOR_PLATE)
        positive = frame["delta_theta"] > 0.005
        root_positive = frame["root_density"] > 0.0
        peak_index = int(frame["delta_theta"].idxmax())
        positive_frame = frame.loc[positive].copy()
        positive_area = float(positive_frame["Area"].sum()) if positive.any() else 0.0
        positive_delta_weight = (
            positive_frame["delta_theta"].clip(lower=0.0) * positive_frame["Area"]
        )
        positive_delta_weight_sum = float(positive_delta_weight.sum())
        if positive_delta_weight_sum > 0.0:
            centroid_x = float(
                (positive_frame["X"] * positive_delta_weight).sum()
                / positive_delta_weight_sum
            )
            centroid_depth = float(
                (positive_frame["depth_cm"] * positive_delta_weight).sum()
                / positive_delta_weight_sum
            )
        else:
            centroid_x = 0.0
            centroid_depth = 0.0
        root_area_weight = frame["root_density"].clip(lower=0.0) * frame["Area"]
        root_area_weight_sum = float(root_area_weight.sum())
        root_weighted_delta = (
            float((frame["delta_theta"] * root_area_weight).sum() / root_area_weight_sum)
            if root_area_weight_sum > 0.0
            else 0.0
        )
        positive_x_span = _span(frame.loc[positive, "X"])
        positive_max_depth = (
            float(frame.loc[positive, "depth_cm"].max()) if positive.any() else 0.0
        )
        positive_root_area = (
            float(frame.loc[positive & root_positive, "Area"].sum())
            if positive.any()
            else 0.0
        )
        peak_x = float(frame.loc[peak_index, "X"])
        rows.append(
            {
                "soil": soil,
                "grid": "base_x100",
                "scenario": "long_high_single",
                "date": DATE_FOR_PLATE,
                "drip_node_x_cm": node_x,
                "delta_theta_max": float(frame.loc[peak_index, "delta_theta"]),
                "peak_delta_x_cm": peak_x,
                "peak_delta_depth_cm": float(frame.loc[peak_index, "depth_cm"]),
                "peak_offset_from_drip_cm": abs(peak_x - node_x),
                "positive_delta_nodes_top60": int(positive.sum()),
                "positive_delta_area_cm2": positive_area,
                "positive_delta_x_span_cm": positive_x_span,
                "positive_delta_max_depth_cm": positive_max_depth,
                "positive_delta_depth_width_ratio": positive_max_depth / positive_x_span
                if positive_x_span > 0.0
                else 0.0,
                "positive_delta_centroid_x_cm": centroid_x,
                "positive_delta_centroid_depth_cm": centroid_depth,
                "positive_delta_root_overlap_fraction": float((positive & root_positive).sum() / positive.sum())
                if positive.any()
                else 0.0,
                "positive_delta_root_area_fraction": positive_root_area / positive_area
                if positive_area > 0.0
                else 0.0,
                "root_weighted_delta_theta": root_weighted_delta,
            }
        )
    return pd.DataFrame.from_records(rows)


def _build_pressure_diagnostics():
    rows = []
    for case_dir in sorted(REGRESSION_ROOT.glob("*__long_pressure_single")):
        if not case_dir.is_dir():
            continue
        soil, grid, scenario = _split_case(case_dir.name)
        g05 = _read_g05(case_dir / "LOAM2D.G05")
        active = g05[g05["DripDemand"] > 1.0e-9].copy()
        width_diff = active["DripWetWidthMax"].diff().fillna(0.0)
        decrease_count = int((width_diff < -1.0e-6).sum())
        rows.append(
            {
                "case": case_dir.name,
                "soil": soil,
                "grid": grid,
                "scenario": scenario,
                "active_output_rows": int(len(active)),
                "wet_width_start_cm": float(active["DripWetWidthMax"].iloc[0])
                if not active.empty
                else 0.0,
                "wet_width_max_cm": float(active["DripWetWidthMax"].max())
                if not active.empty
                else 0.0,
                "wet_width_decrease_count": decrease_count,
                "pressure_factor_min": float(active["DripPressureFactorMin"].min())
                if not active.empty
                else 0.0,
                "drip_pressure_loss_mm": float(active["DripPressureLoss"].sum())
                if not active.empty
                else 0.0,
            }
        )
    return pd.DataFrame.from_records(rows)


def _build_checks(
    case_matrix,
    curve_targets,
    curve_matrix,
    short_matrix,
    spatial,
    pressure,
    surface_coverage,
):
    active = case_matrix[case_matrix["scenario"] != "baseline"].copy()
    curve_error_abs_max = float(curve_matrix["width_error_vs_discrete_cm"].abs().max())
    curve_target_unexpressed_abs_max = float(
        curve_targets["target_not_expressible_cm"].abs().max()
    )
    single_node_cases = float(
        (
            active["soil"].isin(("loam", "sandy_loam"))
            & (active["wet_nodes_max"] <= 1.0)
        ).sum()
    )
    flux_fraction_error_abs_max = float(
        surface_coverage.groupby(["soil", "grid", "elapsed_hours"])[
            "flux_fraction"
        ]
        .sum()
        .sub(1.0)
        .abs()
        .max()
    )
    rows = [
        {
            "check": "case_count",
            "value": float(len(case_matrix)),
            "status": "pass" if len(case_matrix) == 45 else "fail",
            "detail": "Expected 45 cases for 3 soils x 3 grids x 5 scenarios.",
        },
        {
            "check": "water_balance_residual_abs_max_mm",
            "value": float(active["demand_input_loss_residual_mm"].abs().max()),
            "status": "pass" if active["demand_input_loss_residual_mm"].abs().max() < 0.01 else "fail",
            "detail": "Checks DripDemand = DripInput + DripPressureLoss.",
        },
        {
            "check": "wet_width_limit_violations",
            "value": float((active["wet_width_max_cm"] > active["wet_width_limit_cm"] + 0.05).sum()),
            "status": "pass"
            if (active["wet_width_max_cm"] > active["wet_width_limit_cm"] + 0.05).sum() == 0
            else "fail",
            "detail": "Actual wet width should stay within configured caps.",
        },
        {
            "check": "loam_sandy_single_node_cases",
            "value": single_node_cases,
            "status": "pass" if single_node_cases == 0.0 else "review",
            "detail": (
                "Remaining single-node cases would indicate grid discretization "
                "still cannot express the target width."
            ),
        },
        {
            "check": "short_width_error_abs_max_cm",
            "value": float(short_matrix["width_error_vs_discrete_cm"].abs().max()),
            "status": "pass"
            if short_matrix["width_error_vs_discrete_cm"].abs().max() < 0.8
            else "fail",
            "detail": (
                "2 h short cases should match the partial-covered HYDRUS target "
                "within model output-cadence tolerance."
            ),
        },
        {
            "check": "hydrus_curve_width_error_abs_max_cm",
            "value": curve_error_abs_max,
            "status": "pass" if curve_error_abs_max < 0.8 else "fail",
            "detail": (
                "HYDRUS curve-node cases should match the partial-covered target "
                "within model output-cadence tolerance."
            ),
        },
        {
            "check": "partial_flux_fraction_error_abs_max",
            "value": flux_fraction_error_abs_max,
            "status": "pass" if flux_fraction_error_abs_max < 1.0e-9 else "fail",
            "detail": (
                "Per-boundary partial coverage flux fractions should sum to one "
                "for every target case."
            ),
        },
        {
            "check": "hydrus_curve_target_unexpressed_abs_max_cm",
            "value": curve_target_unexpressed_abs_max,
            "status": "review",
            "detail": (
                "Continuous HYDRUS target width not expressible after partial "
                "boundary coverage, usually because the target interval reaches "
                "the modeled surface edge."
            ),
        },
        {
            "check": "pressure_width_decrease_cases",
            "value": float((pressure["wet_width_decrease_count"] > 0).sum()),
            "status": "pass"
            if (pressure["wet_width_decrease_count"] == 0).all()
            else "fail",
            "detail": "Pressure-compensated runs should not shrink target wet width while active.",
        },
        {
            "check": "pressure_loss_positive_cases",
            "value": float((pressure["drip_pressure_loss_mm"] > 0.0).sum()),
            "status": "diagnostic",
            "detail": "Counts pressure runs where pressure correction reduced applied drip water.",
        },
        {
            "check": "spatial_positive_delta_records",
            "value": float((spatial["delta_theta_max"] > 0.005).sum()),
            "status": "pass" if (spatial["delta_theta_max"] > 0.005).all() else "fail",
            "detail": "Selected 2D plates should show local positive wetting.",
        },
        {
            "check": "spatial_peak_offset_abs_max_cm",
            "value": float(spatial["peak_offset_from_drip_cm"].abs().max()),
            "status": "pass"
            if spatial["peak_offset_from_drip_cm"].abs().max() <= 0.5
            else "review",
            "detail": "Peak wetting should remain at or very near the marked dripper.",
        },
        {
            "check": "spatial_positive_area_records",
            "value": float((spatial["positive_delta_area_cm2"] > 0.0).sum()),
            "status": "pass"
            if (spatial["positive_delta_area_cm2"] > 0.0).all()
            else "fail",
            "detail": "Positive delta-theta areas should be non-empty in selected 2D plates.",
        },
        {
            "check": "spatial_root_weighted_delta_records",
            "value": float((spatial["root_weighted_delta_theta"] > 0.0).sum()),
            "status": "pass"
            if (spatial["root_weighted_delta_theta"] > 0.0).all()
            else "review",
            "detail": "Root-zone weighted delta theta should be positive for the selected plate date.",
        },
    ]
    return pd.DataFrame.from_records(rows)


def _plot_case_widths(case_matrix):
    active = case_matrix[case_matrix["scenario"] != "baseline"].copy()
    y_max = 1.12 * max(
        float(active["wet_width_limit_cm"].max()),
        float(active["wet_width_max_cm"].max()),
    )
    scenario_order = {
        "long_low_single": 0,
        "long_multi_node": 1,
        "long_high_single": 2,
        "long_pressure_single": 3,
    }
    active["scenario_order"] = active["scenario"].map(scenario_order)
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.5), sharey=True)
    for ax, soil in zip(axes, ("sandy_loam", "loam", "clay_loam")):
        sub = active[active["soil"] == soil].copy()
        for grid, marker in zip(("narrow_x075", "base_x100", "wide_x125"), ("o", "s", "^")):
            grid_sub = sub[sub["grid"] == grid].sort_values("scenario_order")
            ax.plot(
                grid_sub["scenario_order"],
                grid_sub["wet_width_max_cm"],
                marker=marker,
                linewidth=1.0,
                markersize=3,
                label=grid,
            )
        limit = float(sub["wet_width_limit_cm"].max())
        ax.axhline(limit, color="#6c757d", linestyle="--", linewidth=0.9)
        ax.set_title(soil)
        ax.set_xticks(list(scenario_order.values()))
        ax.set_xticklabels(["low", "multi", "high", "pressure"], rotation=35, ha="right")
        ax.set_ylim(0.0, y_max)
    axes[0].set_ylabel("Observed wet width max (cm)")
    axes[-1].legend(loc="upper right", fontsize=6)
    fig.savefig(OUT_DIR / "precision_case_widths.png", dpi=600, bbox_inches="tight")
    plt.close(fig)


def _plot_curve_widths(curve_targets, curve_matrix):
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6), sharey=True)
    grid_styles = {
        "narrow_x075": ("#4575b4", "o"),
        "base_x100": ("#74add1", "s"),
        "wide_x125": ("#f46d43", "^"),
    }
    for ax, soil in zip(axes, ("sandy_loam", "loam")):
        target_sub = curve_targets[curve_targets["soil"] == soil].copy()
        model_sub = curve_matrix[curve_matrix["soil"] == soil].copy()
        target = (
            target_sub[["elapsed_hours", "hydrus_target_width_cm"]]
            .drop_duplicates()
            .sort_values("elapsed_hours")
        )
        ax.plot(
            target["elapsed_hours"],
            target["hydrus_target_width_cm"],
            color="#222222",
            linewidth=1.1,
            label="HYDRUS target",
        )
        for grid, (color, marker) in grid_styles.items():
            target_grid = target_sub[target_sub["grid"] == grid].sort_values(
                "elapsed_hours"
            )
            model_grid = model_sub[model_sub["grid"] == grid].sort_values(
                "elapsed_hours"
            )
            ax.plot(
                target_grid["elapsed_hours"],
                target_grid["complete_segment_width_cm"],
                color=color,
                linestyle=":",
                linewidth=0.75,
                alpha=0.55,
                label=f"{grid} full segments",
            )
            ax.plot(
                target_grid["elapsed_hours"],
                target_grid["domain_clipped_target_width_cm"],
                color=color,
                linestyle="-.",
                linewidth=0.75,
                alpha=0.75,
                label=f"{grid} clipped",
            )
            ax.plot(
                target_grid["elapsed_hours"],
                target_grid["discrete_target_width_cm"],
                color=color,
                linestyle="--",
                linewidth=0.8,
                label=f"{grid} partial",
            )
            ax.scatter(
                model_grid["elapsed_hours"],
                model_grid["actual_wet_width_max_cm"],
                color=color,
                marker=marker,
                s=12,
                zorder=3,
            )
        ax.set_xscale("log")
        ax.set_title(soil)
        ax.set_xlabel("Elapsed irrigation time (h)")
        ax.set_xticks([0.03, 0.1, 0.3, 1.0, 2.0])
        ax.get_xaxis().set_major_formatter(mpl.ticker.ScalarFormatter())
    axes[0].set_ylabel("Surface wet width (cm)")
    axes[1].legend(fontsize=5, loc="lower right")
    fig.savefig(OUT_DIR / "precision_hydrus_curve_width.png", dpi=600, bbox_inches="tight")
    plt.close(fig)


def _plot_short_widths(short_matrix):
    fig, ax = plt.subplots(figsize=(5.5, 3.0))
    x = np.arange(len(short_matrix))
    ax.bar(
        x - 0.27,
        short_matrix["hydrus_target_width_cm"],
        width=0.18,
        color="#b8c0ff",
        label="HYDRUS target",
    )
    ax.bar(
        x - 0.09,
        short_matrix["domain_clipped_target_width_cm"],
        width=0.18,
        color="#ced4da",
        label="Domain-clipped target",
    )
    ax.bar(
        x + 0.09,
        short_matrix["discrete_target_width_cm"],
        width=0.18,
        color="#8ecae6",
        label="Partial-covered target",
    )
    ax.bar(
        x + 0.27,
        short_matrix["actual_wet_width_max_cm"],
        width=0.18,
        color="#219ebc",
        label="MAIZSIM actual",
    )
    labels = [
        f"{row.soil}\n{row.grid.replace('_', ' ')}"
        for row in short_matrix.itertuples()
    ]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylabel("2 h wet width (cm)")
    ax.legend(fontsize=6)
    fig.savefig(OUT_DIR / "precision_short_hydrus_width.png", dpi=600, bbox_inches="tight")
    plt.close(fig)


def _plot_delta_root_plate():
    soils = ("sandy_loam", "loam", "clay_loam")
    frames = []
    max_abs = 0.0
    for soil in soils:
        baseline = REGRESSION_ROOT / f"{soil}__base_x100__baseline"
        drip = REGRESSION_ROOT / f"{soil}__base_x100__long_high_single"
        frame = _delta_root_frame(
            _read_g03(baseline / "LOAM2D.G03"),
            _read_g03(drip / "LOAM2D.G03"),
            _read_g04(drip / "LOAM2D.G04"),
            DATE_FOR_PLATE,
        )
        frames.append((soil, drip, frame))
        max_abs = max(max_abs, float(np.abs(frame["delta_theta"]).max()))
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.8), sharex=True, sharey=True)
    last = None
    for ax, (soil, drip_dir, frame) in zip(axes, frames):
        width_limit = calibrated_drip_wet_width_max_cm(soil)
        coverage = _partial_coverage_at_target(
            Path(drip_dir) / "LOAM2D.grd",
            center_node=7,
            target_width=width_limit,
        )
        wet_interval = (
            max(coverage["target_left_cm"], coverage["surface_left_cm"]),
            min(coverage["target_right_cm"], coverage["surface_right_cm"]),
        )
        triang = mtri.Triangulation(frame["X"], frame["depth_cm"])
        last = ax.tricontourf(
            triang,
            frame["delta_theta"],
            levels=np.linspace(-max_abs, max_abs, 17),
            cmap="RdBu_r",
            vmin=-max_abs,
            vmax=max_abs,
        )
        if frame["root_density"].max() > 0.0:
            ax.tricontour(
                triang,
                frame["root_density"],
                levels=4,
            colors="#2a9d8f",
            linewidths=0.45,
            alpha=0.75,
        )
        _mark_drip(ax, drip_dir, wet_interval=wet_interval)
        ax.set_title(soil)
        ax.set_xlabel("x (cm)")
        ax.invert_yaxis()
    axes[0].set_ylabel("Depth (cm)")
    cax = fig.add_axes([0.91, 0.18, 0.018, 0.68])
    fig.colorbar(last, cax=cax, label="Delta theta")
    fig.subplots_adjust(right=0.88, wspace=0.08)
    fig.savefig(
        OUT_DIR / "precision_delta_theta_root_overlay_0601.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _plot_spatial_shape_metrics(spatial):
    soils = list(spatial["soil"])
    x = np.arange(len(soils))
    fig, axes = plt.subplots(2, 2, figsize=(5.0, 3.5))
    panels = (
        ("delta_theta_max", "Peak Delta theta"),
        ("positive_delta_area_cm2", "Positive area (cm2)"),
        ("positive_delta_max_depth_cm", "Max depth (cm)"),
        ("positive_delta_depth_width_ratio", "Depth/width"),
    )
    for ax, (column, label) in zip(axes.ravel(), panels):
        ax.bar(x, spatial[column], color="#6baed6", edgecolor="#2b6c8a", linewidth=0.4)
        ax.set_xticks(x)
        ax.set_xticklabels(soils, rotation=30, ha="right")
        ax.set_title(label)
        if column == "delta_theta_max":
            ax.scatter(
                x,
                spatial["peak_offset_from_drip_cm"],
                color=DRIP_MARKER_COLOR,
                s=10,
                zorder=3,
                label="peak offset",
            )
            ax.legend(fontsize=5, loc="upper right")
    fig.tight_layout()
    fig.savefig(
        OUT_DIR / "precision_spatial_shape_metrics.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _read_output_csv(path):
    frame = pd.read_csv(path, skipinitialspace=True)
    frame = frame.rename(columns=lambda column: str(column).strip().strip(","))
    frame = frame.dropna(how="all")
    if "Date" in frame.columns:
        frame["Date"] = frame["Date"].astype(str).str.strip()
    return frame


def _read_g03(path):
    frame = _read_output_csv(path)
    for column in ("Date_time", "X", "Y", "thNew", "Area"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["depth_cm"] = float(frame["Y"].max()) - frame["Y"]
    return frame


def _read_g04(path):
    frame = _read_output_csv(path)
    for column in ("Date_time", "X", "Y", "RDenM", "RDenY", "Area"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["depth_cm"] = float(frame["Y"].max()) - frame["Y"]
    frame["root_density"] = frame["RDenM"].clip(lower=0.0) + frame["RDenY"].clip(lower=0.0)
    return frame


def _read_g05(path):
    frame = read_g05(path)
    frame["Date"] = frame["Date"].astype(str).str.strip()
    for column in (
        "DripInput",
        "DripDemand",
        "DripPressureLoss",
        "DripHydraulicExcess",
        "Runoff",
        "DripWetNodesMax",
        "DripWetWidthMean",
        "DripWetWidthMax",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    return frame


def _nearest_date_frame(frame, target_date):
    target = pd.to_datetime(target_date)
    dates = pd.to_datetime(frame["Date"])
    nearest = frame.loc[(dates - target).abs().idxmin(), "Date"]
    return frame[frame["Date"] == nearest].copy()


def _delta_root_frame(baseline_g03, drip_g03, root_g04, date):
    baseline = _nearest_date_frame(baseline_g03, date)
    drip = _nearest_date_frame(drip_g03, date)
    roots = _nearest_date_frame(root_g04, date)
    merged = drip.merge(
        baseline[["X", "Y", "thNew"]],
        on=["X", "Y"],
        suffixes=("_drip", "_base"),
    )
    merged["delta_theta"] = merged["thNew_drip"] - merged["thNew_base"]
    merged["depth_cm"] = float(merged["Y"].max()) - merged["Y"]
    merged = merged[merged["depth_cm"] <= TOP_DEPTH_CM].copy()
    root_top = roots[roots["depth_cm"] <= TOP_DEPTH_CM].copy()
    merged = merged.merge(root_top[["X", "Y", "root_density"]], on=["X", "Y"], how="left")
    merged["root_density"] = merged["root_density"].fillna(0.0)
    return merged


def _split_case(name):
    parts = name.split("__")
    if len(parts) < 3:
        raise ValueError(f"Invalid case directory name: {name}")
    return parts[0], parts[1], "__".join(parts[2:])


def _grid_node_xy(path, node_id):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    in_nodes = False
    for line in lines:
        if "n" in line and "x" in line and "MatNum" in line:
            in_nodes = True
            continue
        if not in_nodes:
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit() and int(parts[0]) == int(node_id):
            return float(parts[1]), float(parts[2])
    raise ValueError(f"Node {node_id} not found in {path}")


def _surface_nodes(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    layout = _grid_layout(lines)
    nodes = {}
    for line in lines[layout["node_start"] : layout["node_start"] + layout["node_count"]]:
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit():
            nodes[int(parts[0])] = (float(parts[1]), float(parts[2]))
    surface = []
    for line in lines[
        layout["boundary_start"] : layout["boundary_start"] + layout["boundary_count"]
    ]:
        parts = line.split()
        if len(parts) >= 6 and parts[0].lstrip("-").isdigit():
            node = int(parts[0])
            code_w = int(parts[1])
            if abs(code_w) == 4:
                surface.append(
                    {
                        "node": node,
                        "x": nodes[node][0],
                        "width": float(parts[5]),
                    }
                )
    return sorted(surface, key=lambda item: item["x"])


def _surface_intervals(path):
    surface = _surface_nodes(path)
    intervals = []
    for index, item in enumerate(surface):
        width = float(item["width"])
        if len(surface) == 1:
            left = item["x"] - 0.5 * width
            right = item["x"] + 0.5 * width
        elif index == 0:
            right = 0.5 * (item["x"] + surface[index + 1]["x"])
            left = right - width
        elif index == len(surface) - 1:
            left = 0.5 * (surface[index - 1]["x"] + item["x"])
            right = left + width
        else:
            left = 0.5 * (surface[index - 1]["x"] + item["x"])
            right = 0.5 * (item["x"] + surface[index + 1]["x"])
        interval = dict(item)
        interval["segment_left"] = float(left)
        interval["segment_right"] = float(right)
        intervals.append(interval)
    return intervals


def _discrete_width_at_or_below_target(path, center_node, target_width):
    surface = _surface_nodes(path)
    center_index = next(
        index for index, item in enumerate(surface) if item["node"] == center_node
    )
    best = surface[center_index]["width"]
    edge_radius = max(center_index, len(surface) - center_index - 1)
    for radius in range(1, edge_radius + 1):
        left = max(0, center_index - radius)
        right = min(len(surface) - 1, center_index + radius)
        width = sum(item["width"] for item in surface[left : right + 1])
        if width <= target_width + 1.0e-6:
            best = width
    return float(best)


def _partial_coverage_at_target(path, center_node, target_width):
    surface = _surface_intervals(path)
    center = next(item for item in surface if item["node"] == center_node)
    target_left = center["x"] - 0.5 * float(target_width)
    target_right = center["x"] + 0.5 * float(target_width)
    surface_left = min(item["segment_left"] for item in surface)
    surface_right = max(item["segment_right"] for item in surface)
    domain_left = max(target_left, surface_left)
    domain_right = min(target_right, surface_right)
    domain_width = max(0.0, domain_right - domain_left)
    half_width = max(0.5 * float(target_width), 0.5 * float(center["width"]))
    for item in surface:
        cover_left = max(item["segment_left"], target_left)
        cover_right = min(item["segment_right"], target_right)
        item["covered_width"] = min(
            item["width"],
            max(0.0, cover_right - cover_left),
        )
        item["covered_fraction"] = (
            item["covered_width"] / item["width"] if item["width"] > 0.0 else 0.0
        )
        distance = abs(item["x"] - center["x"])
        item["node_weight"] = max(0.0, 1.0 - distance / half_width)
    covered = sum(item["covered_width"] for item in surface)
    weight_sum = sum(item["node_weight"] * item["covered_width"] for item in surface)
    if weight_sum > 1.0e-9:
        for item in surface:
            item["flux_fraction"] = (
                item["node_weight"] * item["covered_width"] / weight_sum
            )
    elif covered > 1.0e-9:
        for item in surface:
            item["flux_fraction"] = item["covered_width"] / covered
    else:
        for item in surface:
            item["flux_fraction"] = 0.0
    active = [item for item in surface if item["covered_width"] > 1.0e-6]
    edge_nodes = [
        item
        for item in active
        if 1.0e-6 < item["covered_fraction"] < 1.0 - 1.0e-6
    ]
    return {
        "target_left_cm": float(target_left),
        "target_right_cm": float(target_right),
        "surface_left_cm": float(surface_left),
        "surface_right_cm": float(surface_right),
        "domain_clipped_target_width_cm": float(domain_width),
        "partial_covered_width_cm": float(covered),
        "domain_clip_loss_cm": float(target_width - domain_width),
        "segment_quantization_error_cm": float(domain_width - covered),
        "partial_active_nodes": len(active),
        "partial_edge_nodes": len(edge_nodes),
        "segments": surface,
    }


def _mark_drip(ax, case_dir, wet_interval=None):
    x_coord, _ = _grid_node_xy(Path(case_dir) / "LOAM2D.grd", 7)
    if wet_interval is not None:
        left, right = wet_interval
        ax.hlines(
            -0.65,
            left,
            right,
            color=DRIP_MARKER_COLOR,
            linewidth=1.5,
            clip_on=False,
        )
        ax.plot(
            [left, right],
            [-0.65, -0.65],
            linestyle="none",
            marker="|",
            color=DRIP_MARKER_COLOR,
            markersize=5,
            clip_on=False,
        )
        ax.text(
            0.5 * (left + right),
            -2.8,
            "surface drip source",
            color=DRIP_MARKER_COLOR,
            fontsize=5,
            ha="center",
            va="top",
            clip_on=False,
        )
    ax.axvline(x_coord, color=DRIP_MARKER_COLOR, linestyle="--", linewidth=0.8)
    ax.plot(
        [x_coord],
        [-1.5],
        marker="v",
        color=DRIP_MARKER_COLOR,
        markersize=4,
        clip_on=False,
    )
    ax.text(
        x_coord + 0.5,
        2.0,
        "drip node 7",
        color=DRIP_MARKER_COLOR,
        fontsize=6,
        ha="left",
        va="top",
    )


def _span(values):
    if len(values) == 0:
        return 0.0
    return float(values.max() - values.min())


if __name__ == "__main__":
    main()
