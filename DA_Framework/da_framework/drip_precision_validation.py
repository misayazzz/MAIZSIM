from __future__ import annotations

import argparse
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
    DEFAULT_SCENARIOS,
    DEFAULT_SOILS,
    EXECUTABLE_NAME,
    DripScenario,
    RegressionCase,
    grid_surface_widths,
    prepare_regression_case,
    read_g05,
    set_water_dtmax,
    validate_case_output,
    write_drip_file,
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
EXECUTABLE_DIR = REPO / "build" / "maizsim" / "x64" / "Release"
DRIP_MARKER_COLOR = "#d62828"
TOP_DEPTH_CM = 60.0
DATE_FOR_PLATE = "06/01/2007"
CENTERED_HYDRUS_DOMAIN_SCALE = 2.2
CENTERED_HYDRUS_GRID_SUFFIX = "centered_x220"
CENTERED_HYDRUS_WIDTH_ABS_TOLERANCE_CM = 1.0
CENTERED_HYDRUS_WIDTH_REL_TOLERANCE = 0.03
CONVERGENCE_DTMX_DAYS = (0.01, 0.005, 0.0025)
CONVERGENCE_REFERENCE_DTMX_DAYS = min(CONVERGENCE_DTMX_DAYS)
CONVERGENCE_ACCEPTED_DTMX_DAYS = 0.005
GRID_REFINEMENT_FACTORS = (1, 2, 4)
GRID_REFINEMENT_SOILS = ("sandy_loam", "loam")
GRID_REFINEMENT_HOURS = 2.0
GRID_REFINEMENT_MAX_BANDWIDTH = 64
GRID_REFINEMENT_ACCEPTED_FACTOR = 2
GRID_REFINEMENT_ACTUAL_INFIL_REL_TOLERANCE = 0.02
GRID_REFINEMENT_EXCESS_ABS_TOLERANCE_MM = 0.01
GRID_REFINEMENT_WIDTH_ABS_TOLERANCE_CM = 0.5
SPATIAL_WORST_CASE_MIN_COUNT = 6
SPATIAL_WORST_CASE_CRITERIA = (
    (
        "root_storage_min",
        "positive_delta_root_storage_fraction",
        True,
        "minimum root-zone storage fraction",
    ),
    (
        "root_weighted_delta_min",
        "root_weighted_delta_theta",
        True,
        "minimum root-weighted delta theta",
    ),
    (
        "net_storage_min",
        "net_delta_storage_cm2",
        True,
        "minimum net delta-theta storage",
    ),
    (
        "positive_storage_min",
        "positive_delta_storage_cm2",
        True,
        "minimum positive delta-theta storage",
    ),
    (
        "negative_storage_max",
        "negative_delta_storage_cm2",
        False,
        "maximum negative delta-theta storage",
    ),
    (
        "depth_width_ratio_max",
        "positive_delta_depth_width_ratio",
        False,
        "maximum positive wetting depth/width ratio",
    ),
)


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


def main(arguments=None):
    args = _parse_args(arguments)
    _configure_paths(args)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHORT_ROOT.mkdir(parents=True, exist_ok=True)
    if args.figures_only:
        outputs = _plot_existing_figures()
        print(json.dumps(outputs, indent=2))
        return
    if not REGRESSION_ROOT.is_dir():
        raise SystemExit(f"Regression root does not exist: {REGRESSION_ROOT}")

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
    centered_curve_matrix = _run_centered_hydrus_curve_cases()
    centered_curve_matrix.to_csv(
        OUT_DIR / "precision_centered_hydrus_curve_model_width.csv",
        index=False,
    )
    timestep_convergence = _run_timestep_convergence_cases()
    timestep_convergence.to_csv(
        OUT_DIR / "precision_timestep_convergence.csv",
        index=False,
    )
    timestep_errors = _timestep_errors_against_reference(timestep_convergence)
    timestep_errors.to_csv(
        OUT_DIR / "precision_timestep_convergence_errors.csv",
        index=False,
    )
    grid_refinement = _run_fixed_domain_grid_refinement_cases()
    grid_refinement.to_csv(
        OUT_DIR / "precision_fixed_domain_grid_refinement.csv",
        index=False,
    )
    grid_refinement_errors = _grid_refinement_errors_against_reference(
        grid_refinement,
    )
    grid_refinement_errors.to_csv(
        OUT_DIR / "precision_fixed_domain_grid_refinement_errors.csv",
        index=False,
    )

    short_matrix = curve_matrix[curve_matrix["elapsed_hours"] == 2.0].copy()
    short_matrix.to_csv(OUT_DIR / "precision_short_hydrus_width.csv", index=False)

    spatial = _build_spatial_diagnostics()
    spatial.to_csv(OUT_DIR / "precision_spatial_delta_root.csv", index=False)
    temporal = _build_spatial_temporal_diagnostics()
    temporal.to_csv(
        OUT_DIR / "precision_spatial_temporal_delta_root.csv",
        index=False,
    )

    pressure = _build_pressure_diagnostics()
    pressure.to_csv(OUT_DIR / "precision_pressure_width_diagnostics.csv", index=False)

    checks = _build_checks(
        case_matrix,
        curve_targets,
        curve_matrix,
        centered_curve_matrix,
        timestep_errors,
        grid_refinement,
        grid_refinement_errors,
        short_matrix,
        spatial,
        temporal,
        pressure,
        surface_coverage,
    )
    checks.to_csv(OUT_DIR / "precision_validation_checks.csv", index=False)

    _plot_case_widths(case_matrix)
    _plot_curve_widths(curve_targets, curve_matrix)
    _plot_centered_curve_widths(centered_curve_matrix)
    _plot_timestep_convergence(timestep_errors)
    _plot_grid_refinement_convergence(grid_refinement_errors)
    _plot_short_widths(short_matrix)
    _plot_delta_root_plate()
    _plot_root_density_plate()
    _plot_delta_root_timeline()
    _plot_root_density_timeline()
    _plot_spatial_delta_root_matrix()
    _write_spatial_worst_cases(spatial)
    _plot_spatial_worst_case_delta_root(spatial)
    _plot_spatial_shape_metrics(spatial)
    _plot_spatial_temporal_storage(temporal)

    outputs = _write_outputs_manifest()
    print(json.dumps(outputs, indent=2))


def _write_outputs_manifest():
    outputs = {
        "workspace": {
            "regression_root": str(REGRESSION_ROOT),
            "short_root": str(SHORT_ROOT),
            "output_dir": str(OUT_DIR),
            "executable_dir": str(EXECUTABLE_DIR),
            "repo": str(REPO),
        },
        "status_policy": (
            "These outputs are internal diagnostics unless paired with archived "
            "HYDRUS or measured reference fields and the strict acceptance gate."
        ),
        "csv": [
            str(OUT_DIR / "precision_case_matrix.csv"),
            str(OUT_DIR / "precision_hydrus_curve_width.csv"),
            str(OUT_DIR / "precision_surface_partial_coverage.csv"),
            str(OUT_DIR / "precision_hydrus_curve_model_width.csv"),
            str(OUT_DIR / "precision_centered_hydrus_curve_model_width.csv"),
            str(OUT_DIR / "precision_timestep_convergence.csv"),
            str(OUT_DIR / "precision_timestep_convergence_errors.csv"),
            str(OUT_DIR / "precision_fixed_domain_grid_refinement.csv"),
            str(OUT_DIR / "precision_fixed_domain_grid_refinement_errors.csv"),
            str(OUT_DIR / "precision_short_hydrus_width.csv"),
            str(OUT_DIR / "precision_spatial_delta_root.csv"),
            str(OUT_DIR / "precision_spatial_temporal_delta_root.csv"),
            str(OUT_DIR / "precision_spatial_worst_cases.csv"),
            str(OUT_DIR / "precision_pressure_width_diagnostics.csv"),
            str(OUT_DIR / "precision_validation_checks.csv"),
        ],
        "figures": [
            str(OUT_DIR / "precision_case_widths.png"),
            str(OUT_DIR / "precision_hydrus_curve_width.png"),
            str(OUT_DIR / "precision_centered_hydrus_curve_width.png"),
            str(OUT_DIR / "precision_timestep_convergence.png"),
            str(OUT_DIR / "precision_fixed_domain_grid_refinement.png"),
            str(OUT_DIR / "precision_short_hydrus_width.png"),
            str(OUT_DIR / "precision_delta_theta_root_overlay_0601.png"),
            str(OUT_DIR / "precision_root_density_0601.png"),
            str(OUT_DIR / "precision_delta_theta_root_timeline.png"),
            str(OUT_DIR / "precision_root_density_timeline.png"),
            str(OUT_DIR / "precision_spatial_delta_root_matrix.png"),
            str(OUT_DIR / "precision_spatial_worst_case_delta_root.png"),
            str(OUT_DIR / "precision_spatial_shape_metrics.png"),
            str(OUT_DIR / "precision_spatial_temporal_storage.png"),
        ],
    }
    (OUT_DIR / "precision_validation_outputs.json").write_text(
        json.dumps(outputs, indent=2),
        encoding="utf-8",
    )
    return outputs


def _plot_existing_figures():
    case_matrix = pd.read_csv(OUT_DIR / "precision_case_matrix.csv")
    curve_targets = pd.read_csv(OUT_DIR / "precision_hydrus_curve_width.csv")
    surface_coverage = pd.read_csv(OUT_DIR / "precision_surface_partial_coverage.csv")
    curve_matrix = pd.read_csv(OUT_DIR / "precision_hydrus_curve_model_width.csv")
    centered_curve_matrix = pd.read_csv(
        OUT_DIR / "precision_centered_hydrus_curve_model_width.csv"
    )
    timestep_errors = pd.read_csv(OUT_DIR / "precision_timestep_convergence_errors.csv")
    grid_refinement = pd.read_csv(OUT_DIR / "precision_fixed_domain_grid_refinement.csv")
    grid_refinement_errors = pd.read_csv(
        OUT_DIR / "precision_fixed_domain_grid_refinement_errors.csv"
    )
    short_matrix = pd.read_csv(OUT_DIR / "precision_short_hydrus_width.csv")
    spatial = pd.read_csv(OUT_DIR / "precision_spatial_delta_root.csv")
    temporal = pd.read_csv(OUT_DIR / "precision_spatial_temporal_delta_root.csv")
    pressure = pd.read_csv(OUT_DIR / "precision_pressure_width_diagnostics.csv")

    checks = _build_checks(
        case_matrix,
        curve_targets,
        curve_matrix,
        centered_curve_matrix,
        timestep_errors,
        grid_refinement,
        grid_refinement_errors,
        short_matrix,
        spatial,
        temporal,
        pressure,
        surface_coverage,
    )
    checks.to_csv(OUT_DIR / "precision_validation_checks.csv", index=False)

    _plot_case_widths(case_matrix)
    _plot_curve_widths(curve_targets, curve_matrix)
    _plot_centered_curve_widths(centered_curve_matrix)
    _plot_timestep_convergence(timestep_errors)
    _plot_grid_refinement_convergence(grid_refinement_errors)
    _plot_short_widths(short_matrix)
    _plot_delta_root_plate()
    _plot_root_density_plate()
    _plot_delta_root_timeline()
    _plot_root_density_timeline()
    _plot_spatial_delta_root_matrix()
    _write_spatial_worst_cases(spatial)
    _plot_spatial_worst_case_delta_root(spatial)
    _plot_spatial_shape_metrics(spatial)
    _plot_spatial_temporal_storage(temporal)
    return _write_outputs_manifest()


