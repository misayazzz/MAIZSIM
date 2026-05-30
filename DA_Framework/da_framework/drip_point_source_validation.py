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
DRIP_STOP = datetime(2007, 5, 21, 0, 0)
FINAL_DATE = date(2007, 5, 21)
SOURCE_NODE = 1
SOURCE_WIDTH_CM = 0.38
DRIP_RATE_CM_H = 0.5
DELTA_LEVELS = (0.02, 0.05)


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


SOILS = (
    SoilCase("sandy_loam", 0.065, 0.410, 0.075, 1.890, 106.10, 1.55, 0.0020, 0.65, 0.25),
    SoilCase("loam", 0.078, 0.430, 0.036, 1.560, 30.00, 1.40, 0.0025, 0.43, 0.39),
    SoilCase("clay_loam", 0.095, 0.410, 0.019, 1.310, 6.24, 1.30, 0.0030, 0.30, 0.34),
)


def run_validation(workspace, executable_dir=None, timeout_seconds=180):
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
    figure_paths = []
    for soil in SOILS:
        baseline_dir = cases_root / f"codex_{soil.name}_baseline"
        drip_dir = cases_root / f"codex_{soil.name}_mode4_drip"
        _prepare_case(baseline_dir, soil, executable_root, drip=False)
        _prepare_case(drip_dir, soil, executable_root, drip=True)

        for run_dir in (baseline_dir, drip_dir):
            result = run_model(run_dir, timeout_seconds=timeout_seconds)
            if not result.success:
                raise RuntimeError(f"{run_dir.name} failed: {result.message}")
            _assert_no_failure_markers(run_dir)

        baseline_g03 = _read_g03(_find_output_file(baseline_dir, ".G03"))
        drip_g03 = _read_g03(_find_output_file(drip_dir, ".G03"))
        g05 = read_g05_surface_water(_find_output_file(drip_dir, ".G05"))

        balance = _drip_balance(g05)
        rows.append(
            {
                "soil": soil.name,
                "drip_input_mm": balance["input"],
                "drip_actual_infil_mm": balance["actual"],
                "drip_storage_change_mm": balance["storage_change"],
                "drip_surface_runoff_mm": balance["surface_runoff"],
                "drip_hydraulic_excess_mm": balance["hydraulic_excess"],
                "acceptance_residual_mm": balance["residual"],
                "drip_surface_storage_max_mm": balance["storage_max"],
                "drip_wet_width_max_cm": float(g05.get("drip_wet_width_max_cm", pd.Series([0.0])).max()),
                "theta_min": float(drip_g03["theta"].min()),
                "theta_max": float(drip_g03["theta"].max()),
                "source_width_cm": SOURCE_WIDTH_CM,
                "source_node": SOURCE_NODE,
                "drip_spread_mode": 4,
            }
        )
        _assert_g05_is_physical(g05, soil.name)
        _assert_theta_is_finite(drip_g03, soil)

        for elapsed_h in (6, 12, 24):
            for threshold in DELTA_LEVELS:
                shape = _delta_shape_metrics(
                    baseline_g03,
                    drip_g03,
                    elapsed_h,
                    threshold=threshold,
                    mirror=True,
                )
                shape_rows.append({"soil": soil.name, "elapsed_h": elapsed_h, **shape})

        figure_paths.extend(
            _write_soil_figures(soil.name, baseline_g03, drip_g03, figures_root)
        )

    summary = pd.DataFrame(rows)
    shapes = pd.DataFrame(shape_rows)
    summary_path = tables_root / "codex_mode4_point_source_summary.csv"
    shapes_path = tables_root / "codex_mode4_wetted_front_metrics.csv"
    manifest_path = output_root / "codex_mode4_point_source_manifest.json"
    summary.to_csv(summary_path, index=False)
    shapes.to_csv(shapes_path, index=False)
    _write_manifest(manifest_path, output_root, summary_path, shapes_path, figure_paths)
    return {
        "workspace": str(output_root),
        "summary_csv": str(summary_path),
        "shape_metrics_csv": str(shapes_path),
        "manifest_json": str(manifest_path),
        "figures": [str(path) for path in figure_paths],
        "summary": rows,
        "shape_metrics": shape_rows,
    }


def _prepare_case(run_dir, soil, executable_root, drip):
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(BASE_RUN, run_dir)
    for name in (MODEL_EXE, MODEL_DLL):
        shutil.copy2(executable_root / name, run_dir / name)
    _write_soil(run_dir / "Loam_200cm.soi", soil)
    _write_time_file(run_dir / "LOAM2D.tim")
    _write_ini_file(run_dir / "LOAM2D.ini")
    _write_water_mover(run_dir / "WaterMovDefault.dat")
    _write_zero_weather_header(run_dir / "WyeClimate.dat")
    _write_zero_weather(run_dir / "LOAM2D.wea")
    _write_zero_management(run_dir / "LOAM2D.man")
    _write_no_irrigation(run_dir / "LOAM2D.irr")
    if drip:
        _write_mode4_drip(run_dir / "LOAM2D.drp")
    else:
        _write_no_drip(run_dir / "LOAM2D.drp")


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


