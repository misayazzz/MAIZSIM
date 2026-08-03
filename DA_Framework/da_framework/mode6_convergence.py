"""Executable grid and time-step convergence matrix for the drip line source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .mode6_30mm_validation import run_mode6_30mm_validation
from .mode6_30mm_validation import three_grid_gci
from .mode6_30mm_validation import _wetting_shape
from .mode6_30mm_validation import EVENT_START
from .mode6_30mm_validation import WATER_BALANCE_ABSOLUTE_TOLERANCE_MM
from .mode6_30mm_validation import WATER_BALANCE_MAX_STEP_TOLERANCE_MM
from .mode6_30mm_validation import WATER_BALANCE_RELATIVE_TOLERANCE_PCT


GRID_LEVELS = (0, 1, 2)
TIME_STEPS_DAYS = (0.001, 0.0005, 0.00025)
CONVERGENCE_METRICS = (
    "actual_infiltration_mm",
    "delta_theta_max",
    "wetting_depth_cm",
    "wetting_area_cm2",
    "half_domain_delta_storage_cm2",
)
PRIMARY_CONVERGENCE_METRICS = (
    "actual_infiltration_mm",
    "half_domain_delta_storage_cm2",
)


def run_mode6_convergence(
    *,
    repo_root,
    workspace,
    kind,
    soil="loam",
    timeout_seconds=1800,
):
    """Run a three-level convergence matrix and write its guarded GCI report."""
    if kind not in {"grid", "time"}:
        raise ValueError("kind must be 'grid' or 'time'")
    work_root = Path(workspace).expanduser().resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    levels = GRID_LEVELS if kind == "grid" else TIME_STEPS_DAYS
    records = []
    run_summaries = []
    for level in levels:
        slug = str(level).replace(".", "p")
        kwargs = {
            "grid_level": int(level) if kind == "grid" else 0,
            "dtmx_days": float(level) if kind == "time" else 0.001,
        }
        summary = run_mode6_30mm_validation(
            repo_root=repo_root,
            workspace=work_root / f"codex_{kind}_{slug}",
            soil_names=(soil,),
            timeout_seconds=timeout_seconds,
            **kwargs,
        )
        row = dict(summary["results"][0])
        row["grid_level"] = int(summary["grid"]["level"])
        row["dtmx_days"] = float(summary["dtmx_days"])
        records.append(row)
        run_summaries.append(summary["json"])

    report = convergence_report(records, axis=kind)
    report.update(
        {
            "soil": soil,
            "run_summaries": run_summaries,
        }
    )
    csv_path = work_root / f"codex_mode6_{kind}_convergence.csv"
    json_path = work_root / f"codex_mode6_{kind}_convergence.json"
    pd.DataFrame(records).to_csv(csv_path, index=False)
    report["csv"] = str(csv_path)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report["json"] = str(json_path)
    return report


def summarize_existing_convergence(*, summary_paths, workspace, kind):
    """Build a convergence report from three completed validation summaries."""
    paths = tuple(Path(path).expanduser().resolve() for path in summary_paths)
    if len(paths) != 3:
        raise ValueError("Exactly three validation summaries are required")
    records = []
    for path in paths:
        summary = json.loads(path.read_text(encoding="utf-8"))
        if len(summary["results"]) != 1:
            raise ValueError("Each convergence summary must contain one soil")
        row = dict(summary["results"][0])
        row["grid_level"] = int(summary["grid"]["level"])
        row["dtmx_days"] = float(summary["dtmx_days"])
        if "mirror_volume_ratio" not in row:
            root = path.parent
            soil = row["soil"]
            grid = summary["grid"]
            shape = _wetting_shape(
                root / f"codex_{soil}__hutd06__baseline" / "HUTD06.G03",
                root / f"codex_{soil}__hutd06__mode6_30mm" / "HUTD06.G03",
                emitter_x_cm=float(summary["emitter_x_cm"]),
                refinement_bounds=(
                    0.0,
                    float(grid["actual_refined_x_max_cm"]),
                    float(grid["actual_refined_y_min_cm"]),
                    float(grid["surface_y_cm"]),
                ),
                evaluation_time=(
                    EVENT_START
                    + pd.Timedelta(hours=float(summary["duration_h"]))
                ),
            )
            row.update(shape)
        records.append(row)
    report = convergence_report(records, axis=kind)
    report["source_summaries"] = [str(path) for path in paths]
    output_root = Path(workspace).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    csv_path = output_root / f"codex_mode6_{kind}_convergence.csv"
    json_path = output_root / f"codex_mode6_{kind}_convergence.json"
    pd.DataFrame(report["records"]).to_csv(csv_path, index=False)
    report["csv"] = str(csv_path)
    report["json"] = str(json_path)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def convergence_report(records, *, axis):
    """Calculate guarded three-level GCI values without hiding failed checks."""
    if axis not in {"grid", "time"}:
        raise ValueError("axis must be 'grid' or 'time'")
    if len(records) != 3:
        raise ValueError("Convergence reporting requires exactly three levels")
    key = "grid_level" if axis == "grid" else "dtmx_days"
    ordered = sorted(records, key=lambda row: float(row[key]))
    if axis == "time":
        ordered.reverse()
    expected = GRID_LEVELS if axis == "grid" else TIME_STEPS_DAYS
    actual = tuple(row[key] for row in ordered)
    if actual != expected:
        raise ValueError(f"Unexpected {axis} levels: {actual}")

    gci = {}
    for metric in CONVERGENCE_METRICS:
        values = tuple(float(row[metric]) for row in ordered)
        result = three_grid_gci(*values)
        result["medium_fine_relative_difference_pct"] = (
            abs(values[1] - values[2]) / max(abs(values[2]), 1.0e-12) * 100.0
        )
        gci[metric] = result
    ledger_pass = all(
        abs(float(row["terminal_ledger_error_mm"])) <= 0.01
        and abs(float(row["ledger_closure_abs_max_mm"])) <= 0.01
        and float(row["solver_limit_max"]) == 0.0
        and float(row["boundary_limit_max"]) == 0.0
        and abs(float(row["uncategorized_step_cuts"])) <= 0.5
        and abs(float(row["baseline_water_balance_residual_mm"]))
        <= WATER_BALANCE_ABSOLUTE_TOLERANCE_MM
        and float(row["baseline_water_balance_max_step_residual_mm"])
        <= WATER_BALANCE_MAX_STEP_TOLERANCE_MM
        and abs(float(row["mode6_water_balance_residual_mm"]))
        <= WATER_BALANCE_ABSOLUTE_TOLERANCE_MM
        and float(row["mode6_water_balance_relative_error_pct"])
        <= WATER_BALANCE_RELATIVE_TOLERANCE_PCT
        and float(row["mode6_water_balance_max_step_residual_mm"])
        <= WATER_BALANCE_MAX_STEP_TOLERANCE_MM
        and abs(float(row["mirror_volume_ratio"]) - 2.0) <= 1.0e-12
        and float(row["mirror_pair_abs_max"]) <= 1.0e-12
        for row in ordered
    )
    return {
        "status": (
            "pass"
            if ledger_pass
            and all(gci[metric]["valid"] for metric in PRIMARY_CONVERGENCE_METRICS)
            else "fail"
        ),
        "axis": axis,
        "levels": list(actual),
        "ledger_and_mirror_pass": ledger_pass,
        "primary_metrics": list(PRIMARY_CONVERGENCE_METRICS),
        "supplemental_metrics_are_diagnostic": True,
        "gci": gci,
        "records": ordered,
    }


def _parse_args(arguments=None):
    parser = argparse.ArgumentParser(
        description="Run guarded Mode6 grid or time-step convergence.",
    )
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[2])
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--kind", choices=("grid", "time"), required=True)
    parser.add_argument("--soil", default="loam")
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument(
        "--summary",
        action="append",
        help="Reuse a completed validation JSON; repeat exactly three times.",
    )
    return parser.parse_args(arguments)


def main(arguments=None):
    args = _parse_args(arguments)
    if args.summary:
        report = summarize_existing_convergence(
            summary_paths=args.summary,
            workspace=args.workspace,
            kind=args.kind,
        )
    else:
        report = run_mode6_convergence(
            repo_root=args.repo_root,
            workspace=args.workspace,
            kind=args.kind,
            soil=args.soil,
            timeout_seconds=args.timeout_seconds,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
