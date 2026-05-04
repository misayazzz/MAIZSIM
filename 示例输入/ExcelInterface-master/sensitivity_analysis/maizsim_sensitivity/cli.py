"""敏感性分析命令行入口."""

from datetime import datetime
from pathlib import Path
import argparse
import sys

import pandas as pd

from .config import SensitivityConfigError
from .config import read_config
from .files import ensure_new_analysis_dir
from .files import prepare_sample_dir
from .files import write_parameters
from .runner import calculate_morris_indices
from .runner import default_max_workers
from .runner import run_samples
from .sampling import actual_parameter_values
from .sampling import analysis_matrix_from_sample_table
from .sampling import generate_accepted_samples


def parse_args(arguments=None):
    """解析命令行参数."""
    parser = argparse.ArgumentParser(
        description="Run MAIZSIM Morris sensitivity analysis from a TOML bounds file."
    )
    parser.add_argument(
        "--bounds",
        required=True,
        help="Path to sensitivity_parameter_bounds.toml.",
    )
    parser.add_argument(
        "--mode",
        choices=["smoke", "formal"],
        default="smoke",
        help="Run scale. smoke validates the workflow, formal runs the Morris analysis.",
    )
    parser.add_argument(
        "--analysis-id",
        help="Output directory name under run_root. Default uses timestamp and mode.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        help="Parallel worker count.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and sampling without creating run directories.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override per-sample model timeout in seconds.",
    )
    parser.add_argument(
        "--slow-seconds",
        type=int,
        help="Override per-sample slow-run threshold in seconds.",
    )
    return parser.parse_args(arguments)


def analysis_id_for_args(args):
    """生成分析 ID."""
    if args.analysis_id:
        return args.analysis_id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{args.mode}_{timestamp}"


def trajectory_count(config, mode):
    """读取指定模式的轨迹数."""
    defaults = config["morris_defaults"]
    field_name = f"{mode}_trajectories"
    return defaults[field_name]


def worker_count(args):
    """确定并行运行数."""
    if args.max_workers is not None:
        if args.max_workers <= 0:
            raise SensitivityConfigError("--max-workers 必须是正整数.")
        return args.max_workers
    return default_max_workers()


def apply_timeout_override(config, args):
    """应用命令行样本超时覆盖."""
    if args.timeout_seconds is None:
        return
    if args.timeout_seconds <= 0:
        raise SensitivityConfigError("--timeout-seconds 必须是正整数.")
    config["timeout_seconds"] = args.timeout_seconds


def apply_slow_override(config, args):
    """应用命令行慢运行阈值覆盖."""
    if args.slow_seconds is None:
        return
    if args.slow_seconds <= 0:
        raise SensitivityConfigError("--slow-seconds 必须是正整数.")
    config["slow_seconds"] = args.slow_seconds


def build_sample_jobs(config, analysis_dir, sample_table):
    """准备样本目录和并行运行任务."""
    sample_root = analysis_dir / "samples"
    sample_root.mkdir(parents=True, exist_ok=True)
    sample_jobs = []
    for _, sample_row in sample_table.iterrows():
        sample_id = int(sample_row["sample_id"])
        sample_dir = sample_root / f"sample_{sample_id:06d}"
        prepare_sample_dir(config["baseline_run_dir"], sample_dir)
        values = actual_parameter_values(config["parameters"], sample_row)
        write_parameters(sample_dir, values)
        sample_jobs.append(
            {
                "sample_id": sample_id,
                "trajectory_id": int(sample_row["trajectory_id"]),
                "step_id": int(sample_row["step_id"]),
                "changed_parameter": sample_row["changed_parameter"],
                "sample_dir": sample_dir,
                "timeout_seconds": config["timeout_seconds"],
                "slow_seconds": config["slow_seconds"],
            }
        )
    return sample_jobs


def write_csv(path, rows):
    """写入 CSV 文件."""
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def report_sampling_summary(summary):
    """输出拒绝采样摘要."""
    if summary["rejected_designs"]:
        print(
            f"高危组合拒绝采样完成. rejected_designs={summary['rejected_designs']}, "
            f"accepted_seed={summary['accepted_seed']}."
        )
    else:
        print(f"高危组合拒绝采样未触发. accepted_seed={summary['accepted_seed']}.")


def slow_sample_rows(manifest_rows):
    """筛选成功但运行明显变慢的样本."""
    rows = []
    for row in manifest_rows:
        if row.get("status") == "success" and row.get("is_slow") == "true":
            rows.append(row)
    return rows


def slow_trajectory_ids(slow_rows):
    """从慢样本记录中提取需要剔除的 Morris 轨迹编号."""
    return sorted({int(row["trajectory_id"]) for row in slow_rows})