def _write_time_file(path):
    lines = [
        "*** SYNCHRONIZER INFORMATION *****************************",
        "Initial time       dt       dtMin     DMul1    DMul2    tFin",
        f"'{_fmt_date(INITIAL_DATE)}'   0.0001        0.0000001     1.3           0.3          '{_fmt_date(FINAL_DATE)}'",
        "Output variables, 1 if true  Daily    Hourly",
        " 1             1 ",
        " Daily       Hourly   Weather data frequency. if daily enter 1   0; if hourly enter 0  1  ",
        " 0             1 ",
        "RunToEnd  - if 1 model continues after crop maturity to end time in time file",
        " 1 ",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ini_file(path):
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
        "'05/18/2007'  '05/21/2007'  60",
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


def _write_zero_weather(path):
    rows = [
        "*** zero-weather mode4 point-source validation",
        " JDay   Date  Hour     Rad      Temper    rain     Wind   RH   CO2",
    ]
    current = INITIAL_DATE
    while current <= FINAL_DATE:
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


def _write_mode4_drip(path):
    lines = [
        "*****Script for Drip application module  ******* wAppl is cm water per hour at each source boundary",
        "Number of Drip irrigations(max=75)",
        " 1 ",
        "Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax DripSpreadMode DripSourceWidth",
        (
            f"'{_fmt_date(DRIP_START.date())}' {DRIP_START.hour:g} "
            f"'{_fmt_date(DRIP_STOP.date())}' {DRIP_STOP.hour:g} "
            f"{DRIP_RATE_CM_H:g} 1 0 0 1 0 0 0 4 {SOURCE_WIDTH_CM:g}"
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


def _column_sum(frame, column):
    if column not in frame:
        return 0.0
    return float(frame[column].sum())


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


def _write_soil_figures(soil_name, baseline, drip, figures_root):
    figure_paths = []
    theta24 = _frame_at_elapsed(drip, 24)
    half_path = figures_root / f"codex_{soil_name}_half_theta_24h.png"
    mirror_path = figures_root / f"codex_{soil_name}_mirrored_theta_24h.png"
    _plot_field(
        theta24,
        "theta",
        half_path,
        title=f"{soil_name} mode4 half-domain theta, 24 h",
        mirrored=False,
        cmap="viridis",
    )
    _plot_field(
        theta24,
        "theta",
        mirror_path,
        title=f"{soil_name} mode4 mirrored theta, 24 h",
        mirrored=True,
        cmap="viridis",
    )
    figure_paths.extend([half_path, mirror_path])

    for elapsed_h in (6, 12, 24):
        delta = _delta_frame(baseline, drip, elapsed_h)
        delta_path = figures_root / f"codex_{soil_name}_mirrored_delta_{elapsed_h}h.png"
        _plot_field(
            delta,
            "delta_theta",
            delta_path,
            title=f"{soil_name} mode4 mirrored delta theta, {elapsed_h} h",
            mirrored=True,
            cmap="RdBu_r",
            delta=True,
        )
        figure_paths.append(delta_path)
    return figure_paths


def _plot_field(frame, value_column, path, title, mirrored, cmap, delta=False):
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
    if mirrored:
        ax.set_xlim(-20, 20)
    else:
        ax.set_xlim(0, 20)
    ax.set_ylim(80, 0)
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("depth (cm)")
    ax.set_title(title)
    fig.colorbar(contour, ax=ax, label=value_column)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _delta_frame(baseline, drip, elapsed_h):
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


def _delta_shape_metrics(baseline, drip, elapsed_h, threshold, mirror):
    delta = _delta_frame(baseline, drip, elapsed_h)
    if mirror:
        delta = _mirror_frame(delta)
    wet = delta[delta["delta_theta"] >= threshold]
    if wet.empty:
        return {
            "threshold": threshold,
            "wet_width_cm": 0.0,
            "wet_depth_cm": 0.0,
            "delta_theta_max": float(delta["delta_theta"].max()),
        }
    return {
        "threshold": threshold,
        "wet_width_cm": float(wet["x"].max() - wet["x"].min()),
        "wet_depth_cm": float(wet["depth_cm"].max()),
        "delta_theta_max": float(delta["delta_theta"].max()),
    }


def _frame_at_elapsed(frame, elapsed_h):
    target = _excel_serial(DRIP_START.date()) + elapsed_h / 24.0
    times = np.asarray(sorted(frame["date_time"].unique()), dtype=float)
    selected = float(times[np.argmin(np.abs(times - target))])
    if abs(selected - target) > 0.08:
        raise ValueError(f"No G03 frame near elapsed {elapsed_h:g} h; nearest Date_time={selected:g}")
    return frame.loc[np.isclose(frame["date_time"], selected)].copy()


def _mirror_frame(frame):
    original = frame.copy()
    mirrored = original.loc[original["x"].abs() > 1.0e-9].copy()
    mirrored["x"] = -mirrored["x"]
    return pd.concat([mirrored, original], ignore_index=True)


def _write_manifest(path, output_root, summary_path, shapes_path, figure_paths):
    manifest = {
        "workspace": str(output_root),
        "mode": "DripSpreadMode=4 surface point source",
        "half_domain": True,
        "symmetry_axis_x_cm": 0.0,
        "source_node": SOURCE_NODE,
        "source_width_cm": SOURCE_WIDTH_CM,
        "drip_rate_cm_h": DRIP_RATE_CM_H,
        "drip_start": DRIP_START.isoformat(),
        "drip_stop": DRIP_STOP.isoformat(),
        "grid_refinement": (
            "Base LOAM2D half-domain grid; first surface boundary width is "
            "0.38 cm and shallow vertical spacing starts at 0.05 cm near the emitter."
        ),
        "summary_csv": str(summary_path),
        "shape_metrics_csv": str(shapes_path),
        "figures": [str(path) for path in figure_paths],
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


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
    args = parser.parse_args(argv)
    result = run_validation(
        args.workspace,
        executable_dir=args.executable_dir,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
