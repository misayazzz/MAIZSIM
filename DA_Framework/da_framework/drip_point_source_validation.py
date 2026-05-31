"""Build and verify DripSpreadMode=4 point-source drip cases."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
import pandas as pd

from .drip_validation import read_g05_surface_water
from .model_runner import MODEL_FAILURE_MARKERS, run_model


REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_RUN = REPO_ROOT / "DA_Framework" / "base_runs" / "SingleLayerLoam2D"
BUILD_OUTPUT = REPO_ROOT / "build" / "maizsim" / "x64" / "Release"
MODEL_EXE = "2dMAIZSIM.exe"
MODEL_DLL = "Maizsim.dll"
INITIAL_DATE = date(2007, 5, 18)
DRIP_START = datetime(2007, 5, 20, 0, 0)
SOURCE_NODE = 1
SOURCE_WIDTH_CM = 0.38
DRIP_RATE_CM_H = 0.5
GRID_WIDTH_CM = 38.1
DELTA_LEVELS = (0.02, 0.05)
FRAME_MATCH_ATOL_DAYS = 1.0e-8
MAX_FRAME_OFFSET_DAYS = 0.08
DEFAULT_EMITTER_SPACING_M = 0.30


@dataclass(frozen=True)
class SoilCase:
    name: str
    theta_r: float
    theta_s: float
    alpha: float
    n: float
    ks_cm_day: float
    bulk_density: float
    organic_matter: float
    sand: float
    silt: float


@dataclass(frozen=True)
class DripScenario:
    name: str
    scenario_group: str = "current"
    drip_rate_cm_h: float = DRIP_RATE_CM_H
    source_width_cm: float = SOURCE_WIDTH_CM
    drip_duration_h: float = 24.0
    final_elapsed_h: float = 24.0
    figure_elapsed_hours: tuple[float, ...] = (6.0, 12.0, 24.0)
    delta_levels: tuple[float, ...] = DELTA_LEVELS
    target_grid_input_mm: float | None = None
    grid_refinement_factor: int = 1

    @property
    def drip_stop(self):
        return DRIP_START + timedelta(hours=self.drip_duration_h)

    @property
    def final_date(self):
        return (DRIP_START + timedelta(hours=self.final_elapsed_h)).date()

    @property
    def local_applied_depth_cm(self):
        return self.drip_rate_cm_h * self.drip_duration_h

    @property
    def source_area_cm2_per_cm_row(self):
        return self.local_applied_depth_cm * self.source_width_cm

    @property
    def applied_water_cross_section_cm2_per_cm_row(self):
        return self.local_applied_depth_cm * self.source_width_cm


def _rate_for_grid_input(target_mm, source_width_cm, duration_h=24.0, grid_width_cm=GRID_WIDTH_CM):
    return float(target_mm) / 10.0 * float(grid_width_cm) / (
        float(source_width_cm) * float(duration_h)
    )


def _grid_input_mm(rate_cm_h, source_width_cm, duration_h=24.0, grid_width_cm=GRID_WIDTH_CM):
    return (
        float(rate_cm_h)
        * float(duration_h)
        * float(source_width_cm)
        / float(grid_width_cm)
        * 10.0
    )


def _line_source_flux_l_h_m(rate_cm_h, source_width_cm, mirrored=True):
    symmetry_factor = 2.0 if mirrored else 1.0
    return symmetry_factor * float(rate_cm_h) * float(source_width_cm) / 10.0


def _emitter_flow_l_h(rate_cm_h, source_width_cm, emitter_spacing_m, mirrored=True):
    return _line_source_flux_l_h_m(
        rate_cm_h,
        source_width_cm,
        mirrored=mirrored,
    ) * float(emitter_spacing_m)


def _equivalent_local_flux_cm_h(grid_depth_mm, source_width_cm, duration_h, grid_width_cm):
    return _rate_for_grid_input(
        grid_depth_mm,
        source_width_cm,
        duration_h=duration_h,
        grid_width_cm=grid_width_cm,
    )


def _rate_for_line_source_flux(line_flux_l_h_m, source_width_cm, mirrored=True):
    symmetry_factor = 2.0 if mirrored else 1.0
    return float(line_flux_l_h_m) * 10.0 / (
        symmetry_factor * float(source_width_cm)
    )


def _rate_for_emitter_flow(emitter_flow_l_h, emitter_spacing_m, source_width_cm, mirrored=True):
    return _rate_for_line_source_flux(
        float(emitter_flow_l_h) / float(emitter_spacing_m),
        source_width_cm,
        mirrored=mirrored,
    )


def _number_label(value):
    return f"{float(value):g}".replace(".", "p")


DEFAULT_SCENARIO = DripScenario("current_24h", target_grid_input_mm=1.2)
SUPPLEMENTAL_SCENARIOS = (
    DEFAULT_SCENARIO,
    DripScenario(
        "high_total_rate5_24h",
        scenario_group="supplemental",
        drip_rate_cm_h=5.0,
        source_width_cm=SOURCE_WIDTH_CM,
        drip_duration_h=24.0,
        final_elapsed_h=24.0,
        figure_elapsed_hours=(6.0, 12.0, 24.0),
    ),
    DripScenario(
        "redistribution_24h_to_72h",
        scenario_group="supplemental",
        drip_rate_cm_h=DRIP_RATE_CM_H,
        source_width_cm=SOURCE_WIDTH_CM,
        drip_duration_h=24.0,
        final_elapsed_h=72.0,
        figure_elapsed_hours=(24.0, 48.0, 72.0),
    ),
    DripScenario(
        "width2cm_fixed_total_24h",
        scenario_group="supplemental",
        drip_rate_cm_h=DRIP_RATE_CM_H * SOURCE_WIDTH_CM / 2.0,
        source_width_cm=2.0,
        drip_duration_h=24.0,
        final_elapsed_h=24.0,
        figure_elapsed_hours=(6.0, 12.0, 24.0),
    ),
)
RATE_MATRIX_SCENARIOS = tuple(
    DripScenario(
        f"rate{_number_label(rate)}cmh_width0p38_24h",
        scenario_group="rate_matrix",
        drip_rate_cm_h=rate,
        source_width_cm=SOURCE_WIDTH_CM,
        drip_duration_h=24.0,
        final_elapsed_h=24.0,
        figure_elapsed_hours=(6.0, 12.0, 24.0),
    )
    for rate in (0.5, 1.0, 2.0)
)
FIXED_TOTAL_SCENARIOS = tuple(
    DripScenario(
        f"fixed_total{_number_label(target_mm)}mm_width0p38_24h",
        scenario_group="fixed_total",
        drip_rate_cm_h=_rate_for_grid_input(target_mm, SOURCE_WIDTH_CM),
        source_width_cm=SOURCE_WIDTH_CM,
        drip_duration_h=24.0,
        final_elapsed_h=24.0,
        figure_elapsed_hours=(6.0, 12.0, 24.0),
        target_grid_input_mm=target_mm,
    )
    for target_mm in (1.2, 10.0, 40.0)
)
SOURCE_WIDTH_SCENARIOS = tuple(
    DripScenario(
        f"width{_number_label(source_width)}cm_fixed1p2mm_24h",
        scenario_group="source_width",
        drip_rate_cm_h=_rate_for_grid_input(1.2, source_width),
        source_width_cm=source_width,
        drip_duration_h=24.0,
        final_elapsed_h=24.0,
        figure_elapsed_hours=(6.0, 12.0, 24.0),
        target_grid_input_mm=1.2,
    )
    for source_width in (0.38, 1.0, 2.0, 5.0)
)
GRID_REFINEMENT_SCENARIOS = tuple(
    DripScenario(
        f"gridx{factor}_fixed1p2mm_width0p38_24h",
        scenario_group="grid_refinement",
        drip_rate_cm_h=_rate_for_grid_input(1.2, SOURCE_WIDTH_CM),
        source_width_cm=SOURCE_WIDTH_CM,
        drip_duration_h=24.0,
        final_elapsed_h=24.0,
        figure_elapsed_hours=(6.0, 12.0, 24.0),
        target_grid_input_mm=1.2,
        grid_refinement_factor=factor,
    )
    for factor in (1, 2, 3)
)
HIGH_TOTAL_SOURCE_WIDTH_SCENARIOS = tuple(
    DripScenario(
        f"total{_number_label(target_mm)}mm_width{_number_label(source_width)}cm_24h",
        scenario_group="total_source_width",
        drip_rate_cm_h=_rate_for_grid_input(target_mm, source_width),
        source_width_cm=source_width,
        drip_duration_h=24.0,
        final_elapsed_h=24.0,
        figure_elapsed_hours=(6.0, 12.0, 24.0),
        target_grid_input_mm=target_mm,
    )
    for target_mm in (10.0, 40.0)
    for source_width in (0.38, 1.0, 2.0, 5.0, 10.0)
)
REDISTRIBUTION_SCENARIOS = (
    DripScenario(
        "redistribution_total1p2mm_width0p38_72h",
        scenario_group="redistribution",
        drip_rate_cm_h=_rate_for_grid_input(1.2, SOURCE_WIDTH_CM),
        source_width_cm=SOURCE_WIDTH_CM,
        drip_duration_h=24.0,
        final_elapsed_h=72.0,
        figure_elapsed_hours=(24.0, 48.0, 72.0),
        target_grid_input_mm=1.2,
    ),
    DripScenario(
        "redistribution_total10mm_width5cm_72h",
        scenario_group="redistribution",
        drip_rate_cm_h=_rate_for_grid_input(10.0, 5.0),
        source_width_cm=5.0,
        drip_duration_h=24.0,
        final_elapsed_h=72.0,
        figure_elapsed_hours=(24.0, 48.0, 72.0),
        target_grid_input_mm=10.0,
    ),
    DripScenario(
        "redistribution_total40mm_width10cm_72h",
        scenario_group="redistribution",
        drip_rate_cm_h=_rate_for_grid_input(40.0, 10.0),
        source_width_cm=10.0,
        drip_duration_h=24.0,
        final_elapsed_h=72.0,
        figure_elapsed_hours=(24.0, 48.0, 72.0),
        target_grid_input_mm=40.0,
    ),
)
SYSTEMATIC_SCENARIOS = (
    RATE_MATRIX_SCENARIOS
    + FIXED_TOTAL_SCENARIOS
    + SOURCE_WIDTH_SCENARIOS
    + GRID_REFINEMENT_SCENARIOS
)
ENHANCED_SCENARIOS = HIGH_TOTAL_SOURCE_WIDTH_SCENARIOS + REDISTRIBUTION_SCENARIOS


SOILS = (
    SoilCase("sandy_loam", 0.065, 0.410, 0.075, 1.890, 106.10, 1.55, 0.0020, 0.65, 0.25),
    SoilCase("loam", 0.078, 0.430, 0.036, 1.560, 30.00, 1.40, 0.0025, 0.43, 0.39),
    SoilCase("clay_loam", 0.095, 0.410, 0.019, 1.310, 6.24, 1.30, 0.0030, 0.30, 0.34),
)


def run_validation(workspace, executable_dir=None, timeout_seconds=180, scenario=DEFAULT_SCENARIO):
    """Run baseline/drip mode4 cases and write figures plus summary tables."""
    output_root = Path(workspace).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    executable_root = Path(executable_dir).resolve() if executable_dir else BUILD_OUTPUT
    cases_root = output_root / "codex_cases"
    figures_root = output_root / "codex_figures"
    tables_root = output_root / "codex_tables"
    for path in (cases_root, figures_root, tables_root):
        path.mkdir(parents=True, exist_ok=True)

    rows = []
    shape_rows = []
    storage_rows = []
    delta_contact_records = []
    figure_paths = []
    for soil in SOILS:
        baseline_dir = cases_root / f"codex_{soil.name}_baseline"
        drip_dir = cases_root / f"codex_{soil.name}_mode4_drip"
        _prepare_case(baseline_dir, soil, executable_root, drip=False, scenario=scenario)
        _prepare_case(drip_dir, soil, executable_root, drip=True, scenario=scenario)

        for run_dir in (baseline_dir, drip_dir):
            result = run_model(run_dir, timeout_seconds=timeout_seconds)
            if not result.success:
                raise RuntimeError(f"{run_dir.name} failed: {result.message}")
            _assert_no_failure_markers(run_dir)

        baseline_g03 = _read_g03(_find_output_file(baseline_dir, ".G03"))
        drip_g03 = _read_g03(_find_output_file(drip_dir, ".G03"))
        baseline_g05 = read_g05_surface_water(_find_output_file(baseline_dir, ".G05"))
        g05 = read_g05_surface_water(_find_output_file(drip_dir, ".G05"))
        grid_info = _grid_case_info(drip_dir / "LOAM2D.grd")

        balance = _drip_balance(g05)
        runoff_fraction = _safe_fraction(balance["surface_runoff"], balance["input"])
        actual_fraction = _safe_fraction(balance["actual"], balance["input"])
        soil_ks_cm_h = soil.ks_cm_day / 24.0
        actual_local_flux_cm_h = _equivalent_local_flux_cm_h(
            balance["actual"],
            scenario.source_width_cm,
            scenario.drip_duration_h,
            grid_info["grid_width_cm"],
        )
        runoff_local_flux_cm_h = _equivalent_local_flux_cm_h(
            balance["surface_runoff"],
            scenario.source_width_cm,
            scenario.drip_duration_h,
            grid_info["grid_width_cm"],
        )
        application_width_max = float(
            g05.get("drip_surface_application_width_max_cm", pd.Series([0.0])).max()
        )
        application_width_mean_all_rows = float(
            g05.get("drip_surface_application_width_mean_cm", pd.Series([0.0])).mean()
        )
        application_width_mean_active = _active_application_width_mean(g05)
        rows.append(
            {
                "soil": soil.name,
                "scenario": scenario.name,
                "scenario_group": scenario.scenario_group,
                "drip_input_mm": balance["input"],
                "drip_actual_infil_mm": balance["actual"],
                "drip_storage_change_mm": balance["storage_change"],
                "drip_surface_runoff_mm": balance["surface_runoff"],
                "drip_hydraulic_excess_mm": balance["hydraulic_excess"],
                "acceptance_residual_mm": balance["residual"],
                "drip_actual_infiltration_fraction": actual_fraction,
                "drip_runoff_fraction": runoff_fraction,
                "minor_runoff_warning": runoff_fraction > 0.05,
                "high_runoff_warning": runoff_fraction > 0.2,
                "capacity_limited_warning": runoff_fraction > 0.2,
                "capacity_limited_warning_basis": "high_runoff_fraction_gt_0p2",
                "drip_surface_storage_max_mm": balance["storage_max"],
                "drip_surface_application_width_mean_cm": application_width_mean_active,
                "drip_surface_application_width_mean_all_rows_cm": application_width_mean_all_rows,
                "drip_surface_application_width_max_cm": application_width_max,
                "drip_wet_width_max_cm": application_width_max,
                "theta_min": float(drip_g03["theta"].min()),
                "theta_max": float(drip_g03["theta"].max()),
                "drip_rate_cm_h": scenario.drip_rate_cm_h,
                "source_width_cm": scenario.source_width_cm,
                "drip_duration_h": scenario.drip_duration_h,
                "final_elapsed_h": scenario.final_elapsed_h,
                "target_grid_input_mm": scenario.target_grid_input_mm,
                "expected_grid_input_mm": _grid_input_mm(
                    scenario.drip_rate_cm_h,
                    scenario.source_width_cm,
                    scenario.drip_duration_h,
                    grid_info["grid_width_cm"],
                ),
                "local_applied_depth_cm": scenario.local_applied_depth_cm,
                "applied_water_cross_section_cm2_per_cm_row": (
                    scenario.applied_water_cross_section_cm2_per_cm_row
                ),
                "source_area_cm2_per_cm_row": scenario.source_area_cm2_per_cm_row,
                "drip_actual_local_flux_cm_h": actual_local_flux_cm_h,
                "drip_runoff_local_flux_cm_h": runoff_local_flux_cm_h,
                "soil_ks_cm_h": soil_ks_cm_h,
                "source_flux_to_ks_ratio": _safe_fraction(
                    scenario.drip_rate_cm_h,
                    soil_ks_cm_h,
                ),
                "actual_local_flux_to_ks_ratio": _safe_fraction(
                    actual_local_flux_cm_h,
                    soil_ks_cm_h,
                ),
                "line_source_flux_l_h_m_half_domain": _line_source_flux_l_h_m(
                    scenario.drip_rate_cm_h,
                    scenario.source_width_cm,
                    mirrored=False,
                ),
                "line_source_flux_l_h_m_mirrored": _line_source_flux_l_h_m(
                    scenario.drip_rate_cm_h,
                    scenario.source_width_cm,
                    mirrored=True,
                ),
                "emitter_flow_l_h_at_0p3m_spacing": _emitter_flow_l_h(
                    scenario.drip_rate_cm_h,
                    scenario.source_width_cm,
                    DEFAULT_EMITTER_SPACING_M,
                    mirrored=True,
                ),
                "grid_refinement_factor": scenario.grid_refinement_factor,
                **grid_info,
                "source_node": SOURCE_NODE,
                "drip_spread_mode": 4,
            }
        )
        _assert_g05_is_physical(g05, soil.name)
        _assert_theta_is_finite(drip_g03, soil)

        for elapsed_h in scenario.figure_elapsed_hours:
            for threshold in scenario.delta_levels:
                shape = _delta_shape_metrics(
                    baseline_g03,
                    drip_g03,
                    elapsed_h,
                    threshold=threshold,
                    mirror=True,
                    scenario=scenario,
                    grid_width_cm=grid_info["grid_width_cm"],
                )
                shape_rows.append(
                    {
                        "soil": soil.name,
                        "scenario": scenario.name,
                        "scenario_group": scenario.scenario_group,
                        "drip_rate_cm_h": scenario.drip_rate_cm_h,
                        "source_width_cm": scenario.source_width_cm,
                        "drip_duration_h": scenario.drip_duration_h,
                        "final_elapsed_h": scenario.final_elapsed_h,
                        "target_grid_input_mm": scenario.target_grid_input_mm,
                        "grid_refinement_factor": scenario.grid_refinement_factor,
                        **grid_info,
                        "elapsed_h": elapsed_h,
                        **shape,
                    }
                )
            delta_contact_records.append(
                {
                    "soil": soil.name,
                    "elapsed_h": elapsed_h,
                    "delta": _delta_frame(baseline_g03, drip_g03, elapsed_h, scenario=scenario),
                }
            )
            storage_rows.append(
                {
                    "soil": soil.name,
                    "scenario": scenario.name,
                    "scenario_group": scenario.scenario_group,
                    "drip_rate_cm_h": scenario.drip_rate_cm_h,
                    "source_width_cm": scenario.source_width_cm,
                    "target_grid_input_mm": scenario.target_grid_input_mm,
                    "expected_grid_input_mm": _grid_input_mm(
                        scenario.drip_rate_cm_h,
                        scenario.source_width_cm,
                        scenario.drip_duration_h,
                        grid_info["grid_width_cm"],
                    ),
                    "grid_refinement_factor": scenario.grid_refinement_factor,
                    **grid_info,
                    "elapsed_h": elapsed_h,
                    **_g03_storage_balance(
                        baseline_g03,
                        drip_g03,
                        baseline_g05,
                        g05,
                        elapsed_h,
                        grid_info["grid_width_cm"],
                    ),
                }
            )

        figure_paths.extend(
            _write_soil_figures(soil.name, baseline_g03, drip_g03, figures_root, scenario)
        )

    figure_paths.extend(_write_delta_contact_sheets(delta_contact_records, figures_root, scenario))
    summary = pd.DataFrame(rows)
    shapes = pd.DataFrame(shape_rows)
    storage = pd.DataFrame(storage_rows)
    summary_path = tables_root / "codex_mode4_point_source_summary.csv"
    shapes_path = tables_root / "codex_mode4_wetted_front_metrics.csv"
    storage_path = tables_root / "codex_mode4_g03_storage_balance.csv"
    manifest_path = output_root / "codex_mode4_point_source_manifest.json"
    summary.to_csv(summary_path, index=False)
    shapes.to_csv(shapes_path, index=False)
    storage.to_csv(storage_path, index=False)
    _write_manifest(
        manifest_path,
        output_root,
        summary_path,
        shapes_path,
        storage_path,
        figure_paths,
        scenario,
    )
    return {
        "workspace": str(output_root),
        "summary_csv": str(summary_path),
        "shape_metrics_csv": str(shapes_path),
        "storage_balance_csv": str(storage_path),
        "manifest_json": str(manifest_path),
        "figures": [str(path) for path in figure_paths],
        "summary": rows,
        "shape_metrics": shape_rows,
        "storage_balance": storage_rows,
    }


def run_supplemental_validation(workspace, executable_dir=None, timeout_seconds=180):
    """Run the default scenario plus the smallest diagnostic scenario matrix."""
    return run_scenario_matrix(
        workspace,
        SUPPLEMENTAL_SCENARIOS,
        matrix_name="supplemental",
        executable_dir=executable_dir,
        timeout_seconds=timeout_seconds,
    )


def run_systematic_validation(workspace, executable_dir=None, timeout_seconds=180):
    """Run non-HYDRUS systematic rate, fixed-total, source-width, and grid checks."""
    return run_scenario_matrix(
        workspace,
        SYSTEMATIC_SCENARIOS,
        matrix_name="systematic",
        executable_dir=executable_dir,
        timeout_seconds=timeout_seconds,
    )


def run_enhanced_validation(workspace, executable_dir=None, timeout_seconds=180):
    """Run Pro-review follow-up checks for source width, totals, and redistribution."""
    return run_scenario_matrix(
        workspace,
        ENHANCED_SCENARIOS,
        matrix_name="enhanced",
        executable_dir=executable_dir,
        timeout_seconds=timeout_seconds,
    )


def run_scenario_matrix(
    workspace,
    scenarios,
    matrix_name,
    executable_dir=None,
    timeout_seconds=180,
):
    output_root = Path(workspace).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    executable_root = Path(executable_dir).resolve() if executable_dir else BUILD_OUTPUT
    tables_root = output_root / "codex_tables"
    tables_root.mkdir(parents=True, exist_ok=True)

    summaries = []
    shapes = []
    storage_balances = []
    figures = []
    scenario_outputs = []
    for scenario in scenarios:
        scenario_root = output_root / f"codex_{scenario.name}"
        result = run_validation(
            scenario_root,
            executable_dir=executable_root,
            timeout_seconds=timeout_seconds,
            scenario=scenario,
        )
        summaries.extend(result["summary"])
        shapes.extend(result["shape_metrics"])
        storage_balances.extend(result["storage_balance"])
        figures.extend(result["figures"])
        scenario_outputs.append(
            {
                "scenario": scenario.name,
                "workspace": result["workspace"],
                "summary_csv": result["summary_csv"],
                "shape_metrics_csv": result["shape_metrics_csv"],
                "storage_balance_csv": result["storage_balance_csv"],
                "manifest_json": result["manifest_json"],
            }
        )

    summary_path = tables_root / f"codex_mode4_{matrix_name}_summary.csv"
    shapes_path = tables_root / f"codex_mode4_{matrix_name}_wetted_front_metrics.csv"
    storage_path = tables_root / f"codex_mode4_{matrix_name}_g03_storage_balance.csv"
    manifest_path = output_root / f"codex_mode4_{matrix_name}_manifest.json"
    pd.DataFrame(summaries).to_csv(summary_path, index=False)
    pd.DataFrame(shapes).to_csv(shapes_path, index=False)
    pd.DataFrame(storage_balances).to_csv(storage_path, index=False)
    _write_matrix_manifest(
        manifest_path,
        output_root,
        matrix_name,
        scenarios,
        summary_path,
        shapes_path,
        storage_path,
        figures,
        scenario_outputs,
    )
    return {
        "workspace": str(output_root),
        "summary_csv": str(summary_path),
        "shape_metrics_csv": str(shapes_path),
        "storage_balance_csv": str(storage_path),
        "manifest_json": str(manifest_path),
        "scenario_outputs": scenario_outputs,
        "figures": figures,
        "summary": summaries,
        "shape_metrics": shapes,
        "storage_balance": storage_balances,
    }


def _prepare_case(run_dir, soil, executable_root, drip, scenario):
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(BASE_RUN, run_dir)
    for name in (MODEL_EXE, MODEL_DLL):
        shutil.copy2(executable_root / name, run_dir / name)
    _write_soil(run_dir / "Loam_200cm.soi", soil)
    _write_time_file(run_dir / "LOAM2D.tim", scenario.final_date)
    _write_ini_file(run_dir / "LOAM2D.ini", scenario.final_date)
    _write_water_mover(run_dir / "WaterMovDefault.dat")
    _write_zero_weather_header(run_dir / "WyeClimate.dat")
    _write_zero_weather(run_dir / "LOAM2D.wea", scenario.final_date)
    _write_zero_management(run_dir / "LOAM2D.man")
    _write_no_irrigation(run_dir / "LOAM2D.irr")
    if drip:
        _write_mode4_drip(run_dir / "LOAM2D.drp", scenario)
    else:
        _write_no_drip(run_dir / "LOAM2D.drp")
    _apply_grid_refinement(run_dir, scenario)


def _apply_grid_refinement(run_dir, scenario):
    factor = int(scenario.grid_refinement_factor)
    if factor == 1:
        return
    if factor < 1:
        raise ValueError("grid_refinement_factor must be at least 1")
    _refine_grid_fixed_domain(run_dir / "LOAM2D.grd", factor)


def _grid_case_info(path):
    profile = _structured_grid_profile(path)
    surface_widths = _surface_widths_from_x(profile["x_values"])
    return {
        "grid_x_node_count": profile["x_count"],
        "grid_y_node_count": profile["y_count"],
        "grid_node_count": profile["node_count"],
        "grid_element_count": (profile["x_count"] - 1) * (profile["y_count"] - 1),
        "grid_width_cm": float(sum(surface_widths)),
        "first_surface_width_cm": float(surface_widths[0]),
    }


def _refine_grid_fixed_domain(path, refinement_factor):
    """Rewrite the structured grid with fixed-domain horizontal refinement."""
    grid_path = Path(path)
    profile = _structured_grid_profile(grid_path)
    factor = int(refinement_factor)
    if factor < 1:
        raise ValueError("refinement_factor must be at least 1")
    if factor == 1:
        return _grid_case_info(grid_path)

    old_x = profile["x_values"]
    new_x = _subdivide_coordinates(old_x, factor)
    y_values = profile["y_values"]
    x_count = len(new_x)
    y_count = len(y_values)
    node_count = x_count * y_count
    element_count = (x_count - 1) * (y_count - 1)
    boundary_count = 2 * x_count

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
        for x_value in new_x:
            lines.append(f"\t{node_id}\t{float(x_value):.10g}\t{float(y_value):.10g}\t1")
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

    surface_widths = _surface_widths_from_x(new_x)
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
    _rewrite_nod_fixed_domain(grid_path.with_suffix(".nod"), profile, old_x, new_x)
    return _grid_case_info(grid_path)


def _structured_grid_profile(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    header_index = next(index for index, line in enumerate(lines) if "KAT" in line and "NumNP" in line)
    counts = lines[header_index + 1].split()
    kat = int(counts[0])
    node_count = int(counts[1])
    element_count = int(counts[2])
    boundary_count = int(counts[3])
    x_count = int(counts[4])
    num_mat = int(counts[5])
    layout = _grid_layout(lines, node_count=node_count, boundary_count=boundary_count)
    if node_count % x_count != 0:
        raise ValueError(f"Grid node count is not divisible by IJ in {path}")
    y_count = node_count // x_count
    expected_elements = (x_count - 1) * (y_count - 1)
    if element_count != expected_elements:
        raise ValueError(f"Grid element count {element_count} does not match {x_count} x {y_count}")

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
        "boundary_count": boundary_count,
        "x_values": x_values,
        "y_values": y_values,
    }


def _grid_layout(lines, node_count, boundary_count):
    node_header = next(index for index, line in enumerate(lines) if "MatNum" in line and "x" in line)
    boundary_header = next(index for index, line in enumerate(lines) if "CodeW" in line and "Width" in line)
    return {
        "node_start": node_header + 1,
        "node_count": int(node_count),
        "boundary_start": boundary_header + 1,
        "boundary_count": int(boundary_count),
    }


def _subdivide_coordinates(values, factor):
    refined = []
    for left, right in zip(values[:-1], values[1:]):
        for step in range(factor):
            refined.append(left + (right - left) * step / factor)
    refined.append(values[-1])
    return refined


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
        if parts:
            records.append([float(value) for value in parts])
    if len(records) != grid_profile["node_count"]:
        raise ValueError(
            f"Nodal record count {len(records)} does not match grid node count "
            f"{grid_profile['node_count']} in {nod_path}"
        )
    x_count = grid_profile["x_count"]
    y_count = grid_profile["y_count"]
    old_x = np.asarray(old_x_values, dtype=float)
    new_x = np.asarray(new_x_values, dtype=float)
    new_lines = list(header)
    node_id = 1
    for row_index in range(y_count):
        row = np.asarray(records[row_index * x_count : (row_index + 1) * x_count], dtype=float)
        for x_value in new_x:
            interpolated = [
                float(np.interp(x_value, old_x, row[:, column]))
                for column in range(1, row.shape[1])
            ]
            new_lines.append(
                "\t"
                + "\t".join([str(node_id)] + [f"{value:.8g}" for value in interpolated])
            )
            node_id += 1
    nod_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _format_int_row(values):
    return "".join(f"{int(value):8d}" for value in values)


def _write_soil(path, soil):
    lines = [
        "           *** Material information ****                                                                   g/g  ",
        "   thr       ths         tha       thm      Alfa      n        Ks         Kk       thk       BulkD     OM    Sand    Silt   InitType",
        (
            f" {soil.theta_r:.3f}\t {soil.theta_s:.3f}\t {soil.theta_r:.3f}\t "
            f"{soil.theta_s:.3f}\t {soil.alpha:.5f}\t {soil.n:.5f}\t "
            f"{soil.ks_cm_day:.3f}\t {soil.ks_cm_day:.3f}\t  {soil.theta_s:.3f}\t "
            f"{soil.bulk_density:.3f}\t {soil.organic_matter:.4f}\t "
            f"{soil.sand:.2f}\t {soil.silt:.2f}\t  'm'"
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_time_file(path, final_date):
    lines = [
        "*** SYNCHRONIZER INFORMATION *****************************",
        "Initial time       dt       dtMin     DMul1    DMul2    tFin",
        f"'{_fmt_date(INITIAL_DATE)}'   0.0001        0.0000001     1.3           0.3          '{_fmt_date(final_date)}'",
        "Output variables, 1 if true  Daily    Hourly",
        " 1             1 ",
        " Daily       Hourly   Weather data frequency. if daily enter 1   0; if hourly enter 0  1  ",
        " 0             1 ",
        "RunToEnd  - if 1 model continues after crop maturity to end time in time file",
        " 1 ",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ini_file(path, final_date):
    lines = [
        "***INitialization data for mode4 point-source drip validation",
        "POPROW  ROWSP  Plant Density      ROWANG  xSeed  ySeed         CEC    EOMult",
        " 5.2578        76.2          6.9           0             0             137           0.65          0.5 ",
        "Latitude longitude altitude",
        " 39.02         76.55         50 ",
        "AutoIrrigate",
        " 0 ",
        "  Sowing        end         timestep",
        "'05/18/2007'  '09/18/2007'  60",
        "output soils data (g03, g04, g05 and g06 files) 1 if true",
        f"'05/18/2007'  '{_fmt_date(final_date)}'  60",
        "    0                     1",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_water_mover(path):
    lines = [
        " *** WATER MOVER PARAMETERINFORMATION **************************",
        "MaxIt   TolTh TolH    hCritA       hCritS      DtMx  htab1   htabN EPSI.Heat  EPSI.Solute",
        " 30            0.01          0.05         -1.0000E+5    1.0000E-3      0.002          0.001         1000          0.5           0.5 ",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_zero_weather_header(path):
    lines = [
        "***STANDARD METEOROLOGICAL DATA  Header file for no-rain mode4 validation",
        "Latitude Longitude",
        " 39.02        -76.55 ",
        "^Daily Bulb T(1) ^ Daily Wind(2) ^RainIntensity(3) ^Daily Conc^(4) ,Furrow(5) ^Rel_humid(6) ^CO2(7)",
        " 0             0             0             0             0             0             0 ",
        "Parameters for changing of units: BSOLAR BTEMP ATEMP ERAIN BWIND BIR ",
        " BSOLAR is 1e6/3600 to go from j m-2 h-1 to wm-2",
        " 1000000       1             0             0.1           1             1 ",
        "Average values for the site",
        "wind    ChemConc     CO2  ",
        "8 0 380",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_zero_weather(path, final_date):
    rows = [
        "*** zero-weather mode4 point-source validation",
        " JDay   Date  Hour     Rad      Temper    rain     Wind   RH   CO2",
    ]
    current = INITIAL_DATE
    while current <= final_date:
        for hour in range(1, 25):
            rows.append(
                f" {current.timetuple().tm_yday} '{_fmt_date(current)}' {hour} 0 20 0 0 100 380"
            )
        current += timedelta(days=1)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_zero_management(path):
    lines = [
        "*** Script for management practices fertilizer, residue and tillage",
        "[N Fertilizer]",
        "****Script for chemical application module  *******mg/cm2",
        "Number of Fertilizer applications (max=25)",
        " 0",
        "tAppl(i)  AmtAppl(i) depth(i) lAppl_C(i) lAppl_N(i)  mAppl_C(i) mAppl_N(i)",
        "No fertilizer",
        "[Residue]",
        "****Script for residue/mulch application module",
        "**** Residue amount can be thickness ('t') or mass ('m')   ***",
        "application  1 or 0, 1(yes) 0(no)",
        "0",
        "[Tillage]",
        "1: Tillage , 0: No till",
        " 0",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_no_irrigation(path):
    lines = [
        "****Script for Irrigation",
        "[Sprinkler]",
        "Sprinkler irrigation",
        "Average irrigation rate (cm/hour)",
        " 0",
        "Number of irrigation application",
        " 0",
        "No Irrigation",
        "[Flood_H]",
        "Flood irrigation as depth of water (cm)",
        "Number of flood irrigations as head (cm)",
        " 0",
        "No flood Irrigation",
        "[Flood_R]",
        "Flood irrigation as rate applied (cm/day)",
        "Number of flood irrigations as rate",
        " 0",
        "No flood Irrigation",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_no_drip(path):
    lines = [
        "*****Script for Drip application module  ******* wAppl is cm water per hour at each source boundary",
        "Number of Drip irrigations(max=75)",
        " 0 ",
        "No drip irrigation",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_mode4_drip(path, scenario):
    lines = [
        "*****Script for Drip application module  ******* wAppl is cm water per hour at each source boundary",
        "Number of Drip irrigations(max=75)",
        " 1 ",
        "Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax DripSpreadMode DripSourceWidth",
        (
            f"'{_fmt_date(DRIP_START.date())}' {DRIP_START.hour:g} "
            f"'{_fmt_date(scenario.drip_stop.date())}' {scenario.drip_stop.hour:g} "
            f"{scenario.drip_rate_cm_h:g} 1 0 0 1 0 0 0 4 {scenario.source_width_cm:g}"
        ),
        "Drip application nodes",
        f" {SOURCE_NODE}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_g03(path):
    frame = pd.read_csv(path, skipinitialspace=True)
    frame = frame.rename(columns=lambda column: str(column).strip())
    required = {
        "date_time": _find_column(frame, "Date_time"),
        "date": _find_column(frame, "Date"),
        "x": _find_column(frame, "X"),
        "y": _find_column(frame, "Y"),
        "h": _find_column(frame, "hNew"),
        "theta": _find_column(frame, "thNew"),
        "area": _find_column(frame, "Area"),
    }
    missing = [name for name, column in required.items() if column is None]
    if missing:
        raise ValueError(f"G03 missing columns {missing}: {path}")
    data = pd.DataFrame(
        {
            name: (
                pd.to_datetime(frame[column], errors="coerce")
                if name == "date"
                else pd.to_numeric(frame[column], errors="coerce")
            )
            for name, column in required.items()
        }
    )
    data["date"] = data["date"].dt.normalize()
    if data.isna().any().any():
        raise ValueError(f"G03 contains invalid numeric/date values: {path}")
    if not np.isfinite(data[["date_time", "x", "y", "h", "theta", "area"]].to_numpy()).all():
        raise ValueError(f"G03 contains non-finite values: {path}")
    surface_y = float(data["y"].max())
    data["depth_cm"] = surface_y - data["y"]
    return data


def _active_application_width_mean(g05):
    width = g05.get("drip_surface_application_width_mean_cm")
    if width is None:
        return 0.0
    if "drip_input_mm" not in g05:
        return float(width.mean())
    active = g05.loc[g05["drip_input_mm"] > 1.0e-12, "drip_surface_application_width_mean_cm"]
    if active.empty:
        return 0.0
    return float(active.mean())


def _drip_balance(g05):
    input_mm = _column_sum(g05, "drip_input_mm")
    actual = _column_sum(g05, "drip_actual_infil_mm")
    storage_change = _column_sum(g05, "drip_surface_storage_change_mm")
    surface_runoff = _column_sum(g05, "drip_surface_runoff_mm")
    hydraulic_excess = _column_sum(g05, "drip_hydraulic_excess_mm")
    residual = input_mm - actual - storage_change - surface_runoff - hydraulic_excess
    return {
        "input": float(input_mm),
        "actual": float(actual),
        "storage_change": float(storage_change),
        "surface_runoff": float(surface_runoff),
        "hydraulic_excess": float(hydraulic_excess),
        "residual": float(residual),
        "storage_max": float(g05.get("drip_surface_storage_mm", pd.Series([0.0])).max()),
    }


def _g03_storage_balance(baseline_g03, drip_g03, baseline_g05, drip_g05, elapsed_h, grid_width_cm):
    baseline_frame = _frame_at_elapsed(baseline_g03, elapsed_h)
    drip_frame = _frame_at_elapsed(drip_g03, elapsed_h)
    g03_storage = _g03_storage_delta_mm(baseline_frame, drip_frame, grid_width_cm)
    baseline_g05_elapsed = _g05_through_elapsed(baseline_g05, elapsed_h)
    drip_g05_elapsed = _g05_through_elapsed(drip_g05, elapsed_h)
    drip_balance = _drip_balance(drip_g05_elapsed)
    drainage_delta = _column_sum(drip_g05_elapsed, "drainage_mm") - _column_sum(
        baseline_g05_elapsed,
        "drainage_mm",
    )
    total_infil_delta = _column_sum(drip_g05_elapsed, "infil_mm") - _column_sum(
        baseline_g05_elapsed,
        "infil_mm",
    )
    expected_storage = drip_balance["actual"] - drainage_delta
    return {
        "g03_storage_delta_mm": g03_storage,
        "g05_drip_input_mm": drip_balance["input"],
        "g05_drip_actual_infil_mm": drip_balance["actual"],
        "g05_drip_surface_storage_change_mm": drip_balance["storage_change"],
        "g05_drip_surface_runoff_mm": drip_balance["surface_runoff"],
        "g05_drip_hydraulic_excess_mm": drip_balance["hydraulic_excess"],
        "g05_drip_balance_residual_mm": drip_balance["residual"],
        "g05_total_infil_delta_mm": total_infil_delta,
        "g05_drainage_delta_mm": drainage_delta,
        "g05_expected_soil_storage_delta_mm": expected_storage,
        "g03_minus_g05_expected_storage_mm": g03_storage - expected_storage,
    }


def _g03_storage_delta_mm(baseline_frame, drip_frame, grid_width_cm):
    merged = drip_frame.merge(
        baseline_frame[["x", "y", "theta"]],
        on=["x", "y"],
        how="inner",
        suffixes=("", "_baseline"),
    )
    if len(merged) != len(drip_frame) or len(merged) != len(baseline_frame):
        raise ValueError("G03 storage frames do not contain the same grid nodes")
    storage_cm2_per_cm_row = (
        (merged["theta"] - merged["theta_baseline"]) * merged["area"]
    ).sum()
    return float(storage_cm2_per_cm_row / float(grid_width_cm) * 10.0)


def _g05_through_elapsed(g05, elapsed_h):
    target = _excel_serial(DRIP_START.date()) + elapsed_h / 24.0
    return g05.loc[g05["date_time"] <= target + FRAME_MATCH_ATOL_DAYS].copy()


def _column_sum(frame, column):
    if column not in frame:
        return 0.0
    return float(frame[column].sum())


def _safe_fraction(numerator, denominator):
    if abs(float(denominator)) < 1.0e-12:
        return 0.0
    return float(numerator) / float(denominator)


def _assert_g05_is_physical(g05, soil_name):
    finite = np.isfinite(g05.select_dtypes(include=[np.number]).to_numpy()).all()
    if not finite:
        raise ValueError(f"{soil_name}: G05 contains non-finite numeric values")
    nonnegative = [
        "drip_input_mm",
        "drip_demand_mm",
        "drip_actual_infil_mm",
        "drip_hydraulic_excess_mm",
        "drip_surface_runoff_mm",
        "drip_surface_storage_mm",
    ]
    for column in nonnegative:
        if column in g05 and float(g05[column].min()) < -1.0e-6:
            raise ValueError(f"{soil_name}: G05 {column} has nonphysical negative values")
    residual = abs(_drip_balance(g05)["residual"])
    if residual > 0.02:
        raise ValueError(f"{soil_name}: drip boundary balance residual is {residual:.6g} mm")


def _assert_theta_is_finite(g03, soil):
    theta = g03["theta"].to_numpy(dtype=float)
    if not np.isfinite(theta).all():
        raise ValueError(f"{soil.name}: non-finite theta in G03")
    if float(theta.min()) < soil.theta_r - 0.02:
        raise ValueError(f"{soil.name}: theta below residual-water tolerance")
    if float(theta.max()) > soil.theta_s + 0.02:
        raise ValueError(f"{soil.name}: theta above saturated-water tolerance")
    h = g03["h"].to_numpy(dtype=float)
    if not np.isfinite(h).all():
        raise ValueError(f"{soil.name}: non-finite pressure head in G03")


def _assert_no_failure_markers(run_dir):
    log_text = ""
    for name in ("stdout.txt", "stderr.txt"):
        path = run_dir / "logs" / name
        if path.exists():
            log_text += path.read_text(encoding="utf-8", errors="replace")
    lower = log_text.casefold()
    for marker in MODEL_FAILURE_MARKERS:
        if marker.casefold() in lower:
            raise RuntimeError(f"{run_dir.name}: failure marker in log: {marker}")


def _write_soil_figures(soil_name, baseline, drip, figures_root, scenario):
    figure_paths = []
    final_elapsed_h = scenario.figure_elapsed_hours[-1]
    theta_final = _frame_at_elapsed(drip, final_elapsed_h)
    elapsed_label = _elapsed_label(final_elapsed_h)
    half_path = figures_root / f"codex_{soil_name}_half_theta_{elapsed_label}.png"
    mirror_path = figures_root / f"codex_{soil_name}_mirrored_theta_{elapsed_label}.png"
    mirror_full_path = figures_root / f"codex_{soil_name}_mirrored_theta_{elapsed_label}_full_domain.png"
    _plot_field(
        theta_final,
        "theta",
        half_path,
        title=f"{soil_name} {scenario.name} half-domain theta, {elapsed_label}",
        mirrored=False,
        cmap="viridis",
    )
    _plot_field(
        theta_final,
        "theta",
        mirror_path,
        title=f"{soil_name} {scenario.name} mirrored theta, {elapsed_label}",
        mirrored=True,
        cmap="viridis",
        x_extent="zoom",
    )
    _plot_field(
        theta_final,
        "theta",
        mirror_full_path,
        title=f"{soil_name} {scenario.name} mirrored theta, {elapsed_label}, full horizontal domain",
        mirrored=True,
        cmap="viridis",
        x_extent="full",
    )
    figure_paths.extend([half_path, mirror_path, mirror_full_path])

    for elapsed_h in scenario.figure_elapsed_hours:
        elapsed_label = _elapsed_label(elapsed_h)
        delta = _delta_frame(baseline, drip, elapsed_h, scenario=scenario)
        delta_path = figures_root / f"codex_{soil_name}_mirrored_delta_{elapsed_label}.png"
        delta_full_path = figures_root / f"codex_{soil_name}_mirrored_delta_{elapsed_label}_full_domain.png"
        _plot_field(
            delta,
            "delta_theta",
            delta_path,
            title=f"{soil_name} {scenario.name} mirrored delta theta, {elapsed_label}, zoomed",
            mirrored=True,
            cmap="RdBu_r",
            delta=True,
            x_extent="zoom",
        )
        _plot_field(
            delta,
            "delta_theta",
            delta_full_path,
            title=f"{soil_name} {scenario.name} mirrored delta theta, {elapsed_label}, full horizontal domain",
            mirrored=True,
            cmap="RdBu_r",
            delta=True,
            x_extent="full",
        )
        figure_paths.extend([delta_path, delta_full_path])
    final_delta = _delta_frame(baseline, drip, final_elapsed_h, scenario=scenario)
    profile_path = figures_root / f"codex_{soil_name}_delta_profiles_{_elapsed_label(final_elapsed_h)}.png"
    _plot_delta_profiles(
        final_delta,
        profile_path,
        title=f"{soil_name} {scenario.name} delta theta profiles, {_elapsed_label(final_elapsed_h)}",
    )
    figure_paths.append(profile_path)
    return figure_paths


def _plot_field(frame, value_column, path, title, mirrored, cmap, delta=False, x_extent="zoom"):
    plot_frame = _mirror_frame(frame) if mirrored else frame.copy()
    x = plot_frame["x"].to_numpy(dtype=float)
    depth = plot_frame["depth_cm"].to_numpy(dtype=float)
    value = plot_frame[value_column].to_numpy(dtype=float)
    triangulation = mtri.Triangulation(x, depth)
    fig, ax = plt.subplots(figsize=(6.2, 4.2), constrained_layout=True)
    if delta:
        vmax = max(0.06, float(np.nanmax(np.abs(value))))
        levels = np.linspace(-vmax, vmax, 25)
        contour = ax.tricontourf(triangulation, value, levels=levels, cmap=cmap, extend="both")
        positive_max = float(np.nanmax(value))
        contour_levels = [level for level in DELTA_LEVELS if positive_max >= level]
        if contour_levels:
            lines = ax.tricontour(
                triangulation,
                value,
                levels=contour_levels,
                colors=("black", "dimgray")[: len(contour_levels)],
                linewidths=1.0,
            )
            ax.clabel(lines, fmt=lambda val: f"dtheta={val:.2f}", fontsize=7)
    else:
        contour = ax.tricontourf(triangulation, value, levels=24, cmap=cmap)
    ax.axvline(0.0, color="0.15", linewidth=0.8, linestyle="--")
    ax.plot([0.0], [0.0], marker="v", color="red", markersize=6)
    _set_plot_xlim(ax, plot_frame, mirrored=mirrored, x_extent=x_extent)
    ax.set_ylim(80, 0)
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("depth (cm)")
    ax.set_title(title)
    fig.colorbar(contour, ax=ax, label=value_column)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _set_plot_xlim(ax, plot_frame, mirrored, x_extent):
    if x_extent == "full":
        margin = max(1.0, 0.02 * float(plot_frame["x"].max() - plot_frame["x"].min()))
        ax.set_xlim(float(plot_frame["x"].min()) - margin, float(plot_frame["x"].max()) + margin)
    elif mirrored:
        ax.set_xlim(-20, 20)
    else:
        ax.set_xlim(0, 20)


def _write_delta_contact_sheets(records, figures_root, scenario):
    if not records:
        return []
    return [
        _write_delta_contact_sheet(records, figures_root, scenario, x_extent="zoom"),
        _write_delta_contact_sheet(records, figures_root, scenario, x_extent="full"),
    ]


def _write_delta_contact_sheet(records, figures_root, scenario, x_extent):
    soils = [soil.name for soil in SOILS]
    elapsed_values = list(scenario.figure_elapsed_hours)
    by_key = {
        (record["soil"], float(record["elapsed_h"])): record["delta"]
        for record in records
    }
    vmax = max(
        0.06,
        max(float(np.nanmax(np.abs(record["delta"]["delta_theta"]))) for record in records),
    )
    levels = np.linspace(-vmax, vmax, 25)
    fig, axes = plt.subplots(
        len(soils),
        len(elapsed_values),
        figsize=(4.0 * len(elapsed_values), 3.1 * len(soils)),
        constrained_layout=True,
        squeeze=False,
    )
    contour = None
    for row_index, soil_name in enumerate(soils):
        for column_index, elapsed_h in enumerate(elapsed_values):
            ax = axes[row_index, column_index]
            delta = by_key[(soil_name, float(elapsed_h))]
            plot_frame = _mirror_frame(delta)
            x = plot_frame["x"].to_numpy(dtype=float)
            depth = plot_frame["depth_cm"].to_numpy(dtype=float)
            value = plot_frame["delta_theta"].to_numpy(dtype=float)
            triangulation = mtri.Triangulation(x, depth)
            contour = ax.tricontourf(
                triangulation,
                value,
                levels=levels,
                cmap="RdBu_r",
                extend="both",
            )
            positive_max = float(np.nanmax(value))
            contour_levels = [level for level in DELTA_LEVELS if positive_max >= level]
            if contour_levels:
                lines = ax.tricontour(
                    triangulation,
                    value,
                    levels=contour_levels,
                    colors=("black", "dimgray")[: len(contour_levels)],
                    linewidths=0.8,
                )
                ax.clabel(lines, fmt=lambda val: f"dtheta={val:.2f}", fontsize=6)
            ax.axvline(0.0, color="0.15", linewidth=0.6, linestyle="--")
            ax.plot([0.0], [0.0], marker="v", color="red", markersize=4)
            _set_plot_xlim(ax, plot_frame, mirrored=True, x_extent=x_extent)
            ax.set_ylim(80, 0)
            ax.set_title(f"{soil_name}, {_elapsed_label(elapsed_h)}", fontsize=8)
            if row_index == len(soils) - 1:
                ax.set_xlabel("x (cm)")
            if column_index == 0:
                ax.set_ylabel("depth (cm)")
    label = "full_domain" if x_extent == "full" else "zoomed"
    fig.suptitle(f"{scenario.name} mirrored delta theta contact sheet, {label}")
    path = figures_root / f"codex_{scenario.name}_delta_contact_sheet_{label}.png"
    if contour is not None:
        fig.colorbar(contour, ax=axes.ravel().tolist(), label="delta_theta")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def _plot_delta_profiles(delta, path, title):
    vertical_x = float(delta.loc[delta["x"].abs().idxmin(), "x"])
    vertical = delta.loc[np.isclose(delta["x"], vertical_x, rtol=0.0, atol=1.0e-8)].copy()
    surface_depth = float(delta["depth_cm"].min())
    surface = delta.loc[
        np.isclose(delta["depth_cm"], surface_depth, rtol=0.0, atol=1.0e-8)
    ].copy()
    surface = _mirror_frame(surface)

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.6), constrained_layout=True)
    vertical = vertical.sort_values("depth_cm")
    axes[0].plot(vertical["delta_theta"], vertical["depth_cm"], color="tab:blue", linewidth=1.8)
    axes[0].axvline(0.0, color="0.25", linewidth=0.8, linestyle="--")
    axes[0].invert_yaxis()
    axes[0].set_xlabel("delta theta")
    axes[0].set_ylabel("depth (cm)")
    axes[0].set_title(f"x = {vertical_x:g} cm")

    surface = surface.sort_values("x")
    axes[1].plot(surface["x"], surface["delta_theta"], color="tab:orange", linewidth=1.8)
    axes[1].axvline(0.0, color="0.25", linewidth=0.8, linestyle="--")
    axes[1].axhline(0.0, color="0.25", linewidth=0.8, linestyle="--")
    axes[1].set_xlabel("x (cm)")
    axes[1].set_ylabel("delta theta")
    axes[1].set_title(f"depth = {surface_depth:g} cm")
    fig.suptitle(title)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _delta_frame(baseline, drip, elapsed_h, scenario=DEFAULT_SCENARIO):
    base_frame = _frame_at_elapsed(baseline, elapsed_h)
    drip_frame = _frame_at_elapsed(drip, elapsed_h)
    merged = drip_frame.merge(
        base_frame[["x", "y", "theta"]],
        on=["x", "y"],
        how="inner",
        suffixes=("", "_baseline"),
    )
    merged["delta_theta"] = merged["theta"] - merged["theta_baseline"]
    return merged


def _delta_shape_metrics(
    baseline,
    drip,
    elapsed_h,
    threshold,
    mirror,
    scenario=DEFAULT_SCENARIO,
    grid_width_cm=GRID_WIDTH_CM,
):
    delta = _delta_frame(baseline, drip, elapsed_h, scenario=scenario)
    peak = delta.loc[delta["delta_theta"].idxmax()]
    peak_x_cm = float(peak["x"])
    peak_depth_cm = float(peak["depth_cm"])
    if mirror:
        delta = _mirror_frame(delta)
    domain = _lateral_domain(delta, mirror=mirror, grid_width_cm=grid_width_cm)
    wet = delta[delta["delta_theta"] >= threshold]
    interpolated = _interpolated_wet_extent(delta, threshold)
    area_metrics = _wet_area_metrics(wet)
    boundary = _lateral_boundary_metrics(wet, domain)
    if wet.empty:
        return {
            "threshold": threshold,
            "wet_width_cm": 0.0,
            "wet_depth_cm": 0.0,
            "wet_width_interpolated_cm": 0.0,
            "wet_depth_interpolated_cm": 0.0,
            "delta_theta_max": float(delta["delta_theta"].max()),
            "peak_x_cm": peak_x_cm,
            "peak_depth_cm": peak_depth_cm,
            **area_metrics,
            **boundary,
        }
    return {
        "threshold": threshold,
        "wet_width_cm": float(wet["x"].max() - wet["x"].min()),
        "wet_depth_cm": float(wet["depth_cm"].max()),
        "wet_width_interpolated_cm": interpolated["wet_width_interpolated_cm"],
        "wet_depth_interpolated_cm": interpolated["wet_depth_interpolated_cm"],
        "delta_theta_max": float(delta["delta_theta"].max()),
        "peak_x_cm": peak_x_cm,
        "peak_depth_cm": peak_depth_cm,
        **area_metrics,
        **boundary,
    }


def _lateral_domain(delta, mirror, grid_width_cm):
    if mirror:
        half_width = max(float(grid_width_cm), float(delta["x"].abs().max()))
        return {"left": -half_width, "right": half_width}
    return {"left": float(delta["x"].min()), "right": float(delta["x"].max())}


def _lateral_boundary_metrics(wet, domain):
    if wet.empty:
        return {
            "touches_lateral_boundary": False,
            "touches_left_lateral_boundary": False,
            "touches_right_lateral_boundary": False,
        }
    tolerance = 1.0e-6
    touches_left = bool((wet["x"] <= domain["left"] + tolerance).any())
    touches_right = bool((wet["x"] >= domain["right"] - tolerance).any())
    return {
        "touches_lateral_boundary": touches_left or touches_right,
        "touches_left_lateral_boundary": touches_left,
        "touches_right_lateral_boundary": touches_right,
    }


def _wet_area_metrics(wet):
    if wet.empty:
        return {
            "wet_node_area_cm2_per_cm_row": 0.0,
            "wet_centroid_x_cm": np.nan,
            "wet_centroid_depth_cm": np.nan,
            "wet_x_second_moment_cm2": np.nan,
            "wet_depth_second_moment_cm2": np.nan,
        }
    weights = wet["area"].to_numpy(dtype=float)
    total_area = float(weights.sum())
    x = wet["x"].to_numpy(dtype=float)
    depth = wet["depth_cm"].to_numpy(dtype=float)
    centroid_x = float(np.average(x, weights=weights))
    centroid_depth = float(np.average(depth, weights=weights))
    return {
        "wet_node_area_cm2_per_cm_row": total_area,
        "wet_centroid_x_cm": centroid_x,
        "wet_centroid_depth_cm": centroid_depth,
        "wet_x_second_moment_cm2": float(np.average((x - centroid_x) ** 2, weights=weights)),
        "wet_depth_second_moment_cm2": float(
            np.average((depth - centroid_depth) ** 2, weights=weights)
        ),
    }


def _interpolated_wet_extent(delta, threshold):
    grid = delta.pivot_table(
        index="depth_cm",
        columns="x",
        values="delta_theta",
        aggfunc="mean",
    ).sort_index().sort_index(axis=1)
    x_values = np.asarray(grid.columns, dtype=float)
    depth_values = np.asarray(grid.index, dtype=float)
    values = grid.to_numpy(dtype=float)
    x_hits = _threshold_hits_along_axis(x_values, values, threshold)
    depth_hits = _threshold_hits_along_axis(depth_values, values.T, threshold)
    width = float(max(x_hits) - min(x_hits)) if x_hits else 0.0
    depth = float(max(depth_hits)) if depth_hits else 0.0
    return {
        "wet_width_interpolated_cm": width,
        "wet_depth_interpolated_cm": depth,
    }


def _threshold_hits_along_axis(coordinates, value_rows, threshold):
    hits = []
    for row in value_rows:
        finite = np.isfinite(row)
        if not finite.any():
            continue
        row = row[finite]
        coords = coordinates[finite]
        hits.extend(float(coord) for coord, value in zip(coords, row) if value >= threshold)
        for left_index in range(len(coords) - 1):
            left_value = row[left_index]
            right_value = row[left_index + 1]
            left_offset = left_value - threshold
            right_offset = right_value - threshold
            if left_offset == 0.0 or right_offset == 0.0:
                continue
            if left_offset * right_offset < 0.0:
                fraction = (threshold - left_value) / (right_value - left_value)
                hits.append(
                    float(coords[left_index] + fraction * (coords[left_index + 1] - coords[left_index]))
                )
    return hits


def _frame_at_elapsed(frame, elapsed_h):
    target = _excel_serial(DRIP_START.date()) + elapsed_h / 24.0
    times = np.asarray(sorted(frame["date_time"].unique()), dtype=float)
    selected = float(times[np.argmin(np.abs(times - target))])
    if abs(selected - target) > MAX_FRAME_OFFSET_DAYS:
        raise ValueError(f"No G03 frame near elapsed {elapsed_h:g} h; nearest Date_time={selected:g}")
    matches = np.isclose(
        frame["date_time"].to_numpy(dtype=float),
        selected,
        rtol=0.0,
        atol=FRAME_MATCH_ATOL_DAYS,
    )
    return frame.loc[matches].copy()


def _mirror_frame(frame):
    original = frame.copy()
    mirrored = original.loc[original["x"].abs() > 1.0e-9].copy()
    mirrored["x"] = -mirrored["x"]
    return pd.concat([mirrored, original], ignore_index=True)


def _write_manifest(path, output_root, summary_path, shapes_path, storage_path, figure_paths, scenario):
    manifest = {
        "workspace": str(output_root),
        "mode": "DripSpreadMode=4 surface point source",
        "half_domain": True,
        "symmetry_axis_x_cm": 0.0,
        "flow_conversion": {
            "grid_input_mm": (
                "rate_cm_h * drip_duration_h * source_width_cm / grid_width_cm * 10"
            ),
            "line_source_flux_l_h_m_half_domain": "rate_cm_h * source_width_cm / 10",
            "line_source_flux_l_h_m_mirrored": (
                "2 * rate_cm_h * source_width_cm / 10 for x=0 symmetry-axis runs"
            ),
            "emitter_flow_l_h": (
                "line_source_flux_l_h_m_mirrored * emitter_spacing_m; "
                f"default spacing in summaries is {DEFAULT_EMITTER_SPACING_M:g} m"
            ),
        },
        "scenario": scenario.name,
        "source_node": SOURCE_NODE,
        "source_width_cm": scenario.source_width_cm,
        "drip_rate_cm_h": scenario.drip_rate_cm_h,
        "drip_duration_h": scenario.drip_duration_h,
        "final_elapsed_h": scenario.final_elapsed_h,
        "local_applied_depth_cm": scenario.local_applied_depth_cm,
        "applied_water_cross_section_cm2_per_cm_row": (
            scenario.applied_water_cross_section_cm2_per_cm_row
        ),
        "source_area_cm2_per_cm_row": scenario.source_area_cm2_per_cm_row,
        "expected_grid_input_mm": _grid_input_mm(
            scenario.drip_rate_cm_h,
            scenario.source_width_cm,
            scenario.drip_duration_h,
        ),
        "line_source_flux_l_h_m_half_domain": _line_source_flux_l_h_m(
            scenario.drip_rate_cm_h,
            scenario.source_width_cm,
            mirrored=False,
        ),
        "line_source_flux_l_h_m_mirrored": _line_source_flux_l_h_m(
            scenario.drip_rate_cm_h,
            scenario.source_width_cm,
            mirrored=True,
        ),
        "drip_start": DRIP_START.isoformat(),
        "drip_stop": scenario.drip_stop.isoformat(),
        "figure_elapsed_hours": list(scenario.figure_elapsed_hours),
        "delta_levels": list(scenario.delta_levels),
        "grid_refinement": (
            "Base LOAM2D half-domain grid; first surface boundary width is "
            "0.38 cm and shallow vertical spacing starts at 0.05 cm near the emitter."
        ),
        "field_notes": {
            "DripSourceWidth": (
                "MAIZSIM half-domain source width for x=0 symmetry-axis runs; "
                "mirrored physical contact width is 2 * DripSourceWidth."
            ),
            "drip_surface_application_width_max_cm": (
                "G05 surface application width, not the G03 wetted-body width."
            ),
            "wet_width_interpolated_cm": (
                "G03 delta-theta wetted-body width estimated by linear threshold interpolation."
            ),
            "touches_lateral_boundary": (
                "True when thresholded G03 wetted nodes reach the mirrored lateral domain edge."
            ),
        },
        "summary_csv": str(summary_path),
        "shape_metrics_csv": str(shapes_path),
        "g03_storage_balance_csv": str(storage_path),
        "figures": [str(path) for path in figure_paths],
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_matrix_manifest(
    path,
    output_root,
    matrix_name,
    scenarios,
    summary_path,
    shapes_path,
    storage_path,
    figure_paths,
    scenario_outputs,
):
    manifest = {
        "workspace": str(output_root),
        "matrix_name": matrix_name,
        "purpose": (
            "Mode4 non-HYDRUS checks for rate sensitivity, total-water sensitivity, "
            "source-width sensitivity, post-irrigation redistribution, and grid sensitivity."
        ),
        "scenarios": [_scenario_manifest_row(scenario) for scenario in scenarios],
        "scenario_outputs": scenario_outputs,
        "field_notes": {
            "DripSourceWidth": (
                "MAIZSIM half-domain source width for x=0 symmetry-axis runs; "
                "mirrored physical contact width is 2 * DripSourceWidth."
            ),
            "drip_surface_application_width_mean_cm": (
                "Mean G05 application width over active drip-input rows only."
            ),
            "drip_surface_application_width_mean_all_rows_cm": (
                "Compatibility diagnostic showing the all-row mean, including zero-input rows."
            ),
            "drip_wet_width_max_cm": (
                "Legacy alias for G05 application width; do not interpret as G03 wetted-body width."
            ),
            "wet_width_interpolated_cm": (
                "G03 delta-theta wetted-body width estimated by linear threshold interpolation."
            ),
            "touches_lateral_boundary": (
                "True when thresholded G03 wetted nodes reach the mirrored lateral domain edge."
            ),
        },
        "summary_csv": str(summary_path),
        "shape_metrics_csv": str(shapes_path),
        "g03_storage_balance_csv": str(storage_path),
        "figures": [str(path) for path in figure_paths],
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _scenario_manifest_row(scenario):
    return {
        "name": scenario.name,
        "scenario_group": scenario.scenario_group,
        "drip_rate_cm_h": scenario.drip_rate_cm_h,
        "source_width_cm": scenario.source_width_cm,
        "drip_duration_h": scenario.drip_duration_h,
        "final_elapsed_h": scenario.final_elapsed_h,
        "target_grid_input_mm": scenario.target_grid_input_mm,
        "expected_grid_input_mm": _grid_input_mm(
            scenario.drip_rate_cm_h,
            scenario.source_width_cm,
            scenario.drip_duration_h,
        ),
        "local_applied_depth_cm": scenario.local_applied_depth_cm,
        "applied_water_cross_section_cm2_per_cm_row": (
            scenario.applied_water_cross_section_cm2_per_cm_row
        ),
        "source_area_cm2_per_cm_row": scenario.source_area_cm2_per_cm_row,
        "line_source_flux_l_h_m_half_domain": _line_source_flux_l_h_m(
            scenario.drip_rate_cm_h,
            scenario.source_width_cm,
            mirrored=False,
        ),
        "line_source_flux_l_h_m_mirrored": _line_source_flux_l_h_m(
            scenario.drip_rate_cm_h,
            scenario.source_width_cm,
            mirrored=True,
        ),
        "emitter_flow_l_h_at_0p3m_spacing": _emitter_flow_l_h(
            scenario.drip_rate_cm_h,
            scenario.source_width_cm,
            DEFAULT_EMITTER_SPACING_M,
            mirrored=True,
        ),
        "grid_refinement_factor": scenario.grid_refinement_factor,
        "figure_elapsed_hours": list(scenario.figure_elapsed_hours),
        "delta_levels": list(scenario.delta_levels),
    }


def _elapsed_label(elapsed_h):
    if float(elapsed_h).is_integer():
        return f"{int(elapsed_h)}h"
    return f"{elapsed_h:g}h".replace(".", "p")


def _find_column(frame, required):
    key = _normalize(required)
    for column in frame.columns:
        if _normalize(column) == key:
            return column
    return None


def _find_output_file(run_dir, suffix):
    suffix_key = suffix.casefold()
    if not suffix_key.startswith("."):
        suffix_key = f".{suffix_key}"
    candidates = [
        path
        for path in Path(run_dir).iterdir()
        if path.is_file() and path.suffix.casefold() == suffix_key
    ]
    if not candidates:
        raise FileNotFoundError(f"No output file with suffix {suffix!r} in {run_dir}")
    return sorted(candidates, key=lambda path: path.name.casefold())[0]


def _normalize(value):
    return "".join(str(value).strip().casefold().split()).replace("_", "")


def _fmt_date(value):
    return f"{value.month:02d}/{value.day:02d}/{value.year}"


def _excel_serial(value):
    return float((value - date(1899, 12, 30)).days)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="HDD codex workspace for generated cases and figures.")
    parser.add_argument("--executable-dir", default=str(BUILD_OUTPUT), help="Directory containing Release x64 exe and DLL.")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--scenario-set",
        choices=("current", "supplemental", "systematic", "enhanced"),
        default="current",
        help=(
            "Run only the current smoke-test scenario, the supplemental diagnostic "
            "matrix, the non-HYDRUS systematic validation matrix, or the "
            "Pro-review enhanced follow-up matrix."
        ),
    )
    args = parser.parse_args(argv)
    if args.scenario_set == "enhanced":
        result = run_enhanced_validation(
            args.workspace,
            executable_dir=args.executable_dir,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.scenario_set == "systematic":
        result = run_systematic_validation(
            args.workspace,
            executable_dir=args.executable_dir,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.scenario_set == "supplemental":
        result = run_supplemental_validation(
            args.workspace,
            executable_dir=args.executable_dir,
            timeout_seconds=args.timeout_seconds,
        )
    else:
        result = run_validation(
            args.workspace,
            executable_dir=args.executable_dir,
            timeout_seconds=args.timeout_seconds,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
