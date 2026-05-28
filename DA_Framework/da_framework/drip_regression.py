"""Long-run drip-irrigation regression matrix for MAIZSIM."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .drip_validation import parse_drip_file
from .hydrus_drip_calibration import calibrated_drip_wet_width_max_cm
from .hydrus_drip_calibration import drip_wet_width_calibration_source
from .model_runner import check_required_outputs, run_model


RUN_FILE = "run.dat"
EXECUTABLE_NAME = "2dMAIZSIM.exe"
DLL_NAME = "Maizsim.dll"
BASE_RUN_RELATIVE = Path("DA_Framework") / "base_runs" / "SingleLayerLoam2D"
REQUIRED_OUTPUTS = (".G03", ".G04", ".G05")


@dataclass(frozen=True)
class SoilVariant:
    """One homogeneous soil-material row for the single-layer base run."""

    name: str
    thr: float
    ths: float
    tha: float
    thm: float
    alpha: float
    n: float
    ks: float
    kk: float
    thk: float
    bulk_density: float
    organic_matter: float
    sand: float
    silt: float
    init_type: str = "m"


@dataclass(frozen=True)
class GridVariant:
    """A proportional x-direction grid scaling variant."""

    name: str
    x_scale: float


@dataclass(frozen=True)
class DripScenario:
    """A drip schedule used across every soil-grid combination."""

    name: str
    event_line: str
    node_line: str
    pressure_reference: str | None = None


@dataclass(frozen=True)
class RegressionCase:
    """One model run in the regression matrix."""

    name: str
    soil: SoilVariant
    grid: GridVariant
    scenario: DripScenario | None
    run_dir: Path


@dataclass(frozen=True)
class CaseMetrics:
    """Validated output metrics for one completed run."""

    name: str
    success: bool
    drip_sum_mm: float
    final_seas_drip_mm: float
    cumrain_sum_mm: float
    infil_sum_mm: float
    runoff_sum_mm: float
    drainage_sum_mm: float
    expected_drip_mm: float
    drip_demand_sum_mm: float
    drip_pressure_loss_sum_mm: float
    drip_hydraulic_excess_sum_mm: float
    drip_actual_infil_sum_mm: float
    drip_source_input_sum_mm: float
    drip_source_loss_sum_mm: float
    demand_input_pressure_residual_mm: float
    input_source_residual_mm: float
    input_acceptance_residual_mm: float
    drip_wet_nodes_mean: float
    drip_wet_nodes_max: float
    drip_wet_width_mean_cm: float
    drip_wet_width_max_cm: float
    drip_wet_width_limit_cm: float
    drip_pressure_factor_mean: float
    drip_pressure_factor_min: float


DEFAULT_SOILS = (
    SoilVariant(
        name="loam",
        thr=0.078,
        ths=0.430,
        tha=0.078,
        thm=0.430,
        alpha=0.036,
        n=1.560,
        ks=30.0,
        kk=30.0,
        thk=0.430,
        bulk_density=1.400,
        organic_matter=0.0025,
        sand=0.43,
        silt=0.39,
    ),
    SoilVariant(
        name="sandy_loam",
        thr=0.045,
        ths=0.410,
        tha=0.045,
        thm=0.410,
        alpha=0.075,
        n=1.890,
        ks=106.1,
        kk=106.1,
        thk=0.410,
        bulk_density=1.550,
        organic_matter=0.0020,
        sand=0.65,
        silt=0.25,
    ),
    SoilVariant(
        name="clay_loam",
        thr=0.095,
        ths=0.410,
        tha=0.095,
        thm=0.410,
        alpha=0.019,
        n=1.310,
        ks=6.24,
        kk=6.24,
        thk=0.410,
        bulk_density=1.300,
        organic_matter=0.0030,
        sand=0.30,
        silt=0.34,
    ),
)

DEFAULT_GRIDS = (
    GridVariant(name="narrow_x075", x_scale=0.75),
    GridVariant(name="base_x100", x_scale=1.00),
    GridVariant(name="wide_x125", x_scale=1.25),
)

REGRESSION_WATER_DTMX_DAYS = 0.005

DEFAULT_SCENARIOS = (
    DripScenario(
        name="long_low_single",
        event_line=(
            "'05/01/2007' 0.0 '06/15/2007' 0.0 0.03 1 "
            "0 0 1 0 0 {wet_width_max_cm:g} 1"
        ),
        node_line=" 7",
    ),
    DripScenario(
        name="long_multi_node",
        event_line=(
            "'05/01/2007' 0.0 '06/15/2007' 0.0 0.02 3 "
            "0 0 1 0 0 {wet_width_max_cm:g} 1"
        ),
        node_line=" 6 7 8",
    ),
    DripScenario(
        name="long_high_single",
        event_line=(
            "'05/01/2007' 0.0 '06/15/2007' 0.0 0.08 1 "
            "0 0 1 0 0 {wet_width_max_cm:g} 1"
        ),
        node_line=" 7",
    ),
    DripScenario(
        name="long_pressure_single",
        event_line=(
            "'05/01/2007' 0.0 '06/15/2007' 0.0 0.08 1 "
            "1 1.0 1.0 0.0 0.0 {wet_width_max_cm:g} 1"
        ),
        node_line=" 7",
        pressure_reference="long_high_single",
    ),
)


def run_regression_matrix(
    repo_root=None,
    workspace=None,
    executable_dir=None,
    timeout_seconds=180,
    keep_workspace=False,
) -> dict:
    """Prepare, run, and validate the full drip-regression matrix."""
    repo = _resolve_repo_root(repo_root)
    base_run = repo / BASE_RUN_RELATIVE
    exe_dir = _resolve_executable_dir(repo, executable_dir)

    if workspace is None:
        tmp_root = repo / "tmp"
        tmp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="codex_drip_regression_",
            dir=tmp_root,
        ) as tmp_dir:
            return _run_matrix_in_workspace(
                repo,
                base_run,
                exe_dir,
                Path(tmp_dir),
                timeout_seconds,
            )

    work_root = Path(workspace).expanduser().resolve()
    if work_root.exists() and not keep_workspace:
        _ensure_tmp_workspace(repo, work_root)
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    summary = _run_matrix_in_workspace(
        repo,
        base_run,
        exe_dir,
        work_root,
        timeout_seconds,
    )
    if not keep_workspace:
        _ensure_tmp_workspace(repo, work_root)
        shutil.rmtree(work_root)
    return summary


def build_regression_cases(workspace, soils=DEFAULT_SOILS, grids=DEFAULT_GRIDS):
    """Return the full list of baseline and drip cases for the matrix."""
    root = Path(workspace)
    cases = []
    for soil in soils:
        for grid in grids:
            prefix = f"{soil.name}__{grid.name}"
            cases.append(
                RegressionCase(
                    name=f"{prefix}__baseline",
                    soil=soil,
                    grid=grid,
                    scenario=None,
                    run_dir=root / f"{prefix}__baseline",
                )
            )
            for scenario in DEFAULT_SCENARIOS:
                cases.append(
                    RegressionCase(
                        name=f"{prefix}__{scenario.name}",
                        soil=soil,
                        grid=grid,
                        scenario=scenario,
                        run_dir=root / f"{prefix}__{scenario.name}",
                    )
                )
    return cases


def prepare_regression_case(base_run, executable_dir, case):
    """Copy and mutate one self-contained model run directory."""
    base = Path(base_run).resolve()
    exe_dir = Path(executable_dir).resolve()
    run_dir = case.run_dir
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(
        base,
        run_dir,
        ignore=shutil.ignore_patterns(
            "logs",
            "*.out",
            "*.g0*",
            "*.G0*",
            "MassBl.out",
            "MassBlRunOff.out",
            "MassBlMulch.out",
        ),
    )
    shutil.copy2(exe_dir / EXECUTABLE_NAME, run_dir / EXECUTABLE_NAME)
    shutil.copy2(exe_dir / DLL_NAME, run_dir / DLL_NAME)
    write_soil_file(run_dir / "Loam_200cm.soi", case.soil)
    set_water_dtmax(run_dir / "WaterMovDefault.dat", REGRESSION_WATER_DTMX_DAYS)
    scale_grid_file(run_dir / "LOAM2D.grd", case.grid.x_scale)
    write_drip_file(run_dir / "LOAM2D.drp", case.scenario, case.soil)
    return run_dir


def write_soil_file(path, soil):
    """Write a single-material MAIZSIM soil file."""
    lines = [
        "           *** Material information ****                                                                   g/g  ",
        "   thr       ths         tha       thm      Alfa      n        Ks         Kk       thk       BulkD     OM    Sand    Silt   InitType",
        (
            f" {soil.thr:.3f}\t {soil.ths:.3f}\t {soil.tha:.3f}\t "
            f"{soil.thm:.3f}\t {soil.alpha:.5f}\t {soil.n:.5f}\t "
            f"{soil.ks:.3f}\t {soil.kk:.3f}\t  {soil.thk:.3f}\t "
            f"{soil.bulk_density:.3f}\t {soil.organic_matter:.4f}\t "
            f"{soil.sand:.2f}\t {soil.silt:.2f}\t  '{soil.init_type}'"
        ),
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_water_dtmax(path, dtmx_days):
    """Set the MAIZSIM water-mover maximum time step in days."""
    water_path = Path(path)
    lines = water_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        parts = line.split()
        if len(parts) < 10:
            continue
        try:
            for value in parts[:10]:
                float(value)
        except ValueError:
            continue
        parts[5] = f"{dtmx_days:g}"
        lines[index] = " ".join(parts)
        water_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    raise ValueError(f"Could not find water-mover parameter row in {water_path}")


def scale_grid_file(path, x_scale):
    """Scale grid x coordinates and boundary widths in a MAIZSIM .grd file."""
    grid_path = Path(path)
    lines = grid_path.read_text(encoding="utf-8").splitlines()
    layout = _grid_layout(lines)
    node_start = layout["node_start"]
    node_count = layout["node_count"]
    boundary_start = layout["boundary_start"]
    boundary_count = layout["boundary_count"]

    for index in range(node_start, node_start + node_count):
        parts = lines[index].split()
        if len(parts) < 4:
            raise ValueError(f"Invalid grid node line {index + 1}: {lines[index]}")
        node, x, y, material = parts[:4]
        lines[index] = f"\t{node}\t{float(x) * x_scale:g}\t{float(y):g}\t{material}"

    for index in range(boundary_start, boundary_start + boundary_count):
        parts = lines[index].split()
        if len(parts) < 6:
            raise ValueError(
                f"Invalid grid boundary line {index + 1}: {lines[index]}"
            )
        node, code_w, code_c, code_h, code_g, width = parts[:6]
        lines[index] = (
            f"    {node} {code_w}    {code_c}     {code_h}    "
            f"{code_g}      {float(width) * x_scale:g}"
        )

    grid_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_drip_file(path, scenario, soil=None):
    """Write the drip schedule for one matrix case."""
    if scenario is None:
        lines = [
            "*****Script for Drip application module  ******* wAppl is cm water per hour at each source boundary",
            "Number of Drip irrigations(max=75)  ",
            " 0 ",
            "No drip irrigation",
        ]
    else:
        lines = [
            "*****Script for Drip application module  ******* wAppl is cm water per hour at each source boundary",
            "Number of Drip irrigations(max=75)  ",
            " 1 ",
            "Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes",
            render_drip_event_line(scenario, soil),
            "Drip application nodes",
            scenario.node_line,
        ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_drip_event_line(scenario, soil=None):
    """Render a drip event line with any soil-specific calibration values."""
    event_line = scenario.event_line
    if "{wet_width_max_cm" not in event_line:
        return event_line
    if soil is None:
        raise ValueError("A soil is required to render calibrated drip width")
    soil_name = soil.name if hasattr(soil, "name") else str(soil)
    return event_line.format(
        wet_width_max_cm=calibrated_drip_wet_width_max_cm(soil_name),
    )


def grid_surface_widths(path):
    """Return surface-node widths and grid width from a .grd file."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    layout = _grid_layout(lines)
    widths = {}
    for line in lines[
        layout["boundary_start"]: layout["boundary_start"] + layout["boundary_count"]
    ]:
        parts = line.split()
        node = int(parts[0])
        code_w = int(parts[1])
        width = float(parts[5])
        if abs(code_w) == 4:
            widths[node] = width
    if not widths:
        raise ValueError(f"Grid has no abs(CodeW)==4 surface nodes: {path}")
    return widths, sum(widths.values())


