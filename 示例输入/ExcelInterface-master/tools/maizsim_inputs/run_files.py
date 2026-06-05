"""run 文件规范化."""

from pathlib import Path

from .errors import ConfigError
from .path_utils import resolve_run_dir


RUN_FILE_NAME = "run.dat"


def normalize_run_files(paths, runs):
    """把宏生成的 run<ID>.dat 规范化为 run.dat."""
    results = []
    for run in runs:
        run_id = run["id"]
        run_dir = resolve_run_dir(paths["root_path"], run["path"])
        if not run_dir.is_dir():
            raise ConfigError(f"{run_id} 的 run 目录不存在, 无法规范化 run 文件: {run_dir}")

        source = run_dir / f"run{run_id}.dat"
        target = run_dir / RUN_FILE_NAME
        if not source.is_file():
            raise ConfigError(f"{run_id} 的宏生成 run 文件不存在, 无法规范化为 {RUN_FILE_NAME}: {source}")

        source.replace(target)
        rewrite_run_file_local_paths(target, run_dir)
        if not target.is_file() or target.stat().st_size <= 0:
            raise ConfigError(f"{run_id} 的 {RUN_FILE_NAME} 未生成或为空: {target}")

        results.append(
            {
                "id": run_id,
                "run_dir": run_dir,
                "source": source,
                "target": target,
            }
        )
    return results


def rewrite_run_file_local_paths(run_file, run_dir):
    """把 run.dat 中指向本运行目录的绝对路径改为文件名."""
    run_dir = Path(run_dir).resolve()
    lines = run_file.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    rewritten = []
    for line in lines:
        content = line.lstrip("\ufeff")
        stripped = content.strip()
        if not stripped:
            rewritten.append(content)
            continue

        candidate = Path(stripped)
        if candidate.is_absolute():
            try:
                resolved = candidate.resolve()
            except OSError:
                rewritten.append(line)
                continue
            if resolved.parent == run_dir:
                rewritten.append(resolved.name)
                continue
        rewritten.append(content)
    run_file.write_text("\r\n".join(rewritten) + "\r\n", encoding="utf-8", newline="")
