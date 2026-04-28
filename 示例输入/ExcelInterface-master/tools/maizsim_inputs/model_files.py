"""模型运行文件复制."""

import shutil

from .errors import ConfigError
from .path_utils import PROJECT_DIR
from .path_utils import resolve_run_dir


MODEL_FILE_NAMES = [
    "2dMAIZSIM.exe",
    "Maizsim.dll",
]


def find_model_file_sources():
    """查找 Models 目录下的模型运行文件, 找不到或为空时抛出配置错误."""
    models_dir = PROJECT_DIR / "Models"
    sources = []
    missing = []
    empty = []
    for file_name in MODEL_FILE_NAMES:
        source = models_dir / file_name
        if not source.is_file():
            missing.append(source)
            continue
        if source.stat().st_size <= 0:
            empty.append(source)
            continue
        sources.append(source)

    if missing:
        tried = "; ".join(str(path) for path in missing)
        raise ConfigError(f"模型运行文件不存在. 已尝试: {tried}")
    if empty:
        tried = "; ".join(str(path) for path in empty)
        raise ConfigError(f"模型运行文件为空. 已尝试: {tried}")
    return sources


def copy_model_files_to_run_dirs(paths, runs):
    """把模型运行文件复制到每个 selected run 目录."""
    sources = find_model_file_sources()
    results = []
    for run in runs:
        run_id = run["id"]
        run_dir = resolve_run_dir(paths["root_path"], run["path"])
        if not run_dir.is_dir():
            raise ConfigError(f"{run_id} 的 run 目录不存在, 无法复制模型运行文件: {run_dir}")

        targets = []
        for source in sources:
            target = run_dir / source.name
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            if not target.is_file() or target.stat().st_size <= 0:
                raise ConfigError(f"{run_id} 的模型运行文件复制失败或为空: {target}")
            targets.append(target)

        results.append(
            {
                "id": run_id,
                "run_dir": run_dir,
                "targets": targets,
            }
        )
    return results