def read_g05(path):
    """Read G05 output with normalized column names."""
    data = pd.read_csv(path, skipinitialspace=True)
    data = data.rename(columns=lambda column: str(column).strip().strip(","))
    data = data.dropna(how="all")
    return data


def validate_matrix_outputs(cases):
    """Validate completed model outputs and return metrics keyed by case name."""
    metrics = {}
    failures = []
    grouped = {}
    for case in cases:
        grouped.setdefault((case.soil.name, case.grid.name), {})[
            case.scenario.name if case.scenario else "baseline"
        ] = case

    for case in cases:
        try:
            metrics[case.name] = validate_case_output(case)
        except Exception as exc:
            failures.append(f"{case.name}: {exc}")

    for (soil_name, grid_name), by_scenario in grouped.items():
        baseline_case = by_scenario["baseline"]
        baseline = metrics.get(baseline_case.name)
        if baseline is None:
            continue
        if abs(baseline.drip_sum_mm) > 0.001:
            failures.append(
                f"{baseline_case.name}: baseline DripInput is "
                f"{baseline.drip_sum_mm:.6g} mm"
            )
        if abs(baseline.drip_demand_sum_mm) > 0.001:
            failures.append(
                f"{baseline_case.name}: baseline DripDemand is "
                f"{baseline.drip_demand_sum_mm:.6g} mm"
            )
        for scenario in DEFAULT_SCENARIOS:
            case = by_scenario[scenario.name]
            current = metrics.get(case.name)
            if current is None:
                continue
            _validate_drip_metrics(case, current, baseline, failures)
            if scenario.pressure_reference:
                reference_case = by_scenario[scenario.pressure_reference]
                reference = metrics.get(reference_case.name)
                if reference and current.drip_sum_mm > reference.drip_sum_mm + 0.001:
                    failures.append(
                        f"{case.name}: pressure-corrected DripInput "
                        f"{current.drip_sum_mm:.6g} exceeds uncorrected "
                        f"{reference.drip_sum_mm:.6g}"
                    )

    if failures:
        raise AssertionError("\n".join(failures))
    return metrics