def filter_table_without_trajectories(sample_table, dropped_trajectory_ids):
    """剔除包含慢样本的整条 Morris 轨迹, 保留剩余样本表."""
    if not dropped_trajectory_ids:
        return sample_table.copy()
    return sample_table.loc[~sample_table["trajectory_id"].isin(dropped_trajectory_ids)].copy()


def filter_outputs_without_trajectories(output_rows, kept_sample_ids):
    """按保留样本编号筛选输出指标记录."""
    kept_sample_ids = set(int(sample_id) for sample_id in kept_sample_ids)
    return [row for row in output_rows if int(row["sample_id"]) in kept_sample_ids]


def calculate_indices_without_slow_trajectories(problem, sample_table, output_rows, slow_rows, config):
    """剔除慢轨迹后计算 Morris 敏感性指标.

    输入为完整样本表, 完整输出指标和慢样本记录. 输出为指标表, 摘要记录和被剔除的
    轨迹编号. 若没有慢样本, 摘要记录中的剔除轨迹为空.
    """
    dropped_trajectory_ids = slow_trajectory_ids(slow_rows)
    filtered_sample_table = filter_table_without_trajectories(sample_table, dropped_trajectory_ids)
    kept_sample_ids = filtered_sample_table["sample_id"].tolist()
    filtered_output_rows = filter_outputs_without_trajectories(output_rows, kept_sample_ids)
    filtered_matrix = analysis_matrix_from_sample_table(config["parameters"], filtered_sample_table)
    indices = calculate_morris_indices(
        problem,
        filtered_matrix,
        filtered_output_rows,
        config["output_metrics"],
        config["morris_defaults"],
    )
    summary = {
        "version": "without_slow_trajectories",
        "output_file": "morris_indices_without_slow_trajectories.csv",
        "sample_count": len(filtered_sample_table),
        "trajectory_count": filtered_sample_table["trajectory_id"].nunique(),
        "slow_sample_count_included": 0,
        "dropped_trajectory_ids": ",".join(str(item) for item in dropped_trajectory_ids),
        "morris_index_rows": len(indices),
    }
    return indices, summary, dropped_trajectory_ids


def calculate_all_morris_indices(problem, sample_table, output_rows, slow_rows, config):
    """计算包含全部成功样本的 Morris 敏感性指标.

    输入为完整样本表, 完整输出指标和慢样本记录. 输出为指标表和摘要记录. 该结果用于
    和过滤慢轨迹后的结果做稳健性对比.
    """
    analysis_matrix = analysis_matrix_from_sample_table(config["parameters"], sample_table)
    indices = calculate_morris_indices(
        problem,
        analysis_matrix,
        output_rows,
        config["output_metrics"],
        config["morris_defaults"],
    )
    summary = {
        "version": "all_samples",
        "output_file": "morris_indices_all.csv",
        "sample_count": len(sample_table),
        "trajectory_count": sample_table["trajectory_id"].nunique(),
        "slow_sample_count_included": len(slow_rows),
        "dropped_trajectory_ids": "",
        "morris_index_rows": len(indices),
    }
    return indices, summary


def write_morris_indices_with_summary(
    problem,
    sample_table,
    output_rows,
    slow_rows,
    config,
    analysis_dir,
    include_filtered,
):
    """写出 Morris 指标文件和生成摘要."""
    summary_rows = []
    all_indices, all_summary = calculate_all_morris_indices(
        problem,
        sample_table,
        output_rows,
        slow_rows,
        config,
    )
    if all_indices.empty:
        return all_indices, pd.DataFrame(), all_summary, []
    all_indices.to_csv(analysis_dir / "morris_indices_all.csv", index=False, encoding="utf-8-sig")
    if not include_filtered:
        all_indices.to_csv(analysis_dir / "morris_indices.csv", index=False, encoding="utf-8-sig")
    summary_rows.append(all_summary)

    filtered_indices = pd.DataFrame()
    filtered_summary = None
    dropped_trajectory_ids = []
    if include_filtered:
        filtered_indices, filtered_summary, dropped_trajectory_ids = calculate_indices_without_slow_trajectories(
            problem,
            sample_table,
            output_rows,
            slow_rows,
            config,
        )
        if not filtered_indices.empty:
            filtered_indices.to_csv(
                analysis_dir / "morris_indices_without_slow_trajectories.csv",
                index=False,
                encoding="utf-8-sig",
            )
            summary_rows.append(filtered_summary)

    write_csv(analysis_dir / "morris_indices_generation_summary.csv", summary_rows)
    if include_filtered:
        return all_indices, filtered_indices, filtered_summary, dropped_trajectory_ids
    return all_indices, filtered_indices, all_summary, dropped_trajectory_ids