def _parse_args(arguments):
    parser = argparse.ArgumentParser(
        description=(
            "Build MAIZSIM drip validation evidence tables and 2D water/root figures "
            "from completed regression outputs."
        )
    )
    parser.add_argument(
        "--regression-root",
        required=True,
        help="Completed drip-regression workspace containing case directories.",
    )
    parser.add_argument(
        "--short-root",
        required=True,
        help="Workspace for short HYDRUS-width curve model runs.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for CSV, PNG, and JSON evidence outputs.",
    )
    parser.add_argument(
        "--executable-dir",
        required=True,
        help="Directory containing 2dMAIZSIM.exe and Maizsim.dll for short runs.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO),
        help="MAIZSIM repository root. Defaults to the current package root.",
    )
    parser.add_argument(
        "--plate-date",
        default=DATE_FOR_PLATE,
        help="Date used for 2D delta-theta/root diagnostic plates.",
    )
    parser.add_argument(
        "--figures-only",
        action="store_true",
        help=(
            "Regenerate derived checks, PNG figures, and the outputs manifest "
            "from existing CSV and G03/G04 evidence files without rerunning "
            "MAIZSIM cases."
        ),
    )
    return parser.parse_args(arguments)


def _configure_paths(args):
    global REPO, REGRESSION_ROOT, SHORT_ROOT, OUT_DIR, EXECUTABLE_DIR, DATE_FOR_PLATE

    REPO = Path(args.repo_root).expanduser().resolve()
    REGRESSION_ROOT = Path(args.regression_root).expanduser().resolve()
    SHORT_ROOT = Path(args.short_root).expanduser().resolve()
    OUT_DIR = Path(args.output_dir).expanduser().resolve()
    EXECUTABLE_DIR = Path(args.executable_dir).expanduser().resolve()
    DATE_FOR_PLATE = str(args.plate_date)


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
        drip_input = float(g05["DripInput"].sum())
        drip_demand = float(g05["DripDemand"].sum())
        drip_pressure_loss = float(g05["DripPressureLoss"].sum())
        drip_hydraulic_excess = float(g05["DripHydraulicExcess"].sum())
        drip_actual_infil = float(g05["DripActualInfil"].sum())
        drip_source_input = float(g05["DripSourceInput"].sum())
        drip_source_loss = float(g05["DripSourceLoss"].sum())
        width_max = float(g05["DripWetWidthMax"].max())
        rows.append(
            {
                "case": case_dir.name,
                "soil": soil,
                "grid": grid,
                "scenario": scenario,
                "spread_modes": " ".join(str(mode) for mode in spread_modes),
                "active_output_rows": int(len(active)),
                "drip_input_mm": drip_input,
                "drip_demand_mm": drip_demand,
                "drip_pressure_loss_mm": drip_pressure_loss,
                "drip_hydraulic_excess_mm": drip_hydraulic_excess,
                "drip_actual_infil_mm": drip_actual_infil,
                "drip_source_input_mm": drip_source_input,
                "drip_source_loss_mm": drip_source_loss,
                "runoff_mm": float(g05["Runoff"].sum()),
                "wet_nodes_max": float(g05["DripWetNodesMax"].max()),
                "wet_width_mean_cm": float(active["DripWetWidthMean"].mean()) if not active.empty else 0.0,
                "wet_width_max_cm": width_max,
                "wet_width_limit_cm": width_limit,
                "wet_width_to_limit": width_max / width_limit if width_limit > 0.0 else 0.0,
                "demand_input_loss_residual_mm": (
                    drip_demand - drip_input - drip_pressure_loss
                ),
                "input_source_residual_mm": (
                    drip_input - drip_source_input - drip_source_loss
                ),
                "input_acceptance_residual_mm": (
                    drip_input - drip_actual_infil - drip_hydraulic_excess
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
                effective_target_width = _fortran_effective_target_width(
                    target_width,
                    widths[7],
                    width_limit,
                )
                coverage = _partial_coverage_at_target(
                    grid_path,
                    center_node=7,
                    target_width=effective_target_width,
                )
                complete_segment_width = _discrete_width_at_or_below_target(
                    grid_path,
                    center_node=7,
                    target_width=effective_target_width,
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
                        "fortran_effective_target_width_cm": (
                            effective_target_width
                        ),
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
                        "hydrus_target_not_expressible_cm": (
                            target_width
                            - coverage["partial_covered_width_cm"]
                        ),
                        "fortran_target_not_expressible_cm": (
                            effective_target_width
                            - coverage["partial_covered_width_cm"]
                        ),
                        "complete_segment_not_expressible_cm": (
                            effective_target_width - complete_segment_width
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
                widths, _ = grid_surface_widths(grid_path)
                target_width = hydrus_surface_drip_width_cm(
                    soil.name,
                    elapsed_hours,
                    width_limit,
                )
                effective_target_width = _fortran_effective_target_width(
                    target_width,
                    widths[7],
                    width_limit,
                )
                coverage = _partial_coverage_at_target(
                    grid_path,
                    center_node=7,
                    target_width=effective_target_width,
                )
                for segment in coverage["segments"]:
                    rows.append(
                        {
                            "soil": soil.name,
                            "grid": grid.name,
                            "elapsed_hours": elapsed_hours,
                            "hydrus_target_width_cm": target_width,
                            "fortran_effective_target_width_cm": (
                                effective_target_width
                            ),
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
                effective_target_width = _fortran_effective_target_width(
                    target_width,
                    widths[7],
                    width_limit,
                )
                coverage = _partial_coverage_at_target(
                    run_dir / "LOAM2D.grd",
                    center_node=7,
                    target_width=effective_target_width,
                )
                complete_segment_width = _discrete_width_at_or_below_target(
                    run_dir / "LOAM2D.grd",
                    center_node=7,
                    target_width=effective_target_width,
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
                        "fortran_effective_target_width_cm": (
                            effective_target_width
                        ),
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
                        "hydrus_target_not_expressible_cm": (
                            target_width
                            - coverage["partial_covered_width_cm"]
                        ),
                        "fortran_target_not_expressible_cm": (
                            effective_target_width
                            - coverage["partial_covered_width_cm"]
                        ),
                        "complete_segment_not_expressible_cm": (
                            effective_target_width - complete_segment_width
                        ),
                        "drip_input_mm": metric.drip_sum_mm,
                        "drip_demand_mm": metric.drip_demand_sum_mm,
                        "drip_hydraulic_excess_mm": metric.drip_hydraulic_excess_sum_mm,
                        "active_output_rows": int((g05["DripDemand"] > 0.0).sum()),
                    }
                )
    return pd.DataFrame.from_records(rows)


def _run_centered_hydrus_curve_cases():
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
            centered_grid_name = f"{grid.name}_{CENTERED_HYDRUS_GRID_SUFFIX}"
            for elapsed_hours in _model_curve_hours(soil.name):
                slug = _duration_slug(elapsed_hours)
                event_stop_hours = elapsed_hours + 0.005
                scenario = DripScenario(
                    name=f"hydrus_centered_{slug}h_single",
                    event_line=(
                        "'05/01/2007' 0.0 "
                        f"'05/01/2007' {event_stop_hours:g} 0.08 1 "
                        f"0 0 1 0 0 {width_limit:g} 1"
                    ),
                    node_line=" 7",
                )
                run_dir = (
                    SHORT_ROOT
                    / f"{soil.name}__{centered_grid_name}__{scenario.name}"
                )
                case = RegressionCase(
                    name=run_dir.name,
                    soil=soil,
                    grid=grid,
                    scenario=scenario,
                    run_dir=run_dir,
                )
                _prepare_short_case(case)
                _scale_grid_around_node(
                    run_dir / "LOAM2D.grd",
                    center_node=7,
                    x_scale=CENTERED_HYDRUS_DOMAIN_SCALE,
                )
                _run_case_if_needed(case)
                metric = validate_case_output(case)
                g05 = _read_g05(run_dir / "LOAM2D.G05")
                widths, _ = grid_surface_widths(run_dir / "LOAM2D.grd")
                target_width = hydrus_surface_drip_width_cm(
                    soil.name,
                    elapsed_hours,
                    width_limit,
                )
                effective_target_width = _fortran_effective_target_width(
                    target_width,
                    widths[7],
                    width_limit,
                )
                coverage = _partial_coverage_at_target(
                    run_dir / "LOAM2D.grd",
                    center_node=7,
                    target_width=effective_target_width,
                )
                complete_segment_width = _discrete_width_at_or_below_target(
                    run_dir / "LOAM2D.grd",
                    center_node=7,
                    target_width=effective_target_width,
                )
                rows.append(
                    {
                        "case": case.name,
                        "soil": soil.name,
                        "grid": centered_grid_name,
                        "elapsed_hours": elapsed_hours,
                        "event_stop_hours": event_stop_hours,
                        "domain_scale": CENTERED_HYDRUS_DOMAIN_SCALE,
                        "center_width_cm": widths[7],
                        "target_left_cm": coverage["target_left_cm"],
                        "target_right_cm": coverage["target_right_cm"],
                        "surface_left_cm": coverage["surface_left_cm"],
                        "surface_right_cm": coverage["surface_right_cm"],
                        "hydrus_target_width_cm": target_width,
                        "fortran_effective_target_width_cm": (
                            effective_target_width
                        ),
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
                        "hydrus_target_not_expressible_cm": (
                            target_width
                            - coverage["partial_covered_width_cm"]
                        ),
                        "fortran_target_not_expressible_cm": (
                            effective_target_width
                            - coverage["partial_covered_width_cm"]
                        ),
                        "complete_segment_not_expressible_cm": (
                            effective_target_width - complete_segment_width
                        ),
                        "drip_input_mm": metric.drip_sum_mm,
                        "drip_demand_mm": metric.drip_demand_sum_mm,
                        "drip_hydraulic_excess_mm": metric.drip_hydraulic_excess_sum_mm,
                        "active_output_rows": int((g05["DripDemand"] > 0.0).sum()),
                    }
                )
    return pd.DataFrame.from_records(rows)


def _run_timestep_convergence_cases():
    rows = []
    soils = [soil for soil in DEFAULT_SOILS if soil.name in ("sandy_loam", "loam", "clay_loam")]
    grid = next(item for item in DEFAULT_GRIDS if item.name == "base_x100")
    scenario = next(item for item in DEFAULT_SCENARIOS if item.name == "long_high_single")
    for soil in soils:
        for dtmx_days in CONVERGENCE_DTMX_DAYS:
            run_dir = (
                SHORT_ROOT
                / "timestep_convergence"
                / f"{soil.name}__{grid.name}__{scenario.name}__dt{_dt_slug(dtmx_days)}"
            )
            case = RegressionCase(
                name=run_dir.name,
                soil=soil,
                grid=grid,
                scenario=scenario,
                run_dir=run_dir,
            )
            if case.run_dir.exists():
                shutil.rmtree(case.run_dir)
            prepare_regression_case(
                REPO / BASE_RUN_RELATIVE,
                EXECUTABLE_DIR,
                case,
            )
            set_water_dtmax(case.run_dir / "WaterMovDefault.dat", dtmx_days)
            _run_case_if_needed(case)
            metric = validate_case_output(case)
            rows.append(
                {
                    "case": case.name,
                    "soil": soil.name,
                    "grid": grid.name,
                    "scenario": scenario.name,
                    "dtmx_days": dtmx_days,
                    "dtmx_minutes": dtmx_days * 24.0 * 60.0,
                    "drip_input_mm": metric.drip_sum_mm,
                    "drip_demand_mm": metric.drip_demand_sum_mm,
                    "drip_actual_infil_mm": metric.drip_actual_infil_sum_mm,
                    "drip_hydraulic_excess_mm": metric.drip_hydraulic_excess_sum_mm,
                    "drip_wet_width_max_cm": metric.drip_wet_width_max_cm,
                    "drip_wet_nodes_max": metric.drip_wet_nodes_max,
                    "input_acceptance_residual_mm": (
                        metric.input_acceptance_residual_mm
                    ),
                }
            )
    return pd.DataFrame.from_records(rows)


def _timestep_errors_against_reference(timestep_convergence):
    rows = []
    value_columns = (
        "drip_input_mm",
        "drip_actual_infil_mm",
        "drip_hydraulic_excess_mm",
        "drip_wet_width_max_cm",
    )
    for soil, soil_frame in timestep_convergence.groupby("soil"):
        reference = soil_frame[
            soil_frame["dtmx_days"] == CONVERGENCE_REFERENCE_DTMX_DAYS
        ].iloc[0]
        for _, row in soil_frame.iterrows():
            output = {
                "soil": soil,
                "grid": row["grid"],
                "scenario": row["scenario"],
                "dtmx_days": float(row["dtmx_days"]),
                "dtmx_minutes": float(row["dtmx_minutes"]),
                "reference_dtmx_days": CONVERGENCE_REFERENCE_DTMX_DAYS,
            }
            for column in value_columns:
                error = float(row[column] - reference[column])
                reference_abs = max(abs(float(reference[column])), 1.0e-9)
                output[f"{column}_error"] = error
                output[f"{column}_rel_error"] = abs(error) / reference_abs
            rows.append(output)
    return pd.DataFrame.from_records(rows)


def _run_fixed_domain_grid_refinement_cases():
    rows = []
    soils = [soil for soil in DEFAULT_SOILS if soil.name in GRID_REFINEMENT_SOILS]
    base_grid = next(item for item in DEFAULT_GRIDS if item.name == "base_x100")
    for soil in soils:
        width_limit = calibrated_drip_wet_width_max_cm(soil.name)
        target_width = hydrus_surface_drip_width_cm(
            soil.name,
            GRID_REFINEMENT_HOURS,
            width_limit,
        )
        event_stop_hours = GRID_REFINEMENT_HOURS + 0.005
        for factor in GRID_REFINEMENT_FACTORS:
            grid_name = f"fixed_centered_x{factor:02d}"
            scenario = DripScenario(
                name=f"grid_refinement_{GRID_REFINEMENT_HOURS:g}h_single",
                event_line=(
                    "'05/01/2007' 0.0 "
                    f"'05/01/2007' {event_stop_hours:g} 0.08 1 "
                    f"0 0 1 0 0 {width_limit:g} 1"
                ),
                node_line=" 7",
            )
            run_dir = (
                SHORT_ROOT
                / "fixed_domain_grid_refinement"
                / f"{soil.name}__{grid_name}__{scenario.name}"
            )
            case = RegressionCase(
                name=run_dir.name,
                soil=soil,
                grid=base_grid,
                scenario=scenario,
                run_dir=run_dir,
            )
            _prepare_short_case(case)
            refine_info = _refine_grid_fixed_domain(
                run_dir / "LOAM2D.grd",
                factor,
                center_node=7,
                x_scale=CENTERED_HYDRUS_DOMAIN_SCALE,
            )
            scenario = DripScenario(
                name=scenario.name,
                event_line=(
                    "'05/01/2007' 0.0 "
                    f"'05/01/2007' {event_stop_hours:g} 0.08 1 "
                    f"0 0 1 0 0 {width_limit:g} 1 "
                    f"{refine_info['reference_source_width_cm']:g}"
                ),
                node_line=f" {refine_info['drip_node']}",
            )
            case = RegressionCase(
                name=run_dir.name,
                soil=soil,
                grid=base_grid,
                scenario=scenario,
                run_dir=run_dir,
            )
            write_drip_file(run_dir / "LOAM2D.drp", scenario, soil)
            _run_case_if_needed(case)
            metric = validate_case_output(case)
            g05 = _read_g05(run_dir / "LOAM2D.G05")
            widths, grid_width = grid_surface_widths(run_dir / "LOAM2D.grd")
            center_width = widths[refine_info["drip_node"]]
            effective_target_width = _fortran_effective_target_width(
                target_width,
                center_width,
                width_limit,
            )
            coverage = _partial_coverage_at_target(
                run_dir / "LOAM2D.grd",
                center_node=refine_info["drip_node"],
                target_width=effective_target_width,
            )
            rows.append(
                {
                    "case": case.name,
                    "soil": soil.name,
                    "grid": grid_name,
                    "scenario": scenario.name,
                    "elapsed_hours": GRID_REFINEMENT_HOURS,
                    "event_stop_hours": event_stop_hours,
                    "refinement_factor": factor,
                    "domain_scale": CENTERED_HYDRUS_DOMAIN_SCALE,
                    "x_node_count": refine_info["x_node_count"],
                    "y_node_count": refine_info["y_node_count"],
                    "node_count": refine_info["node_count"],
                    "element_count": refine_info["element_count"],
                    "boundary_count": refine_info["boundary_count"],
                    "solver_bandwidth": refine_info["solver_bandwidth"],
                    "drip_node": refine_info["drip_node"],
                    "drip_node_x_cm": refine_info["drip_node_x_cm"],
                    "reference_source_width_cm": (
                        refine_info["reference_source_width_cm"]
                    ),
                    "domain_left_cm": refine_info["domain_left_cm"],
                    "domain_right_cm": refine_info["domain_right_cm"],
                    "grid_width_cm": grid_width,
                    "center_width_cm": center_width,
                    "surface_width_min_cm": min(widths.values()),
                    "surface_width_max_cm": max(widths.values()),
                    "hydrus_target_width_cm": target_width,
                    "fortran_effective_target_width_cm": (
                        effective_target_width
                    ),
                    "domain_clipped_target_width_cm": coverage[
                        "domain_clipped_target_width_cm"
                    ],
                    "partial_covered_width_cm": coverage[
                        "partial_covered_width_cm"
                    ],
                    "domain_clip_loss_cm": coverage["domain_clip_loss_cm"],
                    "actual_wet_width_max_cm": metric.drip_wet_width_max_cm,
                    "actual_wet_nodes_max": metric.drip_wet_nodes_max,
                    "width_error_vs_discrete_cm": (
                        metric.drip_wet_width_max_cm
                        - coverage["partial_covered_width_cm"]
                    ),
                    "drip_input_mm": metric.drip_sum_mm,
                    "drip_demand_mm": metric.drip_demand_sum_mm,
                    "drip_actual_infil_mm": metric.drip_actual_infil_sum_mm,
                    "drip_hydraulic_excess_mm": (
                        metric.drip_hydraulic_excess_sum_mm
                    ),
                    "input_acceptance_residual_mm": (
                        metric.input_acceptance_residual_mm
                    ),
                    "active_output_rows": int((g05["DripDemand"] > 0.0).sum()),
                }
            )
    return pd.DataFrame.from_records(rows)


def _grid_refinement_errors_against_reference(grid_refinement):
    rows = []
    value_columns = (
        "drip_input_mm",
        "drip_actual_infil_mm",
        "drip_hydraulic_excess_mm",
        "actual_wet_width_max_cm",
        "partial_covered_width_cm",
    )
    reference_factor = max(GRID_REFINEMENT_FACTORS)
    for soil, soil_frame in grid_refinement.groupby("soil"):
        reference = soil_frame[
            soil_frame["refinement_factor"] == reference_factor
        ].iloc[0]
        for _, row in soil_frame.iterrows():
            output = {
                "soil": soil,
                "grid": row["grid"],
                "scenario": row["scenario"],
                "refinement_factor": int(row["refinement_factor"]),
                "reference_refinement_factor": reference_factor,
                "x_node_count": int(row["x_node_count"]),
                "node_count": int(row["node_count"]),
                "solver_bandwidth": int(row["solver_bandwidth"]),
            }
            for column in value_columns:
                error = float(row[column] - reference[column])
                reference_abs = max(abs(float(reference[column])), 1.0e-9)
                output[f"{column}_error"] = error
                output[f"{column}_rel_error"] = abs(error) / reference_abs
            rows.append(output)
    return pd.DataFrame.from_records(rows)


def _prepare_short_case(case):
    if case.run_dir.exists():
        shutil.rmtree(case.run_dir)
    prepare_regression_case(
        REPO / BASE_RUN_RELATIVE,
        EXECUTABLE_DIR,
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


def _dt_slug(value):
    return f"{value:g}".replace(".", "p")


def _build_spatial_diagnostics():
    rows = []
    for drip in sorted(REGRESSION_ROOT.iterdir()):
        if not drip.is_dir() or "__" not in drip.name:
            continue
        soil, grid, scenario = _split_case(drip.name)
        if scenario == "baseline":
            continue
        baseline = REGRESSION_ROOT / f"{soil}__{grid}__baseline"
        rows.append(_spatial_metrics_for_case(soil, grid, scenario, baseline, drip))
    return pd.DataFrame.from_records(rows)


def _spatial_metrics_for_case(soil, grid, scenario, baseline, drip):
    baseline_g03 = _read_g03(baseline / "LOAM2D.G03")
    drip_g03 = _read_g03(drip / "LOAM2D.G03")
    root_g04 = _read_g04(drip / "LOAM2D.G04")
    node_x, _ = _grid_node_xy(drip / "LOAM2D.grd", 7)
    return _spatial_metrics_from_frames(
        soil,
        grid,
        scenario,
        drip.name,
        node_x,
        baseline_g03,
        drip_g03,
        root_g04,
        DATE_FOR_PLATE,
    )


def _build_spatial_temporal_diagnostics():
    rows = []
    for drip in sorted(REGRESSION_ROOT.iterdir()):
        if not drip.is_dir() or "__" not in drip.name:
            continue
        soil, grid, scenario = _split_case(drip.name)
        if scenario == "baseline":
            continue
        baseline = REGRESSION_ROOT / f"{soil}__{grid}__baseline"
        baseline_g03 = _read_g03(baseline / "LOAM2D.G03")
        drip_g03 = _read_g03(drip / "LOAM2D.G03")
        root_g04 = _read_g04(drip / "LOAM2D.G04")
        node_x, _ = _grid_node_xy(drip / "LOAM2D.grd", 7)
        for date in _common_spatial_dates(baseline_g03, drip_g03, root_g04):
            rows.append(
                _spatial_metrics_from_frames(
                    soil,
                    grid,
                    scenario,
                    drip.name,
                    node_x,
                    baseline_g03,
                    drip_g03,
                    root_g04,
                    date,
                )
            )
    return pd.DataFrame.from_records(rows)


def _common_spatial_dates(*frames):
    common = None
    for frame in frames:
        dates = set(frame["Date"].astype(str).str.strip())
        common = dates if common is None else common & dates
    return tuple(sorted(common or (), key=lambda value: pd.to_datetime(value)))


def _spatial_metrics_from_frames(
    soil,
    grid,
    scenario,
    case,
    node_x,
    baseline_g03,
    drip_g03,
    root_g04,
    date,
):
    frame = _delta_root_frame(baseline_g03, drip_g03, root_g04, date)
    positive = frame["delta_theta"] > 0.005
    root_positive = frame["root_density"] > 0.0
    peak_index = int(frame["delta_theta"].idxmax())
    positive_frame = frame.loc[positive].copy()
    positive_area = float(positive_frame["Area"].sum()) if positive.any() else 0.0
    delta_storage = frame["delta_theta"] * frame["Area"]
    positive_delta_storage = float(delta_storage.clip(lower=0.0).sum())
    negative_delta_storage = float((-delta_storage.clip(upper=0.0)).sum())
    net_delta_storage = float(delta_storage.sum())
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
    root_area = float(frame.loc[root_positive, "Area"].sum()) if root_positive.any() else 0.0
    positive_root_storage = float(
        delta_storage.where(root_positive, 0.0).clip(lower=0.0).sum()
    )
    peak_x = float(frame.loc[peak_index, "X"])
    return {
        "case": case,
        "soil": soil,
        "grid": grid,
        "scenario": scenario,
        "date": date,
        "drip_node_x_cm": node_x,
        "delta_theta_max": float(frame.loc[peak_index, "delta_theta"]),
        "peak_delta_x_cm": peak_x,
        "peak_delta_depth_cm": float(frame.loc[peak_index, "depth_cm"]),
        "peak_offset_from_drip_cm": abs(peak_x - node_x),
        "positive_delta_nodes_top60": int(positive.sum()),
        "positive_delta_area_cm2": positive_area,
        "positive_delta_storage_cm2": positive_delta_storage,
        "negative_delta_storage_cm2": negative_delta_storage,
        "net_delta_storage_cm2": net_delta_storage,
        "positive_delta_x_span_cm": positive_x_span,
        "positive_delta_max_depth_cm": positive_max_depth,
        "positive_delta_depth_width_ratio": positive_max_depth / positive_x_span
        if positive_x_span > 0.0
        else 0.0,
        "positive_delta_centroid_x_cm": centroid_x,
        "positive_delta_centroid_depth_cm": centroid_depth,
        "positive_delta_root_overlap_fraction": float(
            (positive & root_positive).sum() / positive.sum()
        )
        if positive.any()
        else 0.0,
        "positive_delta_root_area_fraction": positive_root_area / positive_area
        if positive_area > 0.0
        else 0.0,
        "root_area_cm2": root_area,
        "positive_delta_root_storage_cm2": positive_root_storage,
        "positive_delta_root_storage_fraction": (
            positive_root_storage / positive_delta_storage
            if positive_delta_storage > 0.0
            else 0.0
        ),
        "root_weighted_delta_theta": root_weighted_delta,
    }


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
    centered_curve_matrix,
    timestep_errors,
    grid_refinement,
    grid_refinement_errors,
    short_matrix,
    spatial,
    temporal,
    pressure,
    surface_coverage,
):
    active = case_matrix[case_matrix["scenario"] != "baseline"].copy()
    curve_error_abs_max = float(curve_matrix["width_error_vs_discrete_cm"].abs().max())
    centered_curve_error_abs_max = float(
        centered_curve_matrix["width_error_vs_discrete_cm"].abs().max()
    )
    centered_curve_rel_error = (
        centered_curve_matrix["width_error_vs_discrete_cm"].abs()
        / centered_curve_matrix["hydrus_target_width_cm"].clip(lower=1.0e-9)
    )
    centered_curve_rel_error_abs_max = float(centered_curve_rel_error.max())
    centered_curve_width_pass = (
        centered_curve_error_abs_max <= CENTERED_HYDRUS_WIDTH_ABS_TOLERANCE_CM
        and centered_curve_rel_error_abs_max <= CENTERED_HYDRUS_WIDTH_REL_TOLERANCE
    )
    centered_domain_clip_abs_max = float(
        centered_curve_matrix["domain_clip_loss_cm"].abs().max()
    )
    centered_target_unexpressed_abs_max = float(
        centered_curve_matrix["fortran_target_not_expressible_cm"].abs().max()
    )
    accepted_timestep = timestep_errors[
        timestep_errors["dtmx_days"] == CONVERGENCE_ACCEPTED_DTMX_DAYS
    ]
    accepted_timestep_actual_rel_error_max = float(
        accepted_timestep["drip_actual_infil_mm_rel_error"].max()
    )
    accepted_timestep_excess_rel_error_max = float(
        accepted_timestep["drip_hydraulic_excess_mm_rel_error"].max()
    )
    accepted_timestep_width_abs_error_max = float(
        accepted_timestep["drip_wet_width_max_cm_error"].abs().max()
    )
    accepted_grid_refinement = grid_refinement_errors[
        grid_refinement_errors["refinement_factor"] == GRID_REFINEMENT_ACCEPTED_FACTOR
    ]
    grid_refinement_actual_rel_error_max = float(
        accepted_grid_refinement["drip_actual_infil_mm_rel_error"].max()
    )
    grid_refinement_excess_rel_error_max = float(
        accepted_grid_refinement["drip_hydraulic_excess_mm_rel_error"].max()
    )
    grid_refinement_excess_abs_error_max = float(
        accepted_grid_refinement["drip_hydraulic_excess_mm_error"].abs().max()
    )
    grid_refinement_width_abs_error_max = float(
        accepted_grid_refinement["actual_wet_width_max_cm_error"].abs().max()
    )
    grid_refinement_width_discrete_error_abs_max = float(
        grid_refinement["width_error_vs_discrete_cm"].abs().max()
    )
    grid_refinement_factor_count = float(
        grid_refinement.groupby("soil")["refinement_factor"].nunique().min()
    )
    grid_refinement_bandwidth_max = float(grid_refinement["solver_bandwidth"].max())
    curve_target_unexpressed_abs_max = float(
        curve_targets["fortran_target_not_expressible_cm"].abs().max()
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
    source_active = active[
        (active["drip_source_input_mm"].abs() > 1.0e-9)
        | (active["drip_source_loss_mm"].abs() > 1.0e-9)
    ]
    source_residual_abs_max = (
        float(source_active["input_source_residual_mm"].abs().max())
        if not source_active.empty
        else 0.0
    )
    boundary_active = active[
        (active["drip_source_input_mm"].abs() <= 1.0e-9)
        & (active["drip_source_loss_mm"].abs() <= 1.0e-9)
    ]
    boundary_residual_abs_max = (
        float(boundary_active["input_acceptance_residual_mm"].abs().max())
        if not boundary_active.empty
        else 0.0
    )
    boundary_residual_tolerance = _g05_sum_roundoff_tolerance(boundary_active)
    direct_bypass_cases = _direct_source_bypass_cases()
    temporal_case_count = int(temporal["case"].astype(str).nunique())
    temporal_date_count_min = (
        int(temporal.groupby("case")["date"].nunique().min())
        if not temporal.empty
        else 0
    )
    temporal_storage_by_case = temporal.groupby("case")[
        "positive_delta_storage_cm2"
    ].max()
    temporal_positive_storage_cases = int((temporal_storage_by_case > 0.1).sum())
    temporal_positive = temporal[temporal["positive_delta_storage_cm2"] > 0.1]
    temporal_root_active = temporal[temporal["root_area_cm2"] > 0.0]
    temporal_positive_root_active = temporal[
        (temporal["positive_delta_storage_cm2"] > 0.1)
        & (temporal["root_area_cm2"] > 0.0)
    ]
    worst_cases = _select_spatial_worst_cases(spatial)
    worst_case_target_count = min(SPATIAL_WORST_CASE_MIN_COUNT, len(spatial))
    temporal_root_active_case_count = int(
        temporal_root_active["case"].astype(str).nunique()
    )
    temporal_root_storage_fraction_min = (
        float(
            temporal_positive_root_active[
                "positive_delta_root_storage_fraction"
            ].min()
        )
        if not temporal_positive_root_active.empty
        else 0.0
    )
    rows = [
        {
            "check": "case_count",
            "value": float(len(case_matrix)),
            "status": "pass" if len(case_matrix) == 45 else "fail",
            "detail": "Expected 45 cases for 3 soils x 3 grids x 5 scenarios.",
        },
        {
            "check": "spatial_active_case_count",
            "value": float(len(spatial)),
            "status": "pass" if len(spatial) == len(active) else "fail",
            "detail": "2D delta-theta/root diagnostics should cover every active regression case.",
        },
        {
            "check": "demand_input_pressure_residual_abs_max_mm",
            "value": float(active["demand_input_loss_residual_mm"].abs().max()),
            "status": "pass" if active["demand_input_loss_residual_mm"].abs().max() < 0.01 else "fail",
            "detail": "Checks DripDemand = DripInput + DripPressureLoss.",
        },
        {
            "check": "source_input_loss_residual_abs_max_mm",
            "value": source_residual_abs_max,
            "status": "pass" if source_residual_abs_max < 0.01 else "fail",
            "detail": "Checks DripInput = DripSourceInput + DripSourceLoss for direct-source accounting.",
        },
        {
            "check": "boundary_acceptance_residual_abs_max_mm",
            "value": boundary_residual_abs_max,
            "status": "pass"
            if boundary_residual_abs_max < boundary_residual_tolerance
            else "fail",
            "detail": (
                "Checks DripInput = DripActualInfil + DripHydraulicExcess "
                "for boundary-flow accounting; tolerance includes G05 daily "
                f"0.001 mm reporting roundoff ({boundary_residual_tolerance:.3g} mm)."
            ),
        },
        {
            "check": "direct_source_bypass_case_count",
            "value": float(len(direct_bypass_cases)),
            "status": "pass" if not direct_bypass_cases else "fail",
            "detail": (
                "Journal-readiness precision evidence must not rely on "
                "DripMode=3 with DripSpreadMode=1 because that path bypasses "
                f"WaterMover; cases: {', '.join(direct_bypass_cases)}."
                if direct_bypass_cases
                else (
                    "Journal-readiness precision evidence must not rely on "
                    "DripMode=3 with DripSpreadMode=1 because that path bypasses "
                    "WaterMover."
                )
            ),
        },
        {
            "check": "non_pressure_pressure_loss_cases",
            "value": float(
                (
                    (~active["scenario"].astype(str).str.contains("pressure"))
                    & (active["drip_pressure_loss_mm"].abs() > 0.01)
                ).sum()
            ),
            "status": "pass"
            if (
                (~active["scenario"].astype(str).str.contains("pressure"))
                & (active["drip_pressure_loss_mm"].abs() > 0.01)
            ).sum()
            == 0
            else "fail",
            "detail": "Non-pressure drip scenarios should not report pressure-loss water.",
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
            "check": "centered_hydrus_curve_width_error_abs_max_cm",
            "value": centered_curve_error_abs_max,
            "status": "pass" if centered_curve_width_pass else "fail",
            "detail": (
                "Centered wide-domain HYDRUS curve cases should match the "
                "partial-covered target within 1 cm and 3% model "
                f"output-cadence tolerance; relative max "
                f"{centered_curve_rel_error_abs_max:.3g}."
            ),
        },
        {
            "check": "centered_hydrus_curve_width_error_rel_abs_max",
            "value": centered_curve_rel_error_abs_max,
            "status": "pass"
            if centered_curve_rel_error_abs_max <= CENTERED_HYDRUS_WIDTH_REL_TOLERANCE
            else "fail",
            "detail": "Relative centered HYDRUS width error should remain below 3%.",
        },
        {
            "check": "centered_hydrus_domain_clip_loss_abs_max_cm",
            "value": centered_domain_clip_abs_max,
            "status": "pass" if centered_domain_clip_abs_max < 0.01 else "fail",
            "detail": (
                "Centered wide-domain cases should express HYDRUS target widths "
                "without clipping at the modeled surface edge."
            ),
        },
        {
            "check": "centered_fortran_target_unexpressed_abs_max_cm",
            "value": centered_target_unexpressed_abs_max,
            "status": "pass" if centered_target_unexpressed_abs_max < 0.01 else "fail",
            "detail": (
                "Centered wide-domain cases should make the Fortran effective "
                "target width exactly expressible by partial boundary coverage."
            ),
        },
        {
            "check": "accepted_timestep_actual_infil_rel_error_max",
            "value": accepted_timestep_actual_rel_error_max,
            "status": "pass"
            if accepted_timestep_actual_rel_error_max <= 0.02
            else "fail",
            "detail": (
                "DtMx=0.005 d should keep actual drip infiltration within 2% "
                "of the DtMx=0.0025 d reference for the convergence cases."
            ),
        },
        {
            "check": "accepted_timestep_hydraulic_excess_rel_error_max",
            "value": accepted_timestep_excess_rel_error_max,
            "status": "pass"
            if accepted_timestep_excess_rel_error_max <= 0.02
            else "fail",
            "detail": (
                "DtMx=0.005 d should keep hydraulic-excess accounting within "
                "2% of the DtMx=0.0025 d reference."
            ),
        },
        {
            "check": "accepted_timestep_wet_width_abs_error_max_cm",
            "value": accepted_timestep_width_abs_error_max,
            "status": "pass"
            if accepted_timestep_width_abs_error_max <= 0.5
            else "fail",
            "detail": (
                "DtMx=0.005 d should keep maximum surface wet width within "
                "0.5 cm of the DtMx=0.0025 d reference."
            ),
        },
        {
            "check": "fixed_domain_grid_refinement_factor_count",
            "value": grid_refinement_factor_count,
            "status": "pass"
            if grid_refinement_factor_count == len(GRID_REFINEMENT_FACTORS)
            else "fail",
            "detail": (
                "Fixed-domain centered grid-refinement evidence should include "
                "all configured refinement factors for every HYDRUS soil."
            ),
        },
        {
            "check": "fixed_domain_grid_refinement_bandwidth_max",
            "value": grid_refinement_bandwidth_max,
            "status": "pass"
            if grid_refinement_bandwidth_max <= GRID_REFINEMENT_MAX_BANDWIDTH
            else "fail",
            "detail": (
                "The refined structured grids must fit the compiled MAIZSIM "
                f"solver band limit MBandD={GRID_REFINEMENT_MAX_BANDWIDTH}."
            ),
        },
        {
            "check": "fixed_domain_width_error_vs_discrete_abs_max_cm",
            "value": grid_refinement_width_discrete_error_abs_max,
            "status": "pass"
            if grid_refinement_width_discrete_error_abs_max
            <= GRID_REFINEMENT_WIDTH_ABS_TOLERANCE_CM
            else "fail",
            "detail": (
                "Fixed-domain grid-refinement cases should reproduce the "
                "partial-boundary discrete target within 0.5 cm."
            ),
        },
        {
            "check": "fixed_domain_factor2_actual_infil_rel_error_max",
            "value": grid_refinement_actual_rel_error_max,
            "status": "pass"
            if grid_refinement_actual_rel_error_max
            <= GRID_REFINEMENT_ACTUAL_INFIL_REL_TOLERANCE
            else "fail",
            "detail": (
                "The 2x fixed-domain grid should keep actual drip infiltration "
                "within 2% of the 4x fixed-domain reference."
            ),
        },
        {
            "check": "fixed_domain_factor2_hydraulic_excess_abs_error_max_mm",
            "value": grid_refinement_excess_abs_error_max,
            "status": "pass"
            if grid_refinement_excess_abs_error_max
            <= GRID_REFINEMENT_EXCESS_ABS_TOLERANCE_MM
            else "fail",
            "detail": (
                "The 2x fixed-domain grid should keep hydraulic-excess "
                "accounting within 0.01 mm of the 4x fixed-domain reference; "
                "an absolute gate is used because hydraulic excess can be "
                f"near zero (relative max {grid_refinement_excess_rel_error_max:.3g})."
            ),
        },
        {
            "check": "fixed_domain_factor2_wet_width_abs_error_max_cm",
            "value": grid_refinement_width_abs_error_max,
            "status": "pass"
            if grid_refinement_width_abs_error_max
            <= GRID_REFINEMENT_WIDTH_ABS_TOLERANCE_CM
            else "fail",
            "detail": (
                "The 2x fixed-domain grid should keep maximum wetted surface "
                "width within 0.5 cm of the 4x fixed-domain reference."
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
            "check": "fortran_target_unexpressed_abs_max_cm",
            "value": curve_target_unexpressed_abs_max,
            "status": "diagnostic",
            "detail": (
                "Fortran effective target width not expressible after partial "
                "boundary coverage, usually because the target interval reaches "
                "the modeled surface edge; centered wide-domain cases are the "
                "strict acceptance evidence."
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
            "detail": "Every active 2D case should show local positive wetting.",
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
            "detail": "Positive delta-theta areas should be non-empty in active 2D cases.",
        },
        {
            "check": "spatial_positive_storage_records",
            "value": float((spatial["positive_delta_storage_cm2"] > 0.1).sum()),
            "status": "pass"
            if (spatial["positive_delta_storage_cm2"] > 0.1).all()
            else "fail",
            "detail": (
                "Area-integrated positive delta-theta storage should be non-trivial "
                "in every active 2D case."
            ),
        },
        {
            "check": "spatial_root_storage_fraction_records",
            "value": float(
                (spatial["positive_delta_root_storage_fraction"] >= 0.95).sum()
            ),
            "status": "pass"
            if (spatial["positive_delta_root_storage_fraction"] >= 0.95).all()
            else "review",
            "detail": (
                "Positive area-integrated wetting should overlap the simulated "
                "root zone for the validation plate."
            ),
        },
        {
            "check": "spatial_root_weighted_delta_records",
            "value": float((spatial["root_weighted_delta_theta"] > 0.0).sum()),
            "status": "pass"
            if (spatial["root_weighted_delta_theta"] > 0.0).mean() >= 0.90
            else "review",
            "detail": (
                "Most active cases should have positive root-zone weighted delta theta; "
                "low-flow cases can be offset by simulated root uptake."
            ),
        },
        {
            "check": "spatial_root_weighted_delta_nonpositive_cases",
            "value": float((spatial["root_weighted_delta_theta"] <= 0.0).sum()),
            "status": "diagnostic",
            "detail": "Counts active cases where root uptake offsets local drip wetting on the plate date.",
        },
        {
            "check": "spatial_net_storage_negative_cases",
            "value": float((spatial["net_delta_storage_cm2"] < 0.0).sum()),
            "status": "diagnostic",
            "detail": (
                "Counts active cases where whole-profile net storage is negative "
                "after accounting for redistribution and uptake on the plate date."
            ),
        },
        {
            "check": "spatial_worst_case_count",
            "value": float(len(worst_cases)),
            "status": "pass"
            if len(worst_cases) >= worst_case_target_count
            else "fail",
            "detail": (
                "Worst-case 2D plate selection should expose at least six "
                "distinct weak internal cases when the matrix is large enough, "
                "rather than relying only on representative panels."
            ),
        },
        {
            "check": "spatial_temporal_case_count",
            "value": float(temporal_case_count),
            "status": "pass" if temporal_case_count == len(active) else "fail",
            "detail": "Temporal 2D diagnostics should cover every active drip case.",
        },
        {
            "check": "spatial_temporal_date_count_min",
            "value": float(temporal_date_count_min),
            "status": "pass" if temporal_date_count_min >= 7 else "fail",
            "detail": (
                "Temporal 2D diagnostics should include at least weekly-scale "
                "date coverage per case."
            ),
        },
        {
            "check": "spatial_temporal_positive_storage_cases",
            "value": float(temporal_positive_storage_cases),
            "status": "pass"
            if temporal_positive_storage_cases == temporal_case_count
            else "fail",
            "detail": (
                "Every active case should show non-trivial positive storage at "
                "some output date."
            ),
        },
        {
            "check": "spatial_temporal_root_active_case_count",
            "value": float(temporal_root_active_case_count),
            "status": "pass"
            if temporal_root_active_case_count == temporal_case_count
            else "review",
            "detail": (
                "Temporal root-density diagnostics should include at least one "
                "root-active date for every active drip case."
            ),
        },
        {
            "check": "spatial_temporal_root_storage_fraction_min",
            "value": temporal_root_storage_fraction_min,
            "status": "pass"
            if temporal_root_storage_fraction_min >= 0.95
            else "review",
            "detail": (
                "Across positive-storage temporal records, area-integrated "
                "wetting should overlap the simulated root zone."
            ),
        },
    ]
    return pd.DataFrame.from_records(rows)


def _direct_source_bypass_cases():
    cases = []
    for case_dir in sorted(REGRESSION_ROOT.iterdir()):
        if not case_dir.is_dir() or "__" not in case_dir.name:
            continue
        soil, grid, scenario = _split_case(case_dir.name)
        if scenario == "baseline":
            continue
        drip_path = case_dir / "LOAM2D.drp"
        if not drip_path.is_file():
            continue
        schedule = parse_drip_file(drip_path)
        for event in schedule.events:
            if event.pressure_mode == 3 and event.spread_mode == 1:
                cases.append(f"{soil}__{grid}__{scenario}")
                break
    return cases


def _g05_sum_roundoff_tolerance(frame):
    """Return tolerance for equations summed from G05 0.001 mm daily columns."""
    if frame.empty or "active_output_rows" not in frame:
        return 0.01
    return max(0.01, 0.001 * float(frame["active_output_rows"].max()))


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


def _plot_centered_curve_widths(centered_curve_matrix):
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6), sharey=True)
    grid_styles = {
        "narrow_x075": ("#4575b4", "o"),
        "base_x100": ("#74add1", "s"),
        "wide_x125": ("#f46d43", "^"),
    }
    for ax, soil in zip(axes, ("sandy_loam", "loam")):
        model_sub = centered_curve_matrix[
            centered_curve_matrix["soil"] == soil
        ].copy()
        target = (
            model_sub[["elapsed_hours", "hydrus_target_width_cm"]]
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
            grid_name = f"{grid}_{CENTERED_HYDRUS_GRID_SUFFIX}"
            model_grid = model_sub[model_sub["grid"] == grid_name].sort_values(
                "elapsed_hours"
            )
            ax.plot(
                model_grid["elapsed_hours"],
                model_grid["discrete_target_width_cm"],
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
        ax.set_title(soil)
        ax.set_xlabel("Elapsed irrigation time (h)")
        ax.set_xticks([0.5, 1.0, 2.0])
    axes[0].set_ylabel("Surface wet width (cm)")
    axes[1].legend(fontsize=5, loc="lower right")
    fig.savefig(
        OUT_DIR / "precision_centered_hydrus_curve_width.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _plot_timestep_convergence(timestep_errors):
    frame = timestep_errors.copy()
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.4))
    panels = (
        ("drip_actual_infil_mm_rel_error", "Actual infiltration rel. error"),
        ("drip_hydraulic_excess_mm_rel_error", "Hydraulic excess rel. error"),
        ("drip_wet_width_max_cm_error", "Wet width error (cm)"),
    )
    colors = {"clay_loam": "#8ecae6", "loam": "#90be6d", "sandy_loam": "#f9c74f"}
    for ax, (column, label) in zip(axes, panels):
        for soil, soil_frame in frame.groupby("soil"):
            soil_frame = soil_frame.sort_values("dtmx_days")
            ax.plot(
                soil_frame["dtmx_minutes"],
                soil_frame[column].abs(),
                marker="o",
                markersize=3,
                linewidth=1.0,
                color=colors.get(soil, "#6c757d"),
                label=soil,
            )
        ticks = [value * 24.0 * 60.0 for value in CONVERGENCE_DTMX_DAYS]
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{value:g}" for value in ticks])
        ax.set_xlim(max(ticks) * 1.08, min(ticks) * 0.92)
        ax.set_xlabel("DtMx (min)")
        ax.set_title(label)
    axes[0].set_ylabel("Absolute error vs 0.0025 d")
    axes[0].legend(fontsize=5)
    fig.savefig(
        OUT_DIR / "precision_timestep_convergence.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _plot_grid_refinement_convergence(grid_refinement_errors):
    frame = grid_refinement_errors.copy()
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.4))
    panels = (
        ("drip_actual_infil_mm_rel_error", "Actual infiltration rel. error"),
        ("drip_hydraulic_excess_mm_error", "Hydraulic excess error (mm)"),
        ("actual_wet_width_max_cm_error", "Wet width error (cm)"),
    )
    colors = {"loam": "#90be6d", "sandy_loam": "#f9c74f"}
    for ax, (column, label) in zip(axes, panels):
        for soil, soil_frame in frame.groupby("soil"):
            soil_frame = soil_frame.sort_values("refinement_factor")
            ax.plot(
                soil_frame["refinement_factor"],
                soil_frame[column].abs(),
                marker="o",
                markersize=3,
                linewidth=1.0,
                color=colors.get(soil, "#6c757d"),
                label=soil,
            )
        ax.set_xticks(list(GRID_REFINEMENT_FACTORS))
        ax.set_xlabel("Horizontal refinement factor")
        ax.set_title(label)
    axes[0].set_ylabel("Absolute error vs 4x fixed-domain grid")
    axes[0].legend(fontsize=5)
    fig.savefig(
        OUT_DIR / "precision_fixed_domain_grid_refinement.png",
        dpi=600,
        bbox_inches="tight",
    )
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


def _plot_root_density_plate():
    soils = ("sandy_loam", "loam", "clay_loam")
    frames = []
    max_root = 0.0
    for soil in soils:
        drip = REGRESSION_ROOT / f"{soil}__base_x100__long_high_single"
        frame = _delta_root_frame(
            _read_g03(REGRESSION_ROOT / f"{soil}__base_x100__baseline" / "LOAM2D.G03"),
            _read_g03(drip / "LOAM2D.G03"),
            _read_g04(drip / "LOAM2D.G04"),
            DATE_FOR_PLATE,
        )
        frames.append((soil, drip, frame))
        max_root = max(max_root, float(frame["root_density"].max()))
    max_root = max(max_root, 1.0e-9)
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
            frame["root_density"],
            levels=np.linspace(0.0, max_root, 15),
            cmap="YlGn",
            vmin=0.0,
            vmax=max_root,
        )
        _mark_drip(ax, drip_dir, wet_interval=wet_interval)
        ax.set_title(soil)
        ax.set_xlabel("x (cm)")
        ax.invert_yaxis()
    axes[0].set_ylabel("Depth (cm)")
    cax = fig.add_axes([0.91, 0.18, 0.018, 0.68])
    fig.colorbar(last, cax=cax, label="Root density")
    fig.subplots_adjust(right=0.88, wspace=0.08)
    fig.savefig(
        OUT_DIR / "precision_root_density_0601.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _plot_delta_root_timeline():
    soils = ("sandy_loam", "loam", "clay_loam")
    grid = "base_x100"
    scenario = "long_high_single"
    frames, selected_dates = _timeline_frames(soils, grid, scenario)
    if not selected_dates:
        raise ValueError("No common dates are available for the delta-root timeline.")
    max_abs_delta = max(
        [float(np.abs(frame["delta_theta"]).max()) for frame in frames.values()],
        default=0.0,
    )
    max_abs_delta = max(max_abs_delta, 1.0e-6)
    max_root = max(
        [float(frame["root_density"].max()) for frame in frames.values()],
        default=0.0,
    )
    root_levels = (
        np.linspace(0.0, max_root, 5)[1:] if max_root > 1.0e-9 else []
    )
    fig, axes = plt.subplots(
        len(soils),
        len(selected_dates),
        figsize=(8.8, 5.8),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    last = None
    for row_index, soil in enumerate(soils):
        drip_dir = REGRESSION_ROOT / f"{soil}__{grid}__{scenario}"
        wet_interval = _drip_wet_interval(drip_dir, soil)
        for column_index, date in enumerate(selected_dates):
            ax = axes[row_index, column_index]
            frame = frames[(soil, date)]
            triang = mtri.Triangulation(frame["X"], frame["depth_cm"])
            last = ax.tricontourf(
                triang,
                frame["delta_theta"],
                levels=np.linspace(-max_abs_delta, max_abs_delta, 17),
                cmap="RdBu_r",
                vmin=-max_abs_delta,
                vmax=max_abs_delta,
            )
            if len(root_levels) > 0:
                ax.tricontour(
                    triang,
                    frame["root_density"],
                    levels=root_levels,
                    colors="#2a9d8f",
                    linewidths=0.35,
                    alpha=0.75,
                )
            _mark_drip(ax, drip_dir, wet_interval=wet_interval, label=False)
            if row_index == 0:
                ax.set_title(_short_date_label(date), fontsize=6)
            if column_index == 0:
                ax.set_ylabel(f"{soil}\nDepth (cm)")
            if row_index == len(soils) - 1:
                ax.set_xlabel("x (cm)")
            ax.invert_yaxis()
            ax.tick_params(labelsize=5)
    cax = fig.add_axes([0.91, 0.17, 0.018, 0.68])
    fig.colorbar(last, cax=cax, label="Delta theta")
    fig.subplots_adjust(right=0.88, wspace=0.08, hspace=0.16)
    fig.savefig(
        OUT_DIR / "precision_delta_theta_root_timeline.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _plot_root_density_timeline():
    soils = ("sandy_loam", "loam", "clay_loam")
    grid = "base_x100"
    scenario = "long_high_single"
    frames, selected_dates = _timeline_frames(soils, grid, scenario)
    if not selected_dates:
        raise ValueError("No common dates are available for the root timeline.")
    max_root = max(
        [float(frame["root_density"].max()) for frame in frames.values()],
        default=0.0,
    )
    max_root = max(max_root, 1.0e-9)
    fig, axes = plt.subplots(
        len(soils),
        len(selected_dates),
        figsize=(8.8, 5.8),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    last = None
    for row_index, soil in enumerate(soils):
        drip_dir = REGRESSION_ROOT / f"{soil}__{grid}__{scenario}"
        wet_interval = _drip_wet_interval(drip_dir, soil)
        for column_index, date in enumerate(selected_dates):
            ax = axes[row_index, column_index]
            frame = frames[(soil, date)]
            triang = mtri.Triangulation(frame["X"], frame["depth_cm"])
            last = ax.tricontourf(
                triang,
                frame["root_density"],
                levels=np.linspace(0.0, max_root, 15),
                cmap="YlGn",
                vmin=0.0,
                vmax=max_root,
            )
            _mark_drip(ax, drip_dir, wet_interval=wet_interval, label=False)
            if row_index == 0:
                ax.set_title(_short_date_label(date), fontsize=6)
            if column_index == 0:
                ax.set_ylabel(f"{soil}\nDepth (cm)")
            if row_index == len(soils) - 1:
                ax.set_xlabel("x (cm)")
            ax.invert_yaxis()
            ax.tick_params(labelsize=5)
    cax = fig.add_axes([0.91, 0.17, 0.018, 0.68])
    fig.colorbar(last, cax=cax, label="Root density")
    fig.subplots_adjust(right=0.88, wspace=0.08, hspace=0.16)
    fig.savefig(
        OUT_DIR / "precision_root_density_timeline.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _timeline_frames(soils, grid, scenario, max_dates=4):
    selected_dates = None
    source = {}
    for soil in soils:
        baseline_g03 = _read_g03(
            REGRESSION_ROOT / f"{soil}__{grid}__baseline" / "LOAM2D.G03"
        )
        drip_dir = REGRESSION_ROOT / f"{soil}__{grid}__{scenario}"
        drip_g03 = _read_g03(drip_dir / "LOAM2D.G03")
        root_g04 = _read_g04(drip_dir / "LOAM2D.G04")
        common_dates = _common_spatial_dates(baseline_g03, drip_g03, root_g04)
        case_dates = _select_timeline_dates(common_dates, max_dates=max_dates)
        selected_dates = case_dates if selected_dates is None else selected_dates
        if tuple(case_dates) != tuple(selected_dates):
            raise ValueError(
                "Timeline figure requires matching common dates across soils."
            )
        source[soil] = (baseline_g03, drip_g03, root_g04)
    frames = {}
    for soil, (baseline_g03, drip_g03, root_g04) in source.items():
        for date in selected_dates:
            frames[(soil, date)] = _delta_root_frame(
                baseline_g03,
                drip_g03,
                root_g04,
                date,
            )
    return frames, tuple(selected_dates or ())


def _select_timeline_dates(dates, max_dates=4):
    ordered = tuple(sorted(set(dates), key=lambda value: pd.to_datetime(value)))
    if len(ordered) <= max_dates:
        return ordered
    positions = np.linspace(0, len(ordered) - 1, max_dates)
    indexes = sorted({int(round(position)) for position in positions})
    return tuple(ordered[index] for index in indexes)


def _short_date_label(date):
    return pd.to_datetime(date).strftime("%m/%d")


def _drip_wet_interval(drip_dir, soil):
    width_limit = calibrated_drip_wet_width_max_cm(soil)
    coverage = _partial_coverage_at_target(
        Path(drip_dir) / "LOAM2D.grd",
        center_node=7,
        target_width=width_limit,
    )
    return (
        max(coverage["target_left_cm"], coverage["surface_left_cm"]),
        min(coverage["target_right_cm"], coverage["surface_right_cm"]),
    )


def _plot_spatial_delta_root_matrix():
    soils = ("sandy_loam", "loam", "clay_loam")
    scenarios = (
        "long_low_single",
        "long_multi_node",
        "long_high_single",
        "long_pressure_single",
    )
    grid = "base_x100"
    frames = {}
    max_abs_delta = 0.0
    max_root = 0.0
    for soil in soils:
        baseline = REGRESSION_ROOT / f"{soil}__{grid}__baseline"
        for scenario in scenarios:
            drip = REGRESSION_ROOT / f"{soil}__{grid}__{scenario}"
            frame = _delta_root_frame(
                _read_g03(baseline / "LOAM2D.G03"),
                _read_g03(drip / "LOAM2D.G03"),
                _read_g04(drip / "LOAM2D.G04"),
                DATE_FOR_PLATE,
            )
            frames[(soil, scenario)] = (drip, frame)
            max_abs_delta = max(
                max_abs_delta,
                float(np.abs(frame["delta_theta"]).max()),
            )
            max_root = max(max_root, float(frame["root_density"].max()))
    max_abs_delta = max(max_abs_delta, 1.0e-6)
    root_levels = (
        np.linspace(0.0, max_root, 5)[1:] if max_root > 1.0e-9 else []
    )

    fig, axes = plt.subplots(
        len(soils),
        len(scenarios),
        figsize=(8.8, 5.8),
        sharex=True,
        sharey=True,
    )
    last = None
    for row_index, soil in enumerate(soils):
        for column_index, scenario in enumerate(scenarios):
            ax = axes[row_index, column_index]
            drip_dir, frame = frames[(soil, scenario)]
            triang = mtri.Triangulation(frame["X"], frame["depth_cm"])
            last = ax.tricontourf(
                triang,
                frame["delta_theta"],
                levels=np.linspace(-max_abs_delta, max_abs_delta, 17),
                cmap="RdBu_r",
                vmin=-max_abs_delta,
                vmax=max_abs_delta,
            )
            if len(root_levels) > 0:
                ax.tricontour(
                    triang,
                    frame["root_density"],
                    levels=root_levels,
                    colors="#2a9d8f",
                    linewidths=0.35,
                    alpha=0.75,
                )
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
            _mark_drip(ax, drip_dir, wet_interval=wet_interval, label=False)
            if row_index == 0:
                ax.set_title(scenario.replace("_", " "), fontsize=6)
            if column_index == 0:
                ax.set_ylabel(f"{soil}\nDepth (cm)")
            if row_index == len(soils) - 1:
                ax.set_xlabel("x (cm)")
            ax.invert_yaxis()
            ax.tick_params(labelsize=5)
    cax = fig.add_axes([0.91, 0.17, 0.018, 0.68])
    fig.colorbar(last, cax=cax, label="Delta theta")
    fig.subplots_adjust(right=0.88, wspace=0.08, hspace=0.16)
    fig.savefig(
        OUT_DIR / "precision_spatial_delta_root_matrix.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _write_spatial_worst_cases(spatial):
    worst_cases = _select_spatial_worst_cases(spatial)
    worst_cases.to_csv(OUT_DIR / "precision_spatial_worst_cases.csv", index=False)
    return worst_cases


def _select_spatial_worst_cases(spatial, max_cases=SPATIAL_WORST_CASE_MIN_COUNT):
    frame = spatial.copy()
    if frame.empty:
        return frame

    selected = {}
    for criterion, column, ascending, description in SPATIAL_WORST_CASE_CRITERIA:
        row = _worst_row_for_column(frame, column, ascending)
        if row is None:
            continue
        _add_worst_case(
            selected,
            row,
            criterion,
            column,
            row["_criterion_value"],
            description,
        )

    severity = _spatial_worst_case_severity(frame)
    frame = frame.assign(_severity_score=severity)
    for _, row in frame.sort_values(["_severity_score", "case"]).iterrows():
        if len(selected) >= max_cases:
            break
        if str(row["case"]) in selected:
            continue
        _add_worst_case(
            selected,
            row,
            "composite_worst_rank",
            "composite_rank",
            row["_severity_score"],
            "composite weak-case rank across all spatial diagnostics",
        )

    rows = []
    for index, item in enumerate(selected.values(), start=1):
        record = dict(item["row"])
        record["selection_rank"] = index
        record["selection_metric_count"] = len(item["metrics"])
        record["selection_metric"] = ";".join(item["metrics"])
        record["selection_column"] = ";".join(item["columns"])
        record["selection_value"] = ";".join(f"{value:.12g}" for value in item["values"])
        record["selection_reason"] = "; ".join(item["descriptions"])
        rows.append(record)
    return pd.DataFrame.from_records(rows)


def _worst_row_for_column(frame, column, ascending):
    if column not in frame:
        return None
    numeric = pd.to_numeric(frame[column], errors="coerce")
    candidates = frame.loc[numeric.notna()].copy()
    if candidates.empty:
        return None
    values = numeric.loc[candidates.index]
    if float(values.max() - values.min()) <= 1.0e-12:
        return None
    candidates["_criterion_value"] = numeric.loc[candidates.index]
    candidates = candidates.sort_values(
        ["_criterion_value", "case"],
        ascending=[ascending, True],
    )
    return candidates.iloc[0]


def _spatial_worst_case_severity(frame):
    score = pd.Series(0.0, index=frame.index)
    count = pd.Series(0.0, index=frame.index)
    for _, column, ascending, _ in SPATIAL_WORST_CASE_CRITERIA:
        if column not in frame:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        valid = numeric.notna()
        if not valid.any():
            continue
        rank = numeric[valid].rank(method="average", ascending=ascending)
        score.loc[valid] += rank / float(valid.sum())
        count.loc[valid] += 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        severity = score / count.replace(0.0, np.nan)
    return severity.fillna(np.inf)


def _add_worst_case(selected, row, criterion, column, value, description):
    case = str(row["case"])
    if case not in selected:
        clean_row = {
            key: value
            for key, value in row.to_dict().items()
            if not str(key).startswith("_")
        }
        selected[case] = {
            "row": clean_row,
            "metrics": [],
            "columns": [],
            "values": [],
            "descriptions": [],
        }
    item = selected[case]
    item["metrics"].append(str(criterion))
    item["columns"].append(str(column))
    item["values"].append(float(value))
    item["descriptions"].append(str(description))


def _plot_spatial_worst_case_delta_root(spatial):
    worst_cases = _select_spatial_worst_cases(spatial)
    if worst_cases.empty:
        raise ValueError("No spatial worst cases are available for plotting.")

    panel_data = []
    max_abs_delta = 0.0
    max_root = 0.0
    for row in worst_cases.to_dict("records"):
        baseline = REGRESSION_ROOT / f"{row['soil']}__{row['grid']}__baseline"
        drip_dir = REGRESSION_ROOT / str(row["case"])
        frame = _delta_root_frame(
            _read_g03(baseline / "LOAM2D.G03"),
            _read_g03(drip_dir / "LOAM2D.G03"),
            _read_g04(drip_dir / "LOAM2D.G04"),
            str(row.get("date", DATE_FOR_PLATE)),
        )
        panel_data.append((row, drip_dir, frame))
        max_abs_delta = max(max_abs_delta, float(np.abs(frame["delta_theta"]).max()))
        max_root = max(max_root, float(frame["root_density"].max()))

    max_abs_delta = max(max_abs_delta, 1.0e-6)
    root_levels = (
        np.linspace(0.0, max_root, 5)[1:] if max_root > 1.0e-9 else []
    )
    column_count = 3
    row_count = int(np.ceil(len(panel_data) / column_count))
    fig, axes = plt.subplots(
        row_count,
        column_count,
        figsize=(8.8, 2.75 * row_count),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    last = None
    for axis in axes.ravel():
        axis.set_visible(False)
    for ax, (row, drip_dir, frame) in zip(axes.ravel(), panel_data):
        ax.set_visible(True)
        triang = mtri.Triangulation(frame["X"], frame["depth_cm"])
        last = ax.tricontourf(
            triang,
            frame["delta_theta"],
            levels=np.linspace(-max_abs_delta, max_abs_delta, 17),
            cmap="RdBu_r",
            vmin=-max_abs_delta,
            vmax=max_abs_delta,
        )
        if len(root_levels) > 0:
            ax.tricontour(
                triang,
                frame["root_density"],
                levels=root_levels,
                colors="#2a9d8f",
                linewidths=0.35,
                alpha=0.75,
            )
        wet_interval = _drip_wet_interval(drip_dir, str(row["soil"]))
        _mark_drip(ax, drip_dir, wet_interval=wet_interval, label=False)
        ax.set_title(
            f"{row['soil']} | {row['grid']}\n{str(row['scenario']).replace('_', ' ')}",
            fontsize=5.5,
        )
        ax.text(
            0.02,
            0.98,
            (
                f"{_short_date_label(row.get('date', DATE_FOR_PLATE))}\n"
                f"root dtheta={float(row['root_weighted_delta_theta']):.3g}\n"
                f"net={float(row['net_delta_storage_cm2']):.2f} cm2"
            ),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=5,
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.72,
                "pad": 1.5,
            },
        )
        ax.invert_yaxis()
        ax.tick_params(labelsize=5)
    for ax in axes[:, 0]:
        if ax.get_visible():
            ax.set_ylabel("Depth (cm)")
    for ax in axes[-1, :]:
        if ax.get_visible():
            ax.set_xlabel("x (cm)")
    cax = fig.add_axes([0.91, 0.17, 0.018, 0.68])
    fig.colorbar(last, cax=cax, label="Delta theta")
    fig.subplots_adjust(right=0.88, wspace=0.08, hspace=0.28)
    fig.savefig(
        OUT_DIR / "precision_spatial_worst_case_delta_root.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _plot_spatial_shape_metrics(spatial):
    spatial = spatial.copy()
    scenarios = sorted(spatial["scenario"].astype(str).unique())
    scenario_x = {name: index for index, name in enumerate(scenarios)}
    grid_offsets = {
        "narrow_x075": -0.22,
        "base_x100": 0.0,
        "wide_x125": 0.22,
    }
    soil_colors = {
        "clay_loam": "#756bb1",
        "loam": "#31a354",
        "sandy_loam": "#3182bd",
    }
    fig, axes = plt.subplots(2, 2, figsize=(6.2, 4.1), sharex=True)
    panels = (
        ("delta_theta_max", "Peak Delta theta"),
        ("positive_delta_area_cm2", "Positive area (cm2)"),
        ("positive_delta_max_depth_cm", "Max depth (cm)"),
        ("positive_delta_depth_width_ratio", "Depth/width"),
    )
    for ax, (column, label) in zip(axes.ravel(), panels):
        for (_, row) in spatial.iterrows():
            x_value = (
                scenario_x[str(row["scenario"])]
                + grid_offsets.get(str(row["grid"]), 0.0)
            )
            ax.scatter(
                x_value,
                row[column],
                s=16,
                color=soil_colors.get(str(row["soil"]), "#636363"),
                edgecolor="white",
                linewidth=0.3,
            )
        ax.set_xticks(np.arange(len(scenarios)))
        ax.set_xticklabels(scenarios, rotation=25, ha="right")
        ax.set_title(label)
        ax.grid(True, axis="y", color="#d9d9d9", linewidth=0.4)
        if column == "delta_theta_max":
            handles = [
                plt.Line2D(
                    [0],
                    [0],
                    marker="o",
                    linestyle="none",
                    markersize=4,
                    markerfacecolor=color,
                    markeredgecolor="white",
                    label=soil,
                )
                for soil, color in soil_colors.items()
            ]
            ax.legend(handles=handles, fontsize=5, loc="upper right")
    fig.tight_layout()
    fig.savefig(
        OUT_DIR / "precision_spatial_shape_metrics.png",
        dpi=600,
        bbox_inches="tight",
    )
    plt.close(fig)


def _plot_spatial_temporal_storage(temporal):
    frame = temporal[temporal["grid"] == "base_x100"].copy()
    if frame.empty:
        frame = temporal.copy()
    frame["date_time"] = pd.to_datetime(frame["date"])
    soil_colors = {
        "clay_loam": "#756bb1",
        "loam": "#31a354",
        "sandy_loam": "#3182bd",
    }
    scenario_styles = {
        "long_low_single": (0, (1, 1)),
        "long_multi_node": (0, (3, 1)),
        "long_high_single": "solid",
        "long_pressure_single": (0, (5, 1)),
    }
    panels = (
        ("positive_delta_storage_cm2", "Positive storage integral (cm2)"),
        ("net_delta_storage_cm2", "Net storage integral (cm2)"),
        ("positive_delta_root_storage_fraction", "Root-overlap storage fraction"),
    )
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 5.0), sharex=True)
    for ax, (column, label) in zip(axes, panels):
        for (soil, scenario), sub in frame.groupby(["soil", "scenario"]):
            sub = sub.sort_values("date_time")
            ax.plot(
                sub["date_time"],
                sub[column],
                color=soil_colors.get(str(soil), "#636363"),
                linestyle=scenario_styles.get(str(scenario), "solid"),
                linewidth=0.9,
                alpha=0.9,
            )
        ax.set_ylabel(label)
        ax.grid(True, axis="y", color="#d9d9d9", linewidth=0.4)
    axes[-1].set_xlabel("Date")
    axes[-1].tick_params(axis="x", rotation=30)
    soil_handles = [
        plt.Line2D([0], [0], color=color, linewidth=1.2, label=soil)
        for soil, color in soil_colors.items()
    ]
    scenario_handles = [
        plt.Line2D(
            [0],
            [0],
            color="#595959",
            linestyle=style,
            linewidth=1.2,
            label=scenario.replace("_", " "),
        )
        for scenario, style in scenario_styles.items()
    ]
    axes[0].legend(handles=soil_handles, fontsize=5, loc="upper right")
    axes[1].legend(handles=scenario_handles, fontsize=5, loc="upper right")
    fig.tight_layout()
    fig.savefig(
        OUT_DIR / "precision_spatial_temporal_storage.png",
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
        "DripActualInfil",
        "DripSourceInput",
        "DripSourceLoss",
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


def _scale_grid_around_node(path, center_node, x_scale):
    """Scale horizontal grid coordinates and boundary widths around one node."""
    grid_path = Path(path)
    lines = grid_path.read_text(encoding="utf-8").splitlines()
    layout = _grid_layout(lines)
    center_x, _ = _grid_node_xy(grid_path, center_node)

    for index in range(layout["node_start"], layout["node_start"] + layout["node_count"]):
        parts = lines[index].split()
        if len(parts) < 4:
            raise ValueError(f"Invalid grid node line {index + 1}: {lines[index]}")
        node, x_value, y_value, material = parts[:4]
        x_new = center_x + (float(x_value) - center_x) * float(x_scale)
        lines[index] = f"\t{node}\t{x_new:g}\t{float(y_value):g}\t{material}"

    boundary_stop = layout["boundary_start"] + layout["boundary_count"]
    for index in range(layout["boundary_start"], boundary_stop):
        parts = lines[index].split()
        if len(parts) < 6:
            raise ValueError(f"Invalid grid boundary line {index + 1}: {lines[index]}")
        node, code_w, code_c, code_h, code_g, width = parts[:6]
        lines[index] = (
            f"    {node} {code_w}    {code_c}     {code_h}    "
            f"{code_g}      {float(width) * float(x_scale):g}"
        )
    grid_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _refine_grid_fixed_domain(path, refinement_factor, center_node, x_scale=1.0):
    """Rewrite a structured MAIZSIM grid with fixed-domain horizontal refinement."""
    grid_path = Path(path)
    profile = _structured_grid_profile(grid_path)
    factor = int(refinement_factor)
    if factor < 1:
        raise ValueError("refinement_factor must be at least 1")
    center_x, _ = _grid_node_xy(grid_path, center_node)
    scaled_x = [
        center_x + (float(x_value) - center_x) * float(x_scale)
        for x_value in profile["x_values"]
    ]
    refined_x = _subdivide_coordinates(scaled_x, factor)
    reference_center_column = _coordinate_index(scaled_x, center_x)
    reference_source_width = _surface_widths_from_x(scaled_x)[
        reference_center_column
    ]
    center_column = _coordinate_index(refined_x, center_x)
    y_values = profile["y_values"]
    x_count = len(refined_x)
    y_count = len(y_values)
    node_count = x_count * y_count
    element_count = (x_count - 1) * (y_count - 1)
    boundary_count = 2 * x_count
    solver_bandwidth = x_count + 1
    if solver_bandwidth > GRID_REFINEMENT_MAX_BANDWIDTH:
        raise ValueError(
            f"Refined grid bandwidth {solver_bandwidth} exceeds "
            f"MBandD={GRID_REFINEMENT_MAX_BANDWIDTH}"
        )

    lines = [
        "***************** GRID GENERATOR INFORMATION **********************************************",
        "KAT   NumNP    NumEl   NumBP    IJ   NumMat",
        (
            f"  {profile['kat']}     {node_count}     {element_count}     "
            f"{boundary_count}     {x_count}     {profile['num_mat']}"
        ),
        "   n           x          y      MatNum",
    ]
    node_id = 1
    for y_value in y_values:
        for x_value in refined_x:
            lines.append(
                f"\t{node_id}\t{float(x_value):.10g}\t{float(y_value):.10g}\t1"
            )
            node_id += 1

    lines.extend(
        [
            "***************** ELEMENT INFORMATION ******************************************************",
            "         e         i         j         k         l     MatNumE",
        ]
    )
    element_id = 1
    for row_index in range(y_count - 1):
        for column_index in range(x_count - 1):
            top_left = row_index * x_count + column_index + 1
            bottom_left = (row_index + 1) * x_count + column_index + 1
            bottom_right = bottom_left + 1
            top_right = top_left + 1
            lines.append(
                f"\t{element_id}\t{top_left}\t{bottom_left}\t"
                f"{bottom_right}\t{top_right}\t1"
            )
            element_id += 1

    surface_widths = _surface_widths_from_x(refined_x)
    lines.extend(
        [
            "****************Boundary geometry information**************************************",
            "    n  CodeW  CodeC  CodeH  CodeG  Width",
        ]
    )
    for node, width in enumerate(surface_widths, start=1):
        lines.append(f"    {node} -4    0     -4    -4      {width:.10g}")
    bottom_start = (y_count - 1) * x_count + 1
    bottom_nodes = list(range(bottom_start, bottom_start + x_count))
    for node, width in zip(bottom_nodes, surface_widths):
        lines.append(f"    {node}   -2   0       1         1      {width:.10g}")

    lines.extend(
        [
            "***************************Seepage face information********************************************",
            "NSeep",
            "  1",
            "NSP(1)",
            f" {len(bottom_nodes)}",
            "NP(NSP,1)  NP(NSP,2)  NP(NSP,3) ...... NP(NSP,IJ-1)NP(NSP,IJ)",
            _format_int_row(bottom_nodes),
            "***************************Drainage Boundaries******************************************",
            "NDrain",
            "0",
        ]
    )
    grid_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _rewrite_nod_fixed_domain(
        grid_path.with_suffix(".nod"),
        profile,
        scaled_x,
        refined_x,
    )
    drip_node = center_column + 1
    return {
        "x_node_count": x_count,
        "y_node_count": y_count,
        "node_count": node_count,
        "element_count": element_count,
        "boundary_count": boundary_count,
        "solver_bandwidth": solver_bandwidth,
        "drip_node": drip_node,
        "drip_node_x_cm": refined_x[center_column],
        "reference_source_width_cm": reference_source_width,
        "domain_left_cm": refined_x[0],
        "domain_right_cm": refined_x[-1],
    }


def _structured_grid_profile(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    layout = _grid_layout(lines)
    header_index = next(
        index
        for index, line in enumerate(lines)
        if "KAT" in line and "NumNP" in line
    )
    counts = lines[header_index + 1].split()
    kat = int(counts[0])
    node_count = int(counts[1])
    element_count = int(counts[2])
    boundary_count = int(counts[3])
    x_count = int(counts[4])
    num_mat = int(counts[5])
    if node_count != layout["node_count"]:
        raise ValueError(f"Grid node count header mismatch in {path}")
    if boundary_count != layout["boundary_count"]:
        raise ValueError(f"Grid boundary count header mismatch in {path}")
    if node_count % x_count != 0:
        raise ValueError(f"Grid node count is not divisible by IJ in {path}")
    y_count = node_count // x_count
    expected_elements = (x_count - 1) * (y_count - 1)
    if element_count != expected_elements:
        raise ValueError(
            f"Grid element count {element_count} does not match structured "
            f"{x_count} x {y_count} grid"
        )

    nodes = []
    for line in lines[layout["node_start"] : layout["node_start"] + node_count]:
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"Invalid grid node line in {path}: {line}")
        nodes.append(
            {
                "node": int(parts[0]),
                "x": float(parts[1]),
                "y": float(parts[2]),
                "material": int(parts[3]),
            }
        )
    for expected_node, item in enumerate(nodes, start=1):
        if item["node"] != expected_node:
            raise ValueError(f"Grid nodes must be sequential in {path}")

    x_values = [nodes[index]["x"] for index in range(x_count)]
    y_values = []
    for row_index in range(y_count):
        row = nodes[row_index * x_count : (row_index + 1) * x_count]
        row_x = [item["x"] for item in row]
        if not np.allclose(row_x, x_values, rtol=0.0, atol=1.0e-8):
            raise ValueError(f"Grid row {row_index + 1} has nonmatching x values")
        row_y = [item["y"] for item in row]
        if max(row_y) - min(row_y) > 1.0e-8:
            raise ValueError(f"Grid row {row_index + 1} has nonconstant y")
        y_values.append(row_y[0])

    return {
        "kat": kat,
        "num_mat": num_mat,
        "x_count": x_count,
        "y_count": y_count,
        "node_count": node_count,
        "x_values": x_values,
        "y_values": y_values,
    }


def _subdivide_coordinates(values, factor):
    refined = []
    for left, right in zip(values[:-1], values[1:]):
        for step in range(factor):
            refined.append(left + (right - left) * step / factor)
    refined.append(values[-1])
    return refined


def _coordinate_index(values, target):
    distances = [abs(float(value) - float(target)) for value in values]
    index = int(np.argmin(distances))
    if distances[index] > 1.0e-7:
        raise ValueError(f"Coordinate {target:g} is not present in refined grid")
    return index


def _surface_widths_from_x(x_values):
    widths = []
    for index, x_value in enumerate(x_values):
        if len(x_values) == 1:
            widths.append(0.0)
        elif index == 0:
            widths.append(0.5 * (x_values[1] - x_value))
        elif index == len(x_values) - 1:
            widths.append(0.5 * (x_value - x_values[index - 1]))
        else:
            widths.append(0.5 * (x_values[index + 1] - x_values[index - 1]))
    return widths


def _rewrite_nod_fixed_domain(path, grid_profile, old_x_values, new_x_values):
    nod_path = Path(path)
    lines = nod_path.read_text(encoding="utf-8").splitlines()
    header = lines[:2]
    records = []
    for line in lines[2:]:
        parts = line.split()
        if not parts:
            continue
        records.append([float(value) for value in parts])
    if len(records) != grid_profile["node_count"]:
        raise ValueError(
            f"Nodal record count {len(records)} does not match grid "
            f"node count {grid_profile['node_count']} in {nod_path}"
        )
    x_count = grid_profile["x_count"]
    y_count = grid_profile["y_count"]
    new_lines = list(header)
    node_id = 1
    old_x = np.asarray(old_x_values, dtype=float)
    new_x = np.asarray(new_x_values, dtype=float)
    for row_index in range(y_count):
        row = np.asarray(
            records[row_index * x_count : (row_index + 1) * x_count],
            dtype=float,
        )
        for x_value in new_x:
            interpolated = [
                float(np.interp(x_value, old_x, row[:, column]))
                for column in range(1, row.shape[1])
            ]
            new_lines.append(
                "\t"
                + "\t".join(
                    [str(node_id)]
                    + [f"{value:.8g}" for value in interpolated]
                )
            )
            node_id += 1
    nod_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _format_int_row(values):
    return "".join(f"{int(value):8d}" for value in values)


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


def _fortran_effective_target_width(hydrus_target_width, center_width, width_limit):
    return min(max(float(hydrus_target_width), float(center_width)), float(width_limit))


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


def _mark_drip(ax, case_dir, wet_interval=None, label=True):
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
        if label:
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
    if label:
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