def validate_case_output(case):
    """Validate one G05 file and return summary metrics."""
    g05_path = case.run_dir / "LOAM2D.G05"
    data = read_g05(g05_path)
    required_columns = (
        "Date",
        "CumRain",
        "infil",
        "Runoff",
        "Drainage",
        "DripInput",
        "SeasDrip",
        "DripDemand",
        "DripPressureLoss",
        "DripHydraulicExcess",
        "DripActualInfil",
        "DripSourceInput",
        "DripSourceLoss",
        "DripWetNodesMean",
        "DripWetNodesMax",
        "DripWetWidthMean",
        "DripWetWidthMax",
        "DripPressureFactorMean",
        "DripPressureFactorMin",
    )
    columns = {
        name: _require_column(data, name, g05_path)
        for name in required_columns
    }
    numeric = {
        name: pd.to_numeric(data[column], errors="raise").astype(float)
        for name, column in columns.items()
        if name != "Date"
    }
    for name, values in numeric.items():
        if not bool(values.map(math.isfinite).all()):
            raise ValueError(f"G05 column {name} contains non-finite values")
    non_negative_columns = (
        "DripDemand",
        "DripInput",
        "SeasDrip",
        "DripPressureLoss",
        "DripHydraulicExcess",
        "DripActualInfil",
        "DripSourceInput",
        "DripSourceLoss",
        "DripWetNodesMean",
        "DripWetNodesMax",
        "DripWetWidthMean",
        "DripWetWidthMax",
        "DripPressureFactorMean",
        "DripPressureFactorMin",
    )
    for name in non_negative_columns:
        if bool((numeric[name] < -1.0e-9).any()):
            raise ValueError(f"G05 column {name} contains negative values")
    if bool((numeric["DripWetNodesMax"] + 1.0e-9 < numeric["DripWetNodesMean"]).any()):
        raise ValueError("G05 DripWetNodesMax is smaller than DripWetNodesMean")
    if bool((numeric["DripWetWidthMax"] + 1.0e-9 < numeric["DripWetWidthMean"]).any()):
        raise ValueError("G05 DripWetWidthMax is smaller than DripWetWidthMean")
    active_rows = numeric["DripDemand"] > 1.0e-9
    if bool(active_rows.any()):
        if bool((numeric["DripPressureFactorMean"][active_rows] > 1.0 + 1.0e-6).any()):
            raise ValueError("G05 DripPressureFactorMean exceeds 1.0")
        if bool((numeric["DripPressureFactorMin"][active_rows] > 1.0 + 1.0e-6).any()):
            raise ValueError("G05 DripPressureFactorMin exceeds 1.0")
        if bool(
            (
                numeric["DripPressureFactorMin"][active_rows]
                > numeric["DripPressureFactorMean"][active_rows] + 1.0e-6
            ).any()
        ):
            raise ValueError(
                "G05 DripPressureFactorMin exceeds DripPressureFactorMean"
            )

    drip_sum = float(numeric["DripInput"].sum())
    seas_drip = float(numeric["SeasDrip"].iloc[-1])
    active_drip = numeric["DripDemand"] > 1.0e-9
    if bool(active_drip.any()):
        drip_wet_nodes_mean = float(numeric["DripWetNodesMean"][active_drip].mean())
        drip_wet_width_mean = float(numeric["DripWetWidthMean"][active_drip].mean())
        drip_pressure_factor_mean = float(
            numeric["DripPressureFactorMean"][active_drip].mean()
        )
        drip_pressure_factor_min = float(
            numeric["DripPressureFactorMin"][active_drip].min()
        )
    else:
        drip_wet_nodes_mean = 0.0
        drip_wet_width_mean = 0.0
        drip_pressure_factor_mean = 0.0
        drip_pressure_factor_min = 0.0
    expected = 0.0
    wet_width_limit = 0.0
    if case.scenario is not None:
        widths, grid_width = grid_surface_widths(case.run_dir / "LOAM2D.grd")
        schedule = parse_drip_file(case.run_dir / "LOAM2D.drp")
        expected = schedule.expected_grid_depth_mm(widths, grid_width)
        positive_limits = [
            event.wet_width_max_cm
            for event in schedule.events
            if event.wet_width_max_cm > 0.0
        ]
        if positive_limits:
            wet_width_limit = max(positive_limits)
            if float(numeric["DripWetWidthMax"].max()) > wet_width_limit + 0.05:
                raise ValueError(
                    "G05 DripWetWidthMax exceeds configured drip wetted-width limit"
                )

    drip_demand_sum = float(numeric["DripDemand"].sum())
    drip_pressure_loss_sum = float(numeric["DripPressureLoss"].sum())
    drip_hydraulic_excess_sum = float(numeric["DripHydraulicExcess"].sum())
    drip_actual_infil_sum = float(numeric["DripActualInfil"].sum())
    drip_source_input_sum = float(numeric["DripSourceInput"].sum())
    drip_source_loss_sum = float(numeric["DripSourceLoss"].sum())

    return CaseMetrics(
        name=case.name,
        success=True,
        drip_sum_mm=drip_sum,
        final_seas_drip_mm=seas_drip,
        cumrain_sum_mm=float(numeric["CumRain"].sum()),
        infil_sum_mm=float(numeric["infil"].sum()),
        runoff_sum_mm=float(numeric["Runoff"].sum()),
        drainage_sum_mm=float(numeric["Drainage"].sum()),
        expected_drip_mm=expected,
        drip_demand_sum_mm=drip_demand_sum,
        drip_pressure_loss_sum_mm=drip_pressure_loss_sum,
        drip_hydraulic_excess_sum_mm=drip_hydraulic_excess_sum,
        drip_actual_infil_sum_mm=drip_actual_infil_sum,
        drip_source_input_sum_mm=drip_source_input_sum,
        drip_source_loss_sum_mm=drip_source_loss_sum,
        demand_input_pressure_residual_mm=(
            drip_demand_sum - drip_sum - drip_pressure_loss_sum
        ),
        input_source_residual_mm=(
            drip_sum - drip_source_input_sum - drip_source_loss_sum
        ),
        input_acceptance_residual_mm=(
            drip_sum - drip_actual_infil_sum - drip_hydraulic_excess_sum
        ),
        drip_wet_nodes_mean=drip_wet_nodes_mean,
        drip_wet_nodes_max=float(numeric["DripWetNodesMax"].max()),
        drip_wet_width_mean_cm=drip_wet_width_mean,
        drip_wet_width_max_cm=float(numeric["DripWetWidthMax"].max()),
        drip_wet_width_limit_cm=wet_width_limit,
        drip_pressure_factor_mean=drip_pressure_factor_mean,
        drip_pressure_factor_min=drip_pressure_factor_min,
    )


