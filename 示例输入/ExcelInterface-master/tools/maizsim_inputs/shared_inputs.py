"""公共输入文件补齐."""

import locale
import shutil

from .errors import ConfigError
from .path_utils import PROJECT_DIR
from .path_utils import resolve_run_dir
from .path_utils import unique_paths
from .run_files import RUN_FILE_NAME


WATER_BOUND_NAME = "WaterBound.DAT"


def get_water_bound_candidates(paths):
    """返回 WaterBound.DAT 的候选来源路径."""
    candidates = [
        paths["input_excel_file"].parent / WATER_BOUND_NAME,
        paths["weather_csv_folder"] / WATER_BOUND_NAME,
        PROJECT_DIR / "Example input" / WATER_BOUND_NAME,
    ]
    return unique_paths(candidates)


def find_water_bound_source(paths):
    """查找 WaterBound.DAT 来源文件, 找不到时抛出配置错误."""
    candidates = get_water_bound_candidates(paths)
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    tried = "; ".join(str(candidate) for candidate in candidates)
    raise ConfigError(f"{WATER_BOUND_NAME} 来源文件不存在. 已尝试: {tried}")


def get_text_encodings():
    """返回 run 文件可尝试的文本编码列表."""
    encodings = ["utf-8-sig", "utf-8", locale.getpreferredencoding(False), "gbk"]
    result = []
    seen = set()
    for encoding in encodings:
        key = encoding.lower()
        if key not in seen:
            seen.add(key)
            result.append(encoding)
    return result


def read_text_with_encoding(path):
    """读取文本并返回内容和实际编码, 无法读取时抛出配置错误."""
    last_error = None
    for encoding in get_text_encodings():
        try:
            return {
                "text": path.read_text(encoding=encoding),
                "encoding": encoding,
            }
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ConfigError(f"无法读取文本文件编码: {path}. 最后错误: {last_error}")


def rewrite_water_bound_reference(run_file, target):
    """把 run.dat 中的 WaterBound.DAT 引用改写到指定目标文件."""
    text_info = read_text_with_encoding(run_file)
    lines = text_info["text"].splitlines(keepends=True)
    matched_indexes = [
        index
        for index, line in enumerate(lines)
        if WATER_BOUND_NAME.lower() in line.lower()
    ]
    if not matched_indexes:
        raise ConfigError(f"run 文件中找不到 {WATER_BOUND_NAME} 引用: {run_file}")
    if len(matched_indexes) > 1:
        raise ConfigError(f"run 文件中存在多个 {WATER_BOUND_NAME} 引用, 已停止改写: {run_file}")

    index = matched_indexes[0]
    original_line = lines[index]
    newline = "\r\n" if original_line.endswith("\r\n") else "\n" if original_line.endswith("\n") else ""
    lines[index] = f"{target}{newline}"
    run_file.write_text("".join(lines), encoding=text_info["encoding"], newline="")
    return {
        "run_file": run_file,
        "target": target,
        "line_number": index + 1,
    }


def copy_water_bound_to_run_dirs(paths, runs):
    """把 WaterBound.DAT 复制到每个 run 目录, 并改写 run.dat 引用."""
    source = find_water_bound_source(paths)
    results = []
    for run in runs:
        run_id = run["id"]
        run_dir = resolve_run_dir(paths["root_path"], run["path"])
        if not run_dir.is_dir():
            raise ConfigError(f"{run_id} 的 run 目录不存在, 无法复制 {WATER_BOUND_NAME}: {run_dir}")

        target = run_dir / WATER_BOUND_NAME
        copied = False
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
            copied = True

        run_file = run_dir / RUN_FILE_NAME
        if not run_file.is_file():
            raise ConfigError(f"{run_id} 的 {RUN_FILE_NAME} 不存在, 无法改写 {WATER_BOUND_NAME} 引用: {run_file}")

        rewrite_result = rewrite_water_bound_reference(run_file, target)
        results.append(
            {
                "id": run_id,
                "source": source,
                "target": target,
                "copied": copied,
                "run_file": rewrite_result["run_file"],
                "line_number": rewrite_result["line_number"],
            }
        )
    return results
