"""样本并行运行和 Morris 指标计算."""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from datetime import datetime
import math
# os 仅用于读取 CPU 数量, 不参与路径处理.
import os
import subprocess
import time

from SALib.analyze import morris
import pandas as pd

from .outputs import parse_metrics


FAILURE_PATTERNS = [
    "ORTHOMIN TERMINATES -- TOO MANY ITERATIONS",
]


def default_max_workers():
    """读取默认并行运行数."""
    return min(8, os.cpu_count() or 1)


def solver_failure_message(stdout_text, stderr_text):
    """从模型输出中识别数值求解失败."""
    combined = f"{stdout_text}\n{stderr_text}"
    for pattern in FAILURE_PATTERNS:
        if pattern in combined:
            return pattern
    return ""


def run_one_sample(sample):
    """运行一个样本目录并解析输出指标."""
    sample_dir = sample["sample_dir"]
    started_at = datetime.now()
    start_time = time.perf_counter()
    stdout_path = sample_dir / "stdout.txt"
    stderr_path = sample_dir / "stderr.txt"
    result = {
        "sample_id": sample["sample_id"],
        "trajectory_id": sample["trajectory_id"],
        "step_id": sample["step_id"],
        "changed_parameter": sample["changed_parameter"],
        "sample_dir": str(sample_dir),
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": "",
        "elapsed_seconds": "",
        "slow_seconds": sample.get("slow_seconds", ""),
        "is_slow": "false",
        "status": "failed",
        "returncode": "",
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "error": "",
    }

    try:
        completed = subprocess.run(
            [str(sample_dir / "2dMAIZSIM.exe"), "run.dat"],
            cwd=sample_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=sample["timeout_seconds"],
            check=False,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8", errors="replace")
        stderr_path.write_text(completed.stderr, encoding="utf-8", errors="replace")
        result["returncode"] = completed.returncode
        if completed.returncode != 0:
            result["error"] = f"模型退出码非 0: {completed.returncode}"
            return result, None
        solver_failure = solver_failure_message(completed.stdout, completed.stderr)
        if solver_failure:
            result["error"] = f"模型数值求解失败: {solver_failure}"
            return result, None

        metrics = parse_metrics(sample_dir)
        result["status"] = "success"
        return result, metrics
    except subprocess.TimeoutExpired as exc:
        result["error"] = f"模型运行超时: {exc.timeout} 秒"
        stdout_path.write_text(exc.stdout or "", encoding="utf-8", errors="replace")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8", errors="replace")
        return result, None
    except Exception as exc:
        result["error"] = str(exc)
        return result, None
    finally:
        result["finished_at"] = datetime.now().isoformat(timespec="seconds")
        elapsed_seconds = time.perf_counter() - start_time
        result["elapsed_seconds"] = f"{elapsed_seconds:.3f}"
        slow_seconds = sample.get("slow_seconds")
        if result["status"] == "success" and slow_seconds is not None and elapsed_seconds >= slow_seconds:
            result["is_slow"] = "true"


def run_samples(sample_jobs, max_workers):
    """使用 concurrent.futures 并行运行全部样本."""
    manifest_rows = []
    output_rows = []
    failure_rows = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(run_one_sample, sample): sample for sample in sample_jobs}
        for future in as_completed(future_map):
            manifest, metrics = future.result()
            manifest_rows.append(manifest)
            if manifest["status"] == "success":
                row = {"sample_id": manifest["sample_id"]}
                row.update(metrics)
                output_rows.append(row)
            else:
                failure_rows.append(manifest)

    manifest_rows.sort(key=lambda row: row["sample_id"])
    output_rows.sort(key=lambda row: row["sample_id"])
    failure_rows.sort(key=lambda row: row["sample_id"])
    return manifest_rows, output_rows, failure_rows


def value_is_missing(value):
    """判断指标值是否缺失."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def calculate_morris_indices(problem, input_matrix, output_rows, metrics, defaults):
    """对每个输出指标计算 Morris 敏感性指数."""
    output_frame = pd.DataFrame(output_rows).sort_values("sample_id")
    if len(output_frame) != len(input_matrix):
        return pd.DataFrame()

    rows = []
    for metric in metrics:
        metric_name = metric["name"]
        if metric_name not in output_frame.columns:
            continue
        values = output_frame[metric_name].to_numpy()
        if any(value_is_missing(value) for value in values):
            continue

        analysis = morris.analyze(
            problem,
            input_matrix,
            values,
            num_resamples=defaults.get("analysis_num_resamples", 1000),
            conf_level=defaults.get("analysis_conf_level", 0.95),
            scaled=defaults.get("analysis_scaled", False),
            print_to_console=False,
            num_levels=defaults.get("num_levels", 4),
            seed=defaults.get("seed", 20260429),
        )
        names = analysis["names"]
        for index, parameter_name in enumerate(names):
            rows.append(
                {
                    "metric": metric_name,
                    "parameter": parameter_name,
                    "mu": analysis["mu"][index],
                    "mu_star": analysis["mu_star"][index],
                    "sigma": analysis["sigma"][index],
                    "mu_star_conf": analysis["mu_star_conf"][index],
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["metric", "mu_star"], ascending=[True, False])