def _run_matrix_in_workspace(repo, base_run, executable_dir, workspace, timeout_seconds):
    _require_file(executable_dir / EXECUTABLE_NAME)
    _require_file(executable_dir / DLL_NAME)
    _require_file(base_run / RUN_FILE)

    cases = build_regression_cases(workspace)
    for case in cases:
        prepare_regression_case(base_run, executable_dir, case)
        result = run_model(
            case.run_dir,
            executable=EXECUTABLE_NAME,
            run_file=RUN_FILE,
            timeout_seconds=timeout_seconds,
        )
        if not result.success:
            raise RuntimeError(f"{case.name}: {result.message}")
        check_required_outputs(case.run_dir, REQUIRED_OUTPUTS)

    metrics = validate_matrix_outputs(cases)
    return _summary(repo, workspace, cases, metrics)


def _summary(repo, workspace, cases, metrics):
    soil_names = sorted({case.soil.name for case in cases})
    grid_names = sorted({case.grid.name for case in cases})
    scenario_names = ["baseline"] + [scenario.name for scenario in DEFAULT_SCENARIOS]
    drip_cases = [case for case in cases if case.scenario is not None]
    totals = {
        "drip_input_mm": round(
            sum(metrics[case.name].drip_sum_mm for case in drip_cases),
            6,
        ),
        "drip_demand_mm": round(
            sum(metrics[case.name].drip_demand_sum_mm for case in drip_cases),
            6,
        ),
        "drip_pressure_loss_mm": round(
            sum(metrics[case.name].drip_pressure_loss_sum_mm for case in drip_cases),
            6,
        ),
        "drip_hydraulic_excess_mm": round(
            sum(
                metrics[case.name].drip_hydraulic_excess_sum_mm
                for case in drip_cases
            ),
            6,
        ),
        "drip_actual_infil_mm": round(
            sum(metrics[case.name].drip_actual_infil_sum_mm for case in drip_cases),
            6,
        ),
        "drip_source_input_mm": round(
            sum(metrics[case.name].drip_source_input_sum_mm for case in drip_cases),
            6,
        ),
        "drip_source_loss_mm": round(
            sum(metrics[case.name].drip_source_loss_sum_mm for case in drip_cases),
            6,
        ),
        "demand_input_pressure_residual_mm": round(
            sum(
                metrics[case.name].demand_input_pressure_residual_mm
                for case in drip_cases
            ),
            6,
        ),
        "input_source_residual_mm": round(
            sum(metrics[case.name].input_source_residual_mm for case in drip_cases),
            6,
        ),
        "input_acceptance_residual_mm": round(
            sum(
                metrics[case.name].input_acceptance_residual_mm
                for case in drip_cases
            ),
            6,
        ),
        "expected_drip_mm": round(
            sum(metrics[case.name].expected_drip_mm for case in drip_cases),
            6,
        ),
        "runoff_mm": round(
            sum(metrics[case.name].runoff_sum_mm for case in drip_cases),
            6,
        ),
    }
    return {
        "repo": str(repo),
        "workspace": str(workspace),
        "soil_count": len(soil_names),
        "grid_count": len(grid_names),
        "scenario_count": len(scenario_names),
        "model_run_count": len(cases),
        "soils": soil_names,
        "grids": grid_names,
        "scenarios": scenario_names,
        "drip_wet_width_limits_cm": {
            soil_name: round(calibrated_drip_wet_width_max_cm(soil_name), 6)
            for soil_name in soil_names
        },
        "drip_wet_width_sources": {
            soil_name: drip_wet_width_calibration_source(soil_name)
            for soil_name in soil_names
        },
        "totals": totals,
        "case_metrics": {
            name: {
                "drip_sum_mm": round(metric.drip_sum_mm, 6),
                "final_seas_drip_mm": round(metric.final_seas_drip_mm, 6),
                "cumrain_sum_mm": round(metric.cumrain_sum_mm, 6),
                "infil_sum_mm": round(metric.infil_sum_mm, 6),
                "runoff_sum_mm": round(metric.runoff_sum_mm, 6),
                "drainage_sum_mm": round(metric.drainage_sum_mm, 6),
                "expected_drip_mm": round(metric.expected_drip_mm, 6),
                "drip_demand_sum_mm": round(metric.drip_demand_sum_mm, 6),
                "drip_pressure_loss_sum_mm": round(
                    metric.drip_pressure_loss_sum_mm,
                    6,
                ),
                "drip_hydraulic_excess_sum_mm": round(
                    metric.drip_hydraulic_excess_sum_mm,
                    6,
                ),
                "drip_actual_infil_sum_mm": round(
                    metric.drip_actual_infil_sum_mm,
                    6,
                ),
                "drip_source_input_sum_mm": round(
                    metric.drip_source_input_sum_mm,
                    6,
                ),
                "drip_source_loss_sum_mm": round(
                    metric.drip_source_loss_sum_mm,
                    6,
                ),
                "demand_input_pressure_residual_mm": round(
                    metric.demand_input_pressure_residual_mm,
                    6,
                ),
                "input_source_residual_mm": round(
                    metric.input_source_residual_mm,
                    6,
                ),
                "input_acceptance_residual_mm": round(
                    metric.input_acceptance_residual_mm,
                    6,
                ),
                "drip_wet_nodes_mean": round(metric.drip_wet_nodes_mean, 6),
                "drip_wet_nodes_max": round(metric.drip_wet_nodes_max, 6),
                "drip_wet_width_mean_cm": round(metric.drip_wet_width_mean_cm, 6),
                "drip_wet_width_max_cm": round(metric.drip_wet_width_max_cm, 6),
                "drip_wet_width_limit_cm": round(
                    metric.drip_wet_width_limit_cm,
                    6,
                ),
                "drip_pressure_factor_mean": round(
                    metric.drip_pressure_factor_mean,
                    6,
                ),
                "drip_pressure_factor_min": round(
                    metric.drip_pressure_factor_min,
                    6,
                ),
            }
            for name, metric in sorted(metrics.items())
        },
    }