def write_filtered_morris_indices(problem, sample_table, output_rows, slow_rows, config, analysis_dir):
    """写出剔除慢轨迹后的 Morris 指标和生成摘要."""
    indices, summary, dropped_trajectory_ids = calculate_indices_without_slow_trajectories(
        problem,
        sample_table,
        output_rows,
        slow_rows,
        config,
    )
    if indices.empty:
        return indices, summary, dropped_trajectory_ids
    output_path = analysis_dir / "morris_indices_without_slow_trajectories.csv"
    summary_path = analysis_dir / "morris_indices_generation_summary.csv"
    indices.to_csv(output_path, index=False, encoding="utf-8-sig")
    write_csv(summary_path, [summary])
    return indices, summary, dropped_trajectory_ids


def main(arguments=None):
    """执行敏感性分析命令行入口."""
    args = parse_args(arguments)
    try:
        config = read_config(Path(args.bounds))
        apply_timeout_override(config, args)
        apply_slow_override(config, args)
        trajectories = trajectory_count(config, args.mode)
        num_levels = config["morris_defaults"]["num_levels"]
        seed = config["morris_defaults"]["seed"]
        max_attempts = config["morris_defaults"]["rejection_max_attempts"]
        tolerance = config["morris_defaults"]["rejection_tolerance"]
        problem, raw_matrix, sample_table, sampling_summary, rejection_rows = generate_accepted_samples(
            config["parameters"],
            trajectories,
            num_levels,
            seed,
            max_attempts,
            tolerance,
        )
        analysis_id = analysis_id_for_args(args)
        analysis_dir = config["run_root"] / analysis_id
        max_workers = worker_count(args)

        print(f"参数边界文件: {config['bounds_path']}")
        print(f"基线运行目录: {config['baseline_run_dir']}")
        print(f"分析输出目录: {analysis_dir}")
        print(
            f"Morris 采样完成. mode={args.mode}, trajectories={trajectories}, "
            f"parameters={len(config['parameters'])}, samples={len(sample_table)}."
        )
        report_sampling_summary(sampling_summary)
        print(f"并行 worker 数: {max_workers}")
        print(f"样本超时阈值: {config['timeout_seconds']} 秒, 慢运行阈值: {config['slow_seconds']} 秒")

        if args.dry_run:
            print(f"dry-run 完成, 未创建分析目录, 未复制样本目录, 未运行模型.")
            return 0

        ensure_new_analysis_dir(analysis_dir)
        sample_table.to_csv(analysis_dir / "samples.csv", index=False, encoding="utf-8-sig")
        write_csv(analysis_dir / "sampling_summary.csv", [sampling_summary])
        if rejection_rows:
            write_csv(analysis_dir / "rejected_designs.csv", rejection_rows)
        sample_jobs = build_sample_jobs(config, analysis_dir, sample_table)
        manifest_rows, output_rows, failure_rows = run_samples(sample_jobs, max_workers)
        slow_rows = slow_sample_rows(manifest_rows)

        write_csv(analysis_dir / "manifest.csv", manifest_rows)
        write_csv(analysis_dir / "outputs.csv", output_rows)
        write_csv(analysis_dir / "failures.csv", failure_rows)
        if slow_rows:
            write_csv(analysis_dir / "slow_samples.csv", slow_rows)

        if failure_rows:
            print(f"模型运行存在失败样本, 已写入 failures.csv. failed={len(failure_rows)}.")
            print(f"跳过 Morris 指标计算, 请先修复失败样本.")
            return 1
        if slow_rows:
            print(f"模型运行存在明显变慢样本, 已写入 slow_samples.csv. slow={len(slow_rows)}.")
            all_indices, indices, summary, dropped_trajectory_ids = write_morris_indices_with_summary(
                problem,
                sample_table,
                output_rows,
                slow_rows,
                config,
                analysis_dir,
                True,
            )
            if all_indices.empty or indices.empty:
                print(f"剔除慢轨迹后 Morris 指标未生成, 原因可能是剩余样本数量不足或输出指标缺失.")
                return 1
            dropped_text = ",".join(str(item) for item in dropped_trajectory_ids)
            print(
                f"已剔除含慢样本的 Morris 轨迹并生成过滤版指标. "
                f"dropped_trajectories={dropped_text}, "
                f"kept_trajectories={summary['trajectory_count']}, "
                f"morris_indices={len(indices)}."
            )
            return 0

        indices, _, summary, _ = write_morris_indices_with_summary(
            problem,
            sample_table,
            output_rows,
            slow_rows,
            config,
            analysis_dir,
            False,
        )
        if indices.empty:
            print(f"Morris 指标未生成, 原因可能是输出指标缺失或样本数量不完整.")
            return 1
        print(f"敏感性分析完成. outputs={len(output_rows)}, morris_indices={len(indices)}.")
        return 0
    except SensitivityConfigError as exc:
        sys.stderr.write(f"错误: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"未处理错误: {exc}\n")
        return 1
