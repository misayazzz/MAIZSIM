"""Executable Mode 6 validation for one emitter in the MAIZSIM half-domain."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import pandas as pd

from .drip_regression import DEFAULT_SOILS
from .drip_regression import grid_surface_widths
from .hutd06_grid_refinement import EMITTER_X_CM
from .hutd06_grid_refinement import REFINED_X_MAX_CM
from .hutd06_grid_refinement import REFINED_Y_MIN_CM
from .hutd06_grid_refinement import refine_hutd06_grid
from .model_runner import check_required_outputs
from .model_runner import run_model


BASE_RUN_RELATIVE = Path("DA_Framework") / "base_runs" / "HUTD06"
EXECUTABLE_RELATIVE = Path("build") / "maizsim" / "x64" / "Release"
RUN_FILE = "run.dat"
MODEL_PREFIX = "HUTD06"
EVENT_START = pd.Timestamp("2006-04-01")
FINAL_DATE = pd.Timestamp("2006-04-04")
DEFAULT_EMITTER_NODE = 1
DEFAULT_DEPTH_MM = 30.0
DEFAULT_DURATION_H = 24.0
DEFAULT_EMITTER_SPACING_CM = 30.0
DEFAULT_CONTACT_WIDTH_CM = 2.0
DEFAULT_DOMAIN_WIDTH_CM = 37.5
DEFAULT_REFINED_X_MAX_CM = REFINED_X_MAX_CM
DEFAULT_REFINED_Y_MIN_CM = REFINED_Y_MIN_CM
DEFAULT_DTMX_DAYS = 0.001
DEFAULT_WATER_MAX_ITERATIONS = 200
DEFAULT_WATER_THETA_TOLERANCE = 0.0001
DEFAULT_WATER_HEAD_TOLERANCE_CM = 0.005
WETTING_THRESHOLD = 0.005
REQUIRED_OUTPUTS = (".G03", ".G05")
WATER_BALANCE_OUTPUT = "WaterMassBalance.out"
WATER_BALANCE_RELATIVE_TOLERANCE_PCT = 0.1
WATER_BALANCE_ABSOLUTE_TOLERANCE_MM = 0.05
WATER_BALANCE_MAX_STEP_TOLERANCE_MM = 0.005
GCI_ASYMPTOTIC_RATIO_LIMITS = (0.9, 1.1)


def run_mode6_30mm_validation(
    *,
    repo_root,
    workspace,
    executable_dir=None,
    emitter_node=None,
    irrigation_depth_mm=DEFAULT_DEPTH_MM,
    duration_h=DEFAULT_DURATION_H,
    emitter_spacing_cm=DEFAULT_EMITTER_SPACING_CM,
    contact_width_cm=DEFAULT_CONTACT_WIDTH_CM,
    domain_width_cm=DEFAULT_DOMAIN_WIDTH_CM,
    refined_x_max_cm=DEFAULT_REFINED_X_MAX_CM,
    refined_y_min_cm=DEFAULT_REFINED_Y_MIN_CM,
    dtmx_days=DEFAULT_DTMX_DAYS,
    grid_level=0,
    soil_names=None,
    timeout_seconds=600,
):
    """Run baseline and Mode 6 cases for loam, sandy loam, and clay loam."""
    repo = Path(repo_root).expanduser().resolve()
    work_root = Path(workspace).expanduser().resolve()
    base_run = repo / BASE_RUN_RELATIVE
    exe_dir = (
        Path(executable_dir).expanduser().resolve()
        if executable_dir is not None
        else repo / EXECUTABLE_RELATIVE
    )
    _require_file(base_run / RUN_FILE)
    _require_file(exe_dir / "2dMAIZSIM.exe")
    _require_file(exe_dir / "Maizsim.dll")
    if irrigation_depth_mm <= 0.0:
        raise ValueError("irrigation_depth_mm must be positive")
    if duration_h <= 0.0:
        raise ValueError("duration_h must be positive")
    if EVENT_START + pd.Timedelta(hours=float(duration_h)) > FINAL_DATE:
        raise ValueError("duration_h extends the drip event beyond the run")
    if emitter_spacing_cm <= 0.0:
        raise ValueError("emitter_spacing_cm must be positive")
    if contact_width_cm <= 0.0:
        raise ValueError("contact_width_cm must be positive")
    if domain_width_cm <= 0.0:
        raise ValueError("domain_width_cm must be positive")
    if dtmx_days <= 0.0:
        raise ValueError("dtmx_days must be positive")
    if int(grid_level) not in (0, 1, 2):
        raise ValueError("grid_level must be 0, 1, or 2")
    soils = _select_soils(soil_names)

    work_root.mkdir(parents=True, exist_ok=True)
    base_widths, base_domain_width = grid_surface_widths(
        base_run / "HUTD06.grd"
    )
    base_emitter_nodes = [
        node
        for node in base_widths
        if abs(_grid_node_x(base_run / "HUTD06.grd", node) - EMITTER_X_CM)
        <= 1.0e-12
    ]
    if len(base_emitter_nodes) != 1:
        raise ValueError("HUTD06 must contain exactly one x=0 cm surface node")
    if float(domain_width_cm) < float(base_domain_width) - 1.0e-12:
        raise ValueError("Validation domain cannot be narrower than base HUTD06")

    depth_cm = float(irrigation_depth_mm) / 10.0
    emitter_flow_lph = (
        2.0
        * float(emitter_spacing_cm)
        * depth_cm
        * float(domain_width_cm)
        / (1000.0 * float(duration_h))
    )
    rows = []
    run_dirs = {}
    grid_metadata = None
    for soil in soils:
        for treatment in ("baseline", "mode6_30mm"):
            case_dir = work_root / f"codex_{soil.name}__hutd06__{treatment}"
            case_grid_metadata = _prepare_case(
                base_run=base_run,
                executable_dir=exe_dir,
                run_dir=case_dir,
                soil=soil,
                emitter_node=(
                    int(emitter_node) if emitter_node is not None else None
                ),
                emitter_flow_lph=(
                    emitter_flow_lph if treatment == "mode6_30mm" else 0.0
                ),
                emitter_spacing_cm=emitter_spacing_cm,
                contact_width_cm=contact_width_cm,
                duration_h=duration_h,
                dtmx_days=dtmx_days,
                grid_level=int(grid_level),
                domain_width_cm=float(domain_width_cm),
                refined_x_max_cm=float(refined_x_max_cm),
                refined_y_min_cm=float(refined_y_min_cm),
            )
            if grid_metadata is None:
                grid_metadata = case_grid_metadata
            elif case_grid_metadata != grid_metadata:
                raise AssertionError("Grid metadata changed between validation cases")
            if abs(
                float(case_grid_metadata["domain_width_cm"])
                - float(domain_width_cm)
            ) > 1.0e-10:
                raise AssertionError("Generated grid width differs from requested width")
            result = run_model(
                case_dir,
                executable="2dMAIZSIM.exe",
                run_file=RUN_FILE,
                timeout_seconds=timeout_seconds,
            )
            if not result.success:
                raise RuntimeError(f"{case_dir.name}: {result.message}")
            check_required_outputs(case_dir, REQUIRED_OUTPUTS)
            _require_final_date(case_dir / "HUTD06.G05")
            _require_final_date(case_dir / WATER_BALANCE_OUTPUT)
            run_dirs[(soil.name, treatment)] = case_dir

        row = _case_metrics(
            soil.name,
            run_dirs[(soil.name, "baseline")],
            run_dirs[(soil.name, "mode6_30mm")],
            emitter_x_cm=float(grid_metadata["emitter_x_cm"]),
            expected_depth_mm=float(irrigation_depth_mm),
            domain_width_cm=float(grid_metadata["domain_width_cm"]),
            contact_width_cm=float(contact_width_cm),
            refinement_bounds=(
                0.0,
                float(grid_metadata["actual_refined_x_max_cm"]),
                float(grid_metadata["actual_refined_y_min_cm"]),
                float(grid_metadata["surface_y_cm"]),
            ),
            wetting_evaluation_time=(
                EVENT_START + pd.Timedelta(hours=float(duration_h))
            ),
        )
        rows.append(row)

    frame = pd.DataFrame(rows)
    _validate_results(frame, expected_depth_mm=float(irrigation_depth_mm))
    csv_path = work_root / "codex_mode6_30mm_summary.csv"
    json_path = work_root / "codex_mode6_30mm_summary.json"
    frame.to_csv(csv_path, index=False)
    summary = {
        "status": "pass",
        "mode": 6,
        "fallback_mode": None,
        "soils": [soil.name for soil in soils],
        "soil_hydraulic_parameters": {
            soil.name: {
                "thr": float(soil.thr),
                "ths": float(soil.ths),
                "tha": float(soil.tha),
                "thm": float(soil.thm),
                "alpha_per_cm": float(soil.alpha),
                "n": float(soil.n),
                "ks_cm_per_day": float(soil.ks),
                "kk_cm_per_day": float(soil.kk),
                "thk": float(soil.thk),
            }
            for soil in soils
        },
        "near_saturation_bridge": {
            "conductivity_ratio_kk_over_ks": 0.9,
            "water_content_offset_ths_minus_thk": 0.004,
            "basis": "existing_HUTD06_material_parameterization",
        },
        "emitter_count": 1,
        "computational_source_count": 1,
        "emitter_node": int(grid_metadata["emitter_node"]),
        "emitter_x_cm": float(grid_metadata["emitter_x_cm"]),
        "domain_geometry": "2d_cartesian_vertical_half_domain",
        "source_geometry": "fixed_surface_contact_on_x0_half_domain_axis",
        "irrigation_basis": "emitter_flow_and_spacing_to_half_line_supply",
        "requested_section_volume_cm2": depth_cm * float(domain_width_cm),
        "out_of_plane_representative_length_cm": None,
        "direct_point_emitter_rate_l_h_comparison_supported": False,
        "domain_width_cm": float(grid_metadata["domain_width_cm"]),
        "irrigation_depth_mm": float(irrigation_depth_mm),
        "duration_h": float(duration_h),
        "emitter_flow_lph": emitter_flow_lph,
        "emitter_spacing_cm": float(emitter_spacing_cm),
        "contact_width_cm": float(contact_width_cm),
        "dtmx_days": float(dtmx_days),
        "grid": grid_metadata,
        "results": frame.to_dict(orient="records"),
        "csv": str(csv_path),
    }
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary["json"] = str(json_path)
    return summary


def _prepare_case(
    *,
    base_run,
    executable_dir,
    run_dir,
    soil,
    emitter_node,
    emitter_flow_lph,
    emitter_spacing_cm,
    contact_width_cm,
    duration_h,
    dtmx_days,
    grid_level=0,
    domain_width_cm=None,
    refined_x_max_cm=REFINED_X_MAX_CM,
    refined_y_min_cm=REFINED_Y_MIN_CM,
):
    """Create one self-contained HUTD06 hydraulic validation case."""
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(
        base_run,
        run_dir,
        ignore=shutil.ignore_patterns(
            "logs",
            "*.out",
            "*.g0*",
            "*.G0*",
        ),
    )
    shutil.copy2(executable_dir / "2dMAIZSIM.exe", run_dir / "2dMAIZSIM.exe")
    shutil.copy2(executable_dir / "Maizsim.dll", run_dir / "Maizsim.dll")
    grid_metadata = refine_hutd06_grid(
        run_dir / "HUTD06.grd",
        run_dir / "HUTD06.nod",
        run_dir / "HUTD06.grd",
        run_dir / "HUTD06.nod",
        level=grid_level,
        domain_width_cm=domain_width_cm,
        refined_x_max_cm=refined_x_max_cm,
        refined_y_min_cm=refined_y_min_cm,
    )
    case_emitter_node = int(grid_metadata["emitter_node"])
    if emitter_node is not None and int(emitter_node) != case_emitter_node:
        raise ValueError(
            "Emitter node is determined by physical x=0 cm on the generated "
            f"grid ({case_emitter_node})"
        )
    _write_mass_balance_file(run_dir / "MassBl.dat")
    _write_homogeneous_soil(run_dir / "HUTD06.soi", soil, material_count=7)
    _write_time_file(run_dir / "HUTD06.tim")
    _write_drip_file(
        run_dir / "HUTD06.drp",
        emitter_node=case_emitter_node,
        emitter_flow_lph=emitter_flow_lph,
        emitter_spacing_cm=emitter_spacing_cm,
        contact_width_cm=contact_width_cm,
        duration_h=duration_h,
    )
    _set_water_solver_controls(
        run_dir / "WaterMovDefault.dat",
        max_iterations=DEFAULT_WATER_MAX_ITERATIONS,
        theta_tolerance=DEFAULT_WATER_THETA_TOLERANCE,
        head_tolerance_cm=DEFAULT_WATER_HEAD_TOLERANCE_CM,
        dtmx_days=dtmx_days,
    )
    return grid_metadata


def _write_mass_balance_file(path):
    lines = [
        "*** MASS BALANCE PRINT DATES",
        "Number of print dates",
        "0",
        "Dates",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _set_water_solver_controls(
    path,
    *,
    max_iterations,
    theta_tolerance,
    head_tolerance_cm,
    dtmx_days,
):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if len(lines) < 3:
        raise ValueError(f"Invalid water-mover parameter file: {path}")
    values = lines[2].split()
    if len(values) < 10:
        raise ValueError(f"Invalid water-mover parameter row: {path}")
    values[0] = str(int(max_iterations))
    values[1] = f"{float(theta_tolerance):.10g}"
    values[2] = f"{float(head_tolerance_cm):.10g}"
    values[5] = f"{float(dtmx_days):.10g}"
    lines[2] = " ".join(values)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_homogeneous_soil(path, soil, material_count):
    if not 0.0 < float(soil.kk) < float(soil.ks):
        raise ValueError(
            f"{soil.name}: Mode 6 validation requires 0 < Kk < Ks "
            "for the MAIZSIM near-saturation conductivity bridge"
        )
    if not float(soil.tha) < float(soil.thk) < float(soil.ths):
        raise ValueError(
            f"{soil.name}: Mode 6 validation requires tha < thk < ths "
            "for the MAIZSIM near-saturation conductivity bridge"
        )
    header = [
        "           *** Material information ****",
        (
            "   thr       ths         tha       thm      Alfa      n        "
            "Ks         Kk       thk       BulkD     OM    Sand    Silt   "
            "InitType"
        ),
    ]
    row = (
        f" {soil.thr:.3f}\t {soil.ths:.3f}\t {soil.tha:.3f}\t "
        f"{soil.thm:.3f}\t {soil.alpha:.5f}\t {soil.n:.5f}\t "
        f"{soil.ks:.3f}\t {soil.kk:.3f}\t {soil.thk:.3f}\t "
        f"{soil.bulk_density:.3f}\t {soil.organic_matter:.4f}\t "
        f"{soil.sand:.2f}\t {soil.silt:.2f}\t '{soil.init_type}'"
    )
    Path(path).write_text(
        "\n".join(header + [row] * int(material_count)) + "\n",
        encoding="utf-8",
    )


def _write_time_file(path):
    lines = [
        "*** SYNCHRONIZER INFORMATION *****************************",
        "Initial time       dt       dtMin     DMul1    DMul2    tFin",
        "'03/31/2006' 0.0001 0.0000001 1.3 0.3 '04/04/2006'",
        "Output variables, 1 if true  Daily    Hourly",
        " 0             1",
        "Daily Hourly Weather data frequency",
        " 1             0",
        "RunToEnd",
        " 0",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_drip_file(
    path,
    *,
    emitter_node,
    emitter_flow_lph,
    emitter_spacing_cm,
    contact_width_cm,
    duration_h,
):
    if emitter_flow_lph <= 0.0:
        lines = [
            "***** Fixed-contact half-domain drip validation",
            "Number of Drip irrigations(max=75)",
            " 0",
            "No drip irrigation",
        ]
    else:
        event_stop = EVENT_START + pd.Timedelta(hours=float(duration_h))
        start_date, start_hour = _fortran_event_time(EVENT_START)
        stop_date, stop_hour = _fortran_event_time(event_stop)
        lines = [
            "***** Fixed-contact half-domain drip validation",
            "Number of Drip irrigations(max=75)",
            " 1",
            (
                "Start_Date Start_hour Stop_Date Stop_hour EmitterFlowLph "
                "EmitterSpacingCm ContactWidthCm Num_nodes"
            ),
            (
                f"{start_date} {start_hour:.10g} "
                f"{stop_date} {stop_hour:.10g} {emitter_flow_lph:.10g} "
                f"{emitter_spacing_cm:.10g} {contact_width_cm:.10g} 1"
            ),
            "Drip application nodes",
            f" {int(emitter_node)}",
        ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fortran_event_time(timestamp):
    instant = pd.Timestamp(timestamp)
    hour = (
        instant.hour
        + instant.minute / 60.0
        + instant.second / 3600.0
        + instant.microsecond / 3.6e9
    )
    return f"'{instant:%m/%d/%Y}'", hour


def _case_metrics(
    soil,
    baseline_dir,
    drip_dir,
    *,
    emitter_x_cm,
    expected_depth_mm,
    domain_width_cm,
    contact_width_cm,
    refinement_bounds,
    wetting_evaluation_time,
):
    g05 = _read_csv(drip_dir / "HUTD06.G05")
    numeric = (
        "DripEmitterInput_mm",
        "SeasDrip_mm",
        "DripActualInfil_mm",
        "DripPondingChange_mm",
        "DripOverflow_mm",
        "DripPonded_mm",
        "DripLedgerClosure_mm",
        "DripContactWidth_cm",
        "DripContactMeasure_cm",
        "DripContactNodes",
        "DripPondingCapacity_mm",
        "DripMode6Available_mm",
        "DripMode6Accepted_mm",
        "DripMode6Remaining_mm",
        "DripMode6ClosureResidual",
        "DripMode6SolverLimit",
        "DripMode6BoundaryLimit",
        "DripMode6StepCuts",
        "DripMode6NonlinearCuts",
        "DripMode6SupplyCuts",
        "DripMode6MassCuts",
        "DripMode6MinDtDays",
    )
    for column in numeric:
        if column not in g05:
            raise ValueError(f"Missing G05 Mode 6 column: {column}")
        g05[column] = pd.to_numeric(g05[column], errors="raise")
    active = g05[g05["DripMode6Available_mm"] > 1.0e-10]
    shape = _wetting_shape(
        baseline_dir / "HUTD06.G03",
        drip_dir / "HUTD06.G03",
        emitter_x_cm=emitter_x_cm,
        refinement_bounds=refinement_bounds,
        evaluation_time=wetting_evaluation_time,
    )
    min_dt = active.loc[
        active["DripMode6MinDtDays"] > 0.0,
        "DripMode6MinDtDays",
    ]
    step_cuts = float(g05["DripMode6StepCuts"].sum())
    nonlinear_step_cuts = float(g05["DripMode6NonlinearCuts"].sum())
    supply_step_cuts = float(g05["DripMode6SupplyCuts"].sum())
    mass_step_cuts = float(g05["DripMode6MassCuts"].sum())
    categorized_step_cuts = (
        nonlinear_step_cuts + supply_step_cuts + mass_step_cuts
    )
    return {
        "soil": soil,
        "requested_input_mm": expected_depth_mm,
        "delivered_input_mm": float(g05["SeasDrip_mm"].iloc[-1]),
        "input_mm": float(g05["DripEmitterInput_mm"].sum()),
        "actual_infiltration_mm": float(g05["DripActualInfil_mm"].sum()),
        "ponding_change_mm": float(g05["DripPondingChange_mm"].sum()),
        "overflow_mm": float(g05["DripOverflow_mm"].sum()),
        "final_ponding_mm": float(g05["DripPonded_mm"].iloc[-1]),
        "mode6_accepted_mm": float(g05["DripMode6Accepted_mm"].sum()),
        "mode6_remaining_mm": float(g05["DripMode6Remaining_mm"].sum()),
        "contact_width_cm": float(
            g05["DripContactWidth_cm"].max()
        ),
        "contact_measure_cm": float(
            g05["DripContactMeasure_cm"].max()
        ),
        "contact_nodes": int(g05["DripContactNodes"].max()),
        "ponding_capacity_mm": float(
            g05["DripPondingCapacity_mm"].max()
        ),
        "delivery_error_mm": (
            float(g05["SeasDrip_mm"].iloc[-1]) - expected_depth_mm
        ),
        "emitter_input_error_mm": (
            float(g05["DripEmitterInput_mm"].sum())
            - float(g05["SeasDrip_mm"].iloc[-1])
        ),
        "accepted_actual_error_mm": (
            float(g05["DripMode6Accepted_mm"].sum())
            - float(g05["DripActualInfil_mm"].sum())
        ),
        "terminal_ledger_error_mm": (
            float(g05["DripEmitterInput_mm"].sum())
            - float(g05["DripActualInfil_mm"].sum())
            - float(g05["DripOverflow_mm"].sum())
            - float(g05["DripPonded_mm"].iloc[-1])
        ),
        "contact_width_error_cm": (
            float(g05["DripContactWidth_cm"].max()) - contact_width_cm
        ),
        "contact_measure_error_cm": (
            float(g05["DripContactMeasure_cm"].max()) - contact_width_cm
        ),
        "ledger_closure_abs_max_mm": float(
            g05["DripLedgerClosure_mm"].abs().max()
        ),
        "mode6_closure_abs_max_mm": float(
            g05["DripMode6ClosureResidual"].abs().max()
        ),
        "solver_limit_max": float(g05["DripMode6SolverLimit"].max()),
        "boundary_limit_max": float(g05["DripMode6BoundaryLimit"].max()),
        "step_cuts": step_cuts,
        "nonlinear_step_cuts": nonlinear_step_cuts,
        "supply_step_cuts": supply_step_cuts,
        "mass_step_cuts": mass_step_cuts,
        "uncategorized_step_cuts": step_cuts - categorized_step_cuts,
        "min_dt_days": float(min_dt.min()) if not min_dt.empty else 0.0,
        "active_contact_width_max_cm": float(
            active["DripContactMeasure_cm"].max()
        ),
        **_water_balance_metrics(
            baseline_dir / WATER_BALANCE_OUTPUT,
            prefix="baseline",
            domain_width_cm=domain_width_cm,
        ),
        **_water_balance_metrics(
            drip_dir / WATER_BALANCE_OUTPUT,
            prefix="mode6",
            domain_width_cm=domain_width_cm,
        ),
        **shape,
    }


def _wetting_shape(
    baseline_path,
    drip_path,
    *,
    emitter_x_cm,
    threshold=WETTING_THRESHOLD,
    refinement_bounds=None,
    evaluation_time=None,
):
    """Return piecewise-linear wetting geometry at one matched G03 time."""
    baseline = _g03_at_time(baseline_path, evaluation_time=evaluation_time)
    drip = _g03_at_time(drip_path, evaluation_time=evaluation_time)
    merged = drip.merge(
        baseline[["X", "Y", "thNew"]],
        on=["X", "Y"],
        suffixes=("_drip", "_base"),
        validate="one_to_one",
    )
    merged["delta_theta"] = merged["thNew_drip"] - merged["thNew_base"]
    merged["depth_cm"] = float(merged["Y"].max()) - merged["Y"]
    if refinement_bounds is None:
        refinement_bounds = (
            EMITTER_X_CM,
            REFINED_X_MAX_CM,
            REFINED_Y_MIN_CM,
            float(merged["Y"].max()),
        )
    geometry = wetting_geometry_from_field(
        merged[["X", "Y", "delta_theta"]],
        threshold=threshold,
        refinement_bounds=refinement_bounds,
    )
    peak = merged.loc[merged["delta_theta"].idxmax()]
    return {
        "wetting_evaluation_time": (
            pd.Timestamp(evaluation_time).isoformat()
            if evaluation_time is not None
            else "final_output"
        ),
        "delta_theta_max": float(peak["delta_theta"]),
        "peak_x_cm": float(peak["X"]),
        "peak_depth_cm": float(peak["depth_cm"]),
        "peak_offset_from_emitter_cm": abs(float(peak["X"]) - emitter_x_cm),
        **half_domain_mirror_metrics(
            merged[["X", "Y", "delta_theta"]]
        ),
        **geometry,
    }


def half_domain_mirror_metrics(field):
    """Reconstruct the x<0 field and verify the half-domain mirror invariant."""
    required = {"X", "Y", "delta_theta"}
    missing = sorted(required.difference(field.columns))
    if missing:
        raise ValueError(
            "Mirror field is missing column(s): " + ", ".join(missing)
        )
    values = field.loc[:, ["X", "Y", "delta_theta"]].copy()
    for column in values.columns:
        values[column] = pd.to_numeric(values[column], errors="raise")
    if not all(math.isfinite(value) for value in values.to_numpy().ravel()):
        raise ValueError("Mirror field values must be finite")
    x_values = sorted(float(value) for value in values["X"].unique())
    y_values = sorted(
        (float(value) for value in values["Y"].unique()), reverse=True
    )
    if not x_values or abs(x_values[0]) > 1.0e-12:
        raise ValueError("Half-domain mirror field must start at x=0")
    if len(x_values) < 2 or len(y_values) < 2:
        raise ValueError("Half-domain mirror field must contain a 2D grid")
    if len(values) != len(x_values) * len(y_values):
        raise ValueError("Half-domain mirror field must be rectangular")
    if values.duplicated(["X", "Y"]).any():
        raise ValueError("Half-domain mirror field coordinates must be unique")

    mirrored = pd.concat(
        [
            values.loc[values["X"] > 0.0].assign(
                X=lambda item: -item["X"]
            ),
            values,
        ],
        ignore_index=True,
    )
    half_storage = _structured_field_integral(values)
    full_storage = _structured_field_integral(mirrored)
    expected_full = 2.0 * half_storage
    scale = max(1.0, abs(expected_full))
    mirror_error = abs(full_storage - expected_full)
    if mirror_error > 1.0e-12 * scale:
        raise AssertionError("Mirrored full-domain storage is not twice the half-domain")
    positive = values.loc[values["X"] > 0.0].copy()
    negative = mirrored.loc[mirrored["X"] < 0.0].copy()
    negative["X"] = -negative["X"]
    pairs = positive.merge(
        negative,
        on=["X", "Y"],
        suffixes=("_positive", "_negative"),
        validate="one_to_one",
    )
    pair_error = float(
        (
            pairs["delta_theta_positive"]
            - pairs["delta_theta_negative"]
        )
        .abs()
        .max()
    )
    return {
        "half_domain_delta_storage_cm2": float(half_storage),
        "mirrored_full_delta_storage_cm2": float(full_storage),
        "mirror_volume_ratio": (
            float(full_storage / half_storage)
            if abs(half_storage) > 1.0e-15
            else 2.0
        ),
        "mirror_pair_abs_max": pair_error,
    }


def _structured_field_integral(field):
    x_values = sorted(float(value) for value in field["X"].unique())
    y_values = sorted(
        (float(value) for value in field["Y"].unique()), reverse=True
    )
    x_weights = _trapezoidal_control_weights(x_values)
    y_weights = _trapezoidal_control_weights(y_values)
    lookup = field.set_index(["X", "Y"])["delta_theta"]
    return sum(
        float(lookup.loc[(x_value, y_value)])
        * x_weights[x_index]
        * y_weights[y_index]
        for x_index, x_value in enumerate(x_values)
        for y_index, y_value in enumerate(y_values)
    )


def _trapezoidal_control_weights(coordinates):
    values = [float(value) for value in coordinates]
    return [
        (
            0.5 * abs(values[1] - values[0])
            if index == 0
            else 0.5 * abs(values[-1] - values[-2])
            if index == len(values) - 1
            else 0.5 * abs(values[index + 1] - values[index - 1])
        )
        for index in range(len(values))
    ]


def wetting_geometry_from_field(
    field,
    *,
    threshold=WETTING_THRESHOLD,
    refinement_bounds=None,
):
    """Measure a structured field using linear triangles and edge crossings.

    Each quadrilateral is split from its top-left to bottom-right node, matching
    the HUTD06 element ordering used by the Fortran area calculation.
    """
    required = {"X", "Y", "delta_theta"}
    missing = sorted(required.difference(field.columns))
    if missing:
        raise ValueError(
            "Wetting field is missing column(s): " + ", ".join(missing)
        )
    threshold = float(threshold)
    if not math.isfinite(threshold):
        raise ValueError("Wetting threshold must be finite")
    records = []
    for row in field.loc[:, ["X", "Y", "delta_theta"]].itertuples(index=False):
        x_value = float(row.X)
        y_value = float(row.Y)
        delta_theta = float(row.delta_theta)
        if not all(
            math.isfinite(value) for value in (x_value, y_value, delta_theta)
        ):
            raise ValueError("Wetting field contains non-finite values")
        records.append((x_value, y_value, delta_theta))
    if not records:
        raise ValueError("Wetting field is empty")
    coordinates = [(x_value, y_value) for x_value, y_value, _ in records]
    if len(set(coordinates)) != len(coordinates):
        raise ValueError("Wetting field contains duplicate coordinates")

    x_values = sorted({x_value for x_value, _, _ in records})
    y_values = sorted(
        {y_value for _, y_value, _ in records},
        reverse=True,
    )
    if len(x_values) < 2 or len(y_values) < 2:
        raise ValueError("Wetting geometry needs at least a 2 x 2 node field")
    if len(records) != len(x_values) * len(y_values):
        raise ValueError("Wetting field is not a complete structured grid")
    values = {
        (x_value, y_value): delta_theta
        for x_value, y_value, delta_theta in records
    }

    wet_polygons = []
    wet_area = 0.0
    domain_scale = max(
        1.0,
        x_values[-1] - x_values[0],
        y_values[0] - y_values[-1],
    )
    coordinate_tolerance = 1.0e-10 * domain_scale
    area_tolerance = coordinate_tolerance * coordinate_tolerance
    for top, bottom in zip(y_values[:-1], y_values[1:]):
        for left, right in zip(x_values[:-1], x_values[1:]):
            top_left = (left, top)
            bottom_left = (left, bottom)
            bottom_right = (right, bottom)
            top_right = (right, top)
            triangles = (
                (top_left, bottom_left, bottom_right),
                (top_left, bottom_right, top_right),
            )
            for triangle in triangles:
                polygon = _clip_triangle_above_threshold(
                    triangle,
                    [values[point] for point in triangle],
                    threshold,
                    coordinate_tolerance,
                )
                area = _polygon_area(polygon)
                if area > area_tolerance:
                    wet_polygons.append(polygon)
                    wet_area += area

    domain_bounds = (
        x_values[0],
        x_values[-1],
        y_values[-1],
        y_values[0],
    )
    touches = _boundary_touch_flags(
        wet_polygons,
        domain_bounds,
        coordinate_tolerance,
        prefix="physical",
    )
    axis_touch = touches["physical_x_min"]
    outer_touch = touches["physical_x_max"]
    bottom_touch = touches["physical_y_min"]
    surface_touch = touches["physical_y_max"]
    output = {
        "wetting_threshold": threshold,
        "wetting_area_cm2": float(wet_area),
        "wetting_touches_axis_boundary": axis_touch,
        "wetting_touches_outer_boundary": outer_touch,
        "wetting_touches_bottom_boundary": bottom_touch,
        "wetting_touches_surface_boundary": surface_touch,
        "wetting_touches_physical_boundary": any(touches.values()),
        # The source is expected to touch the surface.  The x-min edge is the
        # crop-row symmetry plane of the HUTD06 half-domain.  Record both
        # contacts, but only the remote lateral edge or bottom truncates the
        # reconstructed physical wetting body.
        "wetting_censored_physical_boundary": (
            outer_touch or bottom_touch
        ),
    }
    if wet_polygons:
        wet_points = [
            point for polygon in wet_polygons for point in polygon
        ]
        wet_x = [point[0] for point in wet_points]
        wet_y = [point[1] for point in wet_points]
        output["wetting_width_cm"] = float(max(wet_x) - min(wet_x))
        output["wetting_depth_cm"] = float(y_values[0] - min(wet_y))
    else:
        output["wetting_width_cm"] = 0.0
        output["wetting_depth_cm"] = 0.0

    if refinement_bounds is None:
        refinement_flags = {
            "refinement_x_min": False,
            "refinement_x_max": False,
            "refinement_y_min": False,
            "refinement_y_max": False,
        }
    else:
        refinement_bounds = tuple(float(value) for value in refinement_bounds)
        if len(refinement_bounds) != 4:
            raise ValueError(
                "refinement_bounds must be (x_min, x_max, y_min, y_max)"
            )
        _validate_bounds(refinement_bounds, domain_bounds)
        refinement_flags = _boundary_touch_flags(
            wet_polygons,
            refinement_bounds,
            coordinate_tolerance,
            prefix="refinement",
        )
    output.update(
        {
            "wetting_touches_refinement_x_min": refinement_flags[
                "refinement_x_min"
            ],
            "wetting_touches_refinement_x_max": refinement_flags[
                "refinement_x_max"
            ],
            "wetting_touches_refinement_y_min": refinement_flags[
                "refinement_y_min"
            ],
            "wetting_touches_refinement_y_max": refinement_flags[
                "refinement_y_max"
            ],
            "wetting_touches_refinement_boundary": any(
                refinement_flags.values()
            ),
            # x_min is the fixed emitter-side edge and y_max is the source
            # surface. The outward and lower edges are the truncation checks.
            "wetting_censored_refinement_boundary": (
                refinement_flags["refinement_x_max"]
                or refinement_flags["refinement_y_min"]
            ),
        }
    )
    return output


def three_grid_gci(
    coarse,
    medium,
    fine,
    *,
    refinement_ratio=2.0,
    safety_factor=1.25,
    asymptotic_ratio_limits=GCI_ASYMPTOTIC_RATIO_LIMITS,
    absolute_tolerance=1.0e-12,
    relative_tolerance=1.0e-10,
):
    """Return a guarded three-grid GCI result for one scalar metric.

    A GCI is only returned for monotonic convergence with positive apparent
    order and an asymptotic-ratio check inside the requested limits.
    """
    values = tuple(float(value) for value in (coarse, medium, fine))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("GCI values must be finite")
    ratio = float(refinement_ratio)
    if not math.isfinite(ratio) or ratio <= 1.0:
        raise ValueError("refinement_ratio must be finite and greater than 1")
    safety = float(safety_factor)
    if not math.isfinite(safety) or safety <= 0.0:
        raise ValueError("safety_factor must be finite and positive")
    lower, upper = (float(value) for value in asymptotic_ratio_limits)
    if not all(math.isfinite(value) for value in (lower, upper)):
        raise ValueError("asymptotic_ratio_limits must be finite")
    if not (0.0 < lower < upper):
        raise ValueError(
            "asymptotic_ratio_limits must be positive and increasing"
        )
    absolute_tolerance = float(absolute_tolerance)
    relative_tolerance = float(relative_tolerance)
    if (
        not math.isfinite(absolute_tolerance)
        or not math.isfinite(relative_tolerance)
        or absolute_tolerance < 0.0
        or relative_tolerance < 0.0
    ):
        raise ValueError("GCI tolerances must be finite and nonnegative")
    scale = max(1.0, *(abs(value) for value in values))
    tolerance = absolute_tolerance + relative_tolerance * scale
    epsilon_32 = values[0] - values[1]
    epsilon_21 = values[1] - values[2]
    base = {
        "coarse": values[0],
        "medium": values[1],
        "fine": values[2],
        "refinement_ratio": ratio,
        "epsilon_32": epsilon_32,
        "epsilon_21": epsilon_21,
        "monotonic": False,
        "asymptotic": False,
        "valid": False,
        "apparent_order": None,
        "asymptotic_ratio": None,
        "gci_21": None,
        "gci_32": None,
        "gci_fine_pct": None,
    }
    if abs(epsilon_32) <= tolerance and abs(epsilon_21) <= tolerance:
        return {
            **base,
            "status": "resolved_to_tolerance",
            "monotonic": True,
            "asymptotic": True,
            "valid": True,
            "gci_21": 0.0,
            "gci_32": 0.0,
            "gci_fine_pct": 0.0,
        }
    if abs(epsilon_32) <= tolerance or abs(epsilon_21) <= tolerance:
        return {**base, "status": "stagnated"}
    if epsilon_32 * epsilon_21 <= 0.0:
        return {**base, "status": "non_monotonic"}

    apparent_order = math.log(abs(epsilon_32 / epsilon_21)) / math.log(ratio)
    base["monotonic"] = True
    base["apparent_order"] = apparent_order
    # Equal successive changes imply p approximately zero and an unbounded
    # Richardson denominator; do not label floating-point roundoff as an
    # asymptotic convergence order.
    if not math.isfinite(apparent_order) or apparent_order <= 1.0e-6:
        return {**base, "status": "non_asymptotic_order"}
    if abs(values[2]) <= tolerance or abs(values[1]) <= tolerance:
        return {**base, "status": "near_zero_reference"}

    try:
        ratio_power = ratio**apparent_order
    except OverflowError:
        return {**base, "status": "non_asymptotic_order"}
    denominator = ratio_power - 1.0
    if not math.isfinite(denominator) or denominator <= 0.0:
        return {**base, "status": "non_asymptotic_order"}
    provisional_gci_21 = (
        safety * abs(epsilon_21 / values[2]) / denominator
    )
    provisional_gci_32 = (
        safety * abs(epsilon_32 / values[1]) / denominator
    )
    asymptotic_ratio = provisional_gci_32 / (
        ratio_power * provisional_gci_21
    )
    base["asymptotic_ratio"] = asymptotic_ratio
    if (
        not math.isfinite(asymptotic_ratio)
        or asymptotic_ratio < lower
        or asymptotic_ratio > upper
    ):
        return {**base, "status": "non_asymptotic_ratio"}
    return {
        **base,
        "status": "pass",
        "asymptotic": True,
        "valid": True,
        "gci_21": provisional_gci_21,
        "gci_32": provisional_gci_32,
        "gci_fine_pct": 100.0 * provisional_gci_21,
    }


def _clip_triangle_above_threshold(
    points,
    values,
    threshold,
    tolerance,
):
    vertices = [
        (float(point[0]), float(point[1]), float(value))
        for point, value in zip(points, values)
    ]
    clipped = []
    previous = vertices[-1]
    previous_inside = previous[2] >= threshold
    for current in vertices:
        current_inside = current[2] >= threshold
        if current_inside != previous_inside:
            denominator = current[2] - previous[2]
            if denominator != 0.0:
                fraction = (threshold - previous[2]) / denominator
                fraction = min(1.0, max(0.0, fraction))
                clipped.append(
                    (
                        previous[0] + fraction * (current[0] - previous[0]),
                        previous[1] + fraction * (current[1] - previous[1]),
                    )
                )
        if current_inside:
            clipped.append((current[0], current[1]))
        previous = current
        previous_inside = current_inside
    return _deduplicate_polygon(clipped, tolerance)


def _deduplicate_polygon(points, tolerance):
    unique = []
    for point in points:
        if not unique or not _points_close(point, unique[-1], tolerance):
            unique.append(point)
    if len(unique) > 1 and _points_close(unique[0], unique[-1], tolerance):
        unique.pop()
    return unique


def _points_close(first, second, tolerance):
    return (
        abs(first[0] - second[0]) <= tolerance
        and abs(first[1] - second[1]) <= tolerance
    )


def _polygon_area(polygon):
    if len(polygon) < 3:
        return 0.0
    doubled_area = 0.0
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        doubled_area += first[0] * second[1] - second[0] * first[1]
    return 0.5 * abs(doubled_area)


def _validate_bounds(bounds, domain_bounds):
    x_min, x_max, y_min, y_max = bounds
    domain_x_min, domain_x_max, domain_y_min, domain_y_max = domain_bounds
    if not all(math.isfinite(value) for value in bounds):
        raise ValueError("Refinement bounds must be finite")
    if not (x_min < x_max and y_min < y_max):
        raise ValueError("Refinement bounds must have positive width and height")
    if (
        x_min < domain_x_min
        or x_max > domain_x_max
        or y_min < domain_y_min
        or y_max > domain_y_max
    ):
        raise ValueError("Refinement bounds must lie inside the physical domain")


def _boundary_touch_flags(polygons, bounds, tolerance, *, prefix):
    x_min, x_max, y_min, y_max = bounds
    return {
        f"{prefix}_x_min": any(
            _polygon_intersects_vertical_segment(
                polygon,
                x_min,
                y_min,
                y_max,
                tolerance,
            )
            for polygon in polygons
        ),
        f"{prefix}_x_max": any(
            _polygon_intersects_vertical_segment(
                polygon,
                x_max,
                y_min,
                y_max,
                tolerance,
            )
            for polygon in polygons
        ),
        f"{prefix}_y_min": any(
            _polygon_intersects_horizontal_segment(
                polygon,
                y_min,
                x_min,
                x_max,
                tolerance,
            )
            for polygon in polygons
        ),
        f"{prefix}_y_max": any(
            _polygon_intersects_horizontal_segment(
                polygon,
                y_max,
                x_min,
                x_max,
                tolerance,
            )
            for polygon in polygons
        ),
    }


def _polygon_intersects_vertical_segment(
    polygon,
    x_value,
    y_min,
    y_max,
    tolerance,
):
    intersections = []
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        if abs(first[0] - x_value) <= tolerance:
            intersections.append(first[1])
        if abs(second[0] - first[0]) <= tolerance:
            continue
        fraction = (x_value - first[0]) / (second[0] - first[0])
        if -tolerance <= fraction <= 1.0 + tolerance:
            intersections.append(
                first[1] + fraction * (second[1] - first[1])
            )
    return any(
        y_min - tolerance <= value <= y_max + tolerance
        for value in intersections
    )


def _polygon_intersects_horizontal_segment(
    polygon,
    y_value,
    x_min,
    x_max,
    tolerance,
):
    intersections = []
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        if abs(first[1] - y_value) <= tolerance:
            intersections.append(first[0])
        if abs(second[1] - first[1]) <= tolerance:
            continue
        fraction = (y_value - first[1]) / (second[1] - first[1])
        if -tolerance <= fraction <= 1.0 + tolerance:
            intersections.append(
                first[0] + fraction * (second[0] - first[0])
            )
    return any(
        x_min - tolerance <= value <= x_max + tolerance
        for value in intersections
    )


def _g03_at_time(path, *, evaluation_time=None):
    frame = _read_csv(path)
    for column in ("Date_time", "X", "Y", "thNew"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    available = tuple(float(value) for value in frame["Date_time"].unique())
    if not available:
        raise ValueError(f"Empty G03 output: {path}")
    if evaluation_time is None:
        selected = max(available)
    else:
        epoch = pd.Timestamp("1899-12-30")
        target = (
            pd.Timestamp(evaluation_time) - epoch
        ).total_seconds() / 86400.0
        selected = min(available, key=lambda value: abs(value - target))
        if abs(selected - target) > 5.0e-6:
            raise ValueError(
                f"G03 output {path} has no state at requested time "
                f"{pd.Timestamp(evaluation_time).isoformat()}; nearest "
                f"Date_time is {selected:.9f}"
            )
    return frame[frame["Date_time"] == selected].copy()


def _water_balance_metrics(path, *, prefix, domain_width_cm):
    frame = _read_csv(path)
    numeric = (
        "Date_time",
        "Storage_cm2",
        "DeltaStorage_cm2",
        "CumulativeIn_cm2",
        "CumulativeOut_cm2",
        "CumulativeSink_cm2",
        "Residual_cm2",
        "RelativeError_pct",
        "MaxStepResidual_cm2",
        "AcceptedSteps",
    )
    for column in numeric:
        if column not in frame:
            raise ValueError(f"Missing water-balance column: {column}")
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame.empty:
        raise ValueError(f"Empty water-balance output: {path}")
    final = frame.loc[frame["Date_time"].idxmax()]
    mm_per_cm2 = 10.0 / float(domain_width_cm)
    return {
        f"{prefix}_water_balance_residual_mm": (
            float(final["Residual_cm2"]) * mm_per_cm2
        ),
        f"{prefix}_water_balance_relative_error_pct": float(
            final["RelativeError_pct"]
        ),
        f"{prefix}_water_balance_max_step_residual_mm": (
            float(final["MaxStepResidual_cm2"]) * mm_per_cm2
        ),
        f"{prefix}_water_balance_accepted_steps": int(final["AcceptedSteps"]),
    }


def _read_csv(path):
    # Legacy Fortran records end with a delimiter while the header does not.
    # Disabling implicit index inference keeps Date_time and Date aligned.
    frame = pd.read_csv(path, skipinitialspace=True, index_col=False)
    frame = frame.rename(columns=lambda column: str(column).strip().strip(","))
    return frame.dropna(how="all")


def _require_final_date(path):
    frame = _read_csv(path)
    dates = pd.to_datetime(frame["Date"].astype(str).str.strip(), errors="coerce")
    if dates.isna().all() or dates.max().normalize() < FINAL_DATE:
        raise RuntimeError(f"Model stopped before {FINAL_DATE.date()}: {path}")


def _validate_results(frame, *, expected_depth_mm):
    tolerance_mm = max(0.01, 0.001 * expected_depth_mm)
    failures = []
    for row in frame.to_dict(orient="records"):
        soil = row["soil"]
        checks = (
            (
                abs(row["delivered_input_mm"] - expected_depth_mm)
                <= tolerance_mm,
                "requested delivery",
            ),
            (
                abs(row["emitter_input_error_mm"]) <= tolerance_mm,
                "emitter input accounting",
            ),
            (
                abs(row["accepted_actual_error_mm"]) <= tolerance_mm,
                "accepted/actual closure",
            ),
            (
                abs(row["terminal_ledger_error_mm"]) <= tolerance_mm,
                "terminal ponding/overflow ledger",
            ),
            (
                row["mode6_closure_abs_max_mm"] <= tolerance_mm,
                "Mode 6 closure",
            ),
            (
                row["ledger_closure_abs_max_mm"] <= tolerance_mm,
                "local ponding ledger closure",
            ),
            (
                abs(row["contact_width_error_cm"]) <= 1.0e-10
                and abs(row["contact_measure_error_cm"]) <= 1.0e-10,
                "fixed physical contact measure",
            ),
            (row["contact_nodes"] >= 1, "contact node count"),
            (row["solver_limit_max"] == 0.0, "solver limit"),
            (row["boundary_limit_max"] == 0.0, "boundary limit"),
            (
                abs(row["uncategorized_step_cuts"]) <= 0.5,
                "classified step cuts",
            ),
            (
                abs(row["baseline_water_balance_residual_mm"])
                <= WATER_BALANCE_ABSOLUTE_TOLERANCE_MM,
                "baseline full-domain water balance",
            ),
            (
                row["baseline_water_balance_max_step_residual_mm"]
                <= WATER_BALANCE_MAX_STEP_TOLERANCE_MM,
                "baseline maximum step water balance",
            ),
            (
                abs(row["mode6_water_balance_residual_mm"])
                <= WATER_BALANCE_ABSOLUTE_TOLERANCE_MM
                and row["mode6_water_balance_relative_error_pct"]
                <= WATER_BALANCE_RELATIVE_TOLERANCE_PCT,
                "Mode 6 full-domain water balance",
            ),
            (
                row["mode6_water_balance_max_step_residual_mm"]
                <= WATER_BALANCE_MAX_STEP_TOLERANCE_MM,
                "Mode 6 maximum step water balance",
            ),
            (row["delta_theta_max"] > WETTING_THRESHOLD, "wetting response"),
            (row["wetting_depth_cm"] > 0.0, "wetting depth"),
            (
                abs(row["mirror_volume_ratio"] - 2.0) <= 1.0e-12
                and row["mirror_pair_abs_max"] <= 1.0e-12,
                "half-domain mirror invariant",
            ),
        )
        failures.extend(
            f"{soil}: failed {label}" for passed, label in checks if not passed
        )
    if failures:
        raise AssertionError("\n".join(failures))


def _grid_node_x(path, node_id):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    node_header = next(
        index
        for index, line in enumerate(lines)
        if "MatNum" in line and "x" in line
    )
    for line in lines[node_header + 1 :]:
        parts = line.split()
        if len(parts) < 4 or not parts[0].isdigit():
            break
        if int(parts[0]) == int(node_id):
            return float(parts[1])
    raise ValueError(f"Node {node_id} not found in {path}")


def _require_file(path):
    if not Path(path).is_file():
        raise FileNotFoundError(path)


def _select_soils(soil_names):
    if soil_names is None:
        return DEFAULT_SOILS
    requested = tuple(soil_names)
    if not requested:
        raise ValueError("soil_names must contain at least one soil")
    available = {soil.name: soil for soil in DEFAULT_SOILS}
    unknown = [name for name in requested if name not in available]
    if unknown:
        raise ValueError(
            "Unknown soil name(s): "
            + ", ".join(unknown)
            + ". Available: "
            + ", ".join(available)
        )
    if len(set(requested)) != len(requested):
        raise ValueError("soil_names must not contain duplicates")
    return tuple(available[name] for name in requested)


def _parse_args(arguments=None):
    parser = argparse.ArgumentParser(
        description="Validate one-emitter Mode 6 at 30 mm in three soils.",
    )
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[2])
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable-dir")
    parser.add_argument(
        "--emitter-node",
        type=int,
        help=(
            "Optional assertion for the generated x=0 cm surface-node "
            "number; normally derived from the grid"
        ),
    )
    parser.add_argument("--irrigation-depth-mm", type=float, default=DEFAULT_DEPTH_MM)
    parser.add_argument("--duration-h", type=float, default=DEFAULT_DURATION_H)
    parser.add_argument(
        "--emitter-spacing-cm",
        type=float,
        default=DEFAULT_EMITTER_SPACING_CM,
    )
    parser.add_argument(
        "--contact-width-cm",
        type=float,
        default=DEFAULT_CONTACT_WIDTH_CM,
    )
    parser.add_argument(
        "--domain-width-cm",
        type=float,
        default=DEFAULT_DOMAIN_WIDTH_CM,
    )
    parser.add_argument(
        "--refined-x-max-cm",
        type=float,
        default=DEFAULT_REFINED_X_MAX_CM,
    )
    parser.add_argument(
        "--refined-y-min-cm",
        type=float,
        default=DEFAULT_REFINED_Y_MIN_CM,
    )
    parser.add_argument("--dtmx-days", type=float, default=DEFAULT_DTMX_DAYS)
    parser.add_argument("--grid-level", type=int, choices=(0, 1, 2), default=0)
    parser.add_argument(
        "--soil",
        dest="soil_names",
        action="append",
        choices=tuple(soil.name for soil in DEFAULT_SOILS),
        help="Run only this soil; repeat the option to select several soils.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=600)
    return parser.parse_args(arguments)


def main(arguments=None):
    args = _parse_args(arguments)
    summary = run_mode6_30mm_validation(
        repo_root=args.repo_root,
        workspace=args.workspace,
        executable_dir=args.executable_dir,
        emitter_node=args.emitter_node,
        irrigation_depth_mm=args.irrigation_depth_mm,
        duration_h=args.duration_h,
        emitter_spacing_cm=args.emitter_spacing_cm,
        contact_width_cm=args.contact_width_cm,
        domain_width_cm=args.domain_width_cm,
        refined_x_max_cm=args.refined_x_max_cm,
        refined_y_min_cm=args.refined_y_min_cm,
        dtmx_days=args.dtmx_days,
        grid_level=args.grid_level,
        soil_names=args.soil_names,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