def _validate_drip_metrics(case, current, baseline, failures):
    if current.drip_sum_mm <= 0.0:
        failures.append(f"{case.name}: DripInput is not positive")
    if current.drip_demand_sum_mm <= 0.0:
        failures.append(f"{case.name}: DripDemand is not positive")
    if abs(
        current.drip_demand_sum_mm
        - current.drip_sum_mm
        - current.drip_pressure_loss_sum_mm
    ) > max(0.5, 0.05 * current.drip_demand_sum_mm):
        failures.append(
            f"{case.name}: DripDemand {current.drip_demand_sum_mm:.6g}, "
            f"DripInput {current.drip_sum_mm:.6g}, and pressure loss "
            f"{current.drip_pressure_loss_sum_mm:.6g} do not close"
        )
    if abs(current.drip_demand_sum_mm - current.expected_drip_mm) > max(
        0.5,
        0.05 * current.expected_drip_mm,
    ):
        failures.append(
            f"{case.name}: DripDemand {current.drip_demand_sum_mm:.6g} "
            f"differs from expected {current.expected_drip_mm:.6g}"
        )
    if abs(current.final_seas_drip_mm - current.drip_sum_mm) > max(
        0.1,
        0.02 * current.drip_sum_mm,
    ):
        failures.append(
            f"{case.name}: final SeasDrip {current.final_seas_drip_mm:.6g} "
            f"does not match DripInput sum {current.drip_sum_mm:.6g}"
        )
    if case.scenario and "pressure" not in case.scenario.name:
        if abs(current.drip_sum_mm - current.expected_drip_mm) > max(
            1.0,
            0.15 * current.expected_drip_mm,
        ):
            failures.append(
                f"{case.name}: DripInput {current.drip_sum_mm:.6g} differs "
                f"from expected {current.expected_drip_mm:.6g}"
            )
        if abs(current.drip_pressure_loss_sum_mm) > 0.01:
            failures.append(
                f"{case.name}: non-pressure drip has pressure loss "
                f"{current.drip_pressure_loss_sum_mm:.6g}"
            )
        if abs(current.drip_pressure_factor_mean - 1.0) > 0.001:
            failures.append(
                f"{case.name}: non-pressure mean pressure factor is "
                f"{current.drip_pressure_factor_mean:.6g}"
            )
        if abs(current.drip_pressure_factor_min - 1.0) > 0.001:
            failures.append(
                f"{case.name}: non-pressure min pressure factor is "
                f"{current.drip_pressure_factor_min:.6g}"
            )
    if current.drip_wet_nodes_max < max(1.0, current.drip_wet_nodes_mean):
        failures.append(
            f"{case.name}: wet node diagnostics are inconsistent "
            f"mean={current.drip_wet_nodes_mean:.6g}, "
            f"max={current.drip_wet_nodes_max:.6g}"
        )
    if current.drip_wet_width_max_cm + 1.0e-6 < current.drip_wet_width_mean_cm:
        failures.append(
            f"{case.name}: wet width diagnostics are inconsistent "
            f"mean={current.drip_wet_width_mean_cm:.6g}, "
            f"max={current.drip_wet_width_max_cm:.6g}"
        )
    if not (0.0 <= current.drip_pressure_factor_min <= 1.0 + 1.0e-6):
        failures.append(
            f"{case.name}: min pressure factor is "
            f"{current.drip_pressure_factor_min:.6g}"
        )
    if not (0.0 <= current.drip_pressure_factor_mean <= 1.0 + 1.0e-6):
        failures.append(
            f"{case.name}: mean pressure factor is "
            f"{current.drip_pressure_factor_mean:.6g}"
        )
    cumrain_delta = current.cumrain_sum_mm - baseline.cumrain_sum_mm
    infil_delta = current.infil_sum_mm - baseline.infil_sum_mm
    if cumrain_delta <= 0.0:
        failures.append(f"{case.name}: CumRain did not increase")
    if infil_delta < -0.1:
        failures.append(f"{case.name}: infiltration decreased by {infil_delta:.6g}")
    if abs(cumrain_delta - current.drip_sum_mm) > max(1.0, 0.20 * current.drip_sum_mm):
        failures.append(
            f"{case.name}: CumRain delta {cumrain_delta:.6g} and "
            f"DripInput {current.drip_sum_mm:.6g} disagree"
        )
    if current.runoff_sum_mm < -0.001:
        failures.append(f"{case.name}: Runoff is negative")


def _grid_layout(lines):
    header_index = next(
        index
        for index, line in enumerate(lines)
        if "KAT" in line and "NumNP" in line
    )
    counts = lines[header_index + 1].split()
    node_count = int(counts[1])
    boundary_count = int(counts[3])
    node_header = next(
        index
        for index, line in enumerate(lines)
        if "MatNum" in line and "x" in line
    )
    boundary_header = next(
        index
        for index, line in enumerate(lines)
        if "CodeW" in line and "Width" in line
    )
    return {
        "node_count": node_count,
        "boundary_count": boundary_count,
        "node_start": node_header + 1,
        "boundary_start": boundary_header + 1,
    }


def _require_column(data, required_name, path):
    normalized = _normalize_column(required_name)
    for column in data.columns:
        if _normalize_column(column) == normalized:
            return column
    raise ValueError(f"Missing G05 column {required_name!r} in {path}")


def _normalize_column(column):
    return "".join(str(column).strip().casefold().split()).replace("_", "")


def _resolve_repo_root(repo_root):
    if repo_root is not None:
        return Path(repo_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _resolve_executable_dir(repo, executable_dir):
    if executable_dir is not None:
        return Path(executable_dir).expanduser().resolve()
    return repo / "build" / "maizsim" / "x64" / "Release"


def _require_file(path):
    if not Path(path).is_file():
        raise FileNotFoundError(f"Required file does not exist: {path}")


def _ensure_tmp_workspace(repo, workspace):
    tmp_root = (repo / "tmp").resolve()
    target = Path(workspace).resolve()
    if not str(target).casefold().startswith(str(tmp_root).casefold()):
        raise ValueError(f"Refusing to delete workspace outside {tmp_root}: {target}")


def parse_args(arguments=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the MAIZSIM drip long-regression matrix.",
    )
    parser.add_argument("--repo-root", help="Repository root. Defaults to auto-detect.")
    parser.add_argument(
        "--workspace",
        help="Workspace under repo tmp/. Defaults to an auto-cleaned temp directory.",
    )
    parser.add_argument(
        "--executable-dir",
        help="Directory containing 2dMAIZSIM.exe and Maizsim.dll.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help="Timeout for each model run.",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep the workspace after the run for inspection.",
    )
    return parser.parse_args(arguments)


def main(arguments=None):
    """CLI entrypoint."""
    args = parse_args(arguments)
    summary = run_regression_matrix(
        repo_root=args.repo_root,
        workspace=args.workspace,
        executable_dir=args.executable_dir,
        timeout_seconds=args.timeout_seconds,
        keep_workspace=args.keep_workspace,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
