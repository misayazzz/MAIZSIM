"""路径解析和输出目标保护."""

from pathlib import Path

from .errors import ConfigError


PACKAGE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = PACKAGE_DIR.parent
PROJECT_DIR = TOOLS_DIR.parent
WORKSPACE_DIR = PROJECT_DIR.parent


def unique_paths(paths):
    """按顺序去重 Path 候选值."""
    result = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def resolve_existing_path(value, config_path, field_name):
    """解析必须已存在的路径, 优先按配置文件目录解析相对路径."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field_name} 必须是非空字符串路径.")

    raw_path = Path(value).expanduser()
    if raw_path.is_absolute():
        candidates = [raw_path]
    else:
        candidates = [
            config_path.parent / raw_path,
            Path.cwd() / raw_path,
            WORKSPACE_DIR / raw_path,
            PROJECT_DIR / raw_path,
        ]

    candidates = unique_paths(candidates)
    for candidate in candidates:
        if candidate.exists():
            return candidate

    tried = "; ".join(str(candidate) for candidate in candidates)
    raise ConfigError(f"{field_name} 路径不存在. 已尝试: {tried}")


def require_file(path, field_name):
    """确认路径是文件."""
    if not path.is_file():
        raise ConfigError(f"{field_name} 必须指向文件: {path}")


def require_directory(path, field_name):
    """确认路径是目录."""
    if not path.is_dir():
        raise ConfigError(f"{field_name} 必须指向目录: {path}")


def resolve_output_path(value, config_path, field_name):
    """解析输出路径, 优先按配置文件目录解析相对路径."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field_name} 必须是非空字符串路径.")

    raw_path = Path(value).expanduser()
    if raw_path.is_absolute():
        return raw_path.resolve()

    candidates = unique_paths(
        [
            config_path.parent / raw_path,
            Path.cwd() / raw_path,
            WORKSPACE_DIR / raw_path,
            PROJECT_DIR / raw_path,
        ]
    )
    for candidate in candidates:
        if candidate.parent.exists():
            return candidate
    return candidates[0]


def path_has_part(path, part):
    """判断路径中是否包含指定目录名."""
    target = part.lower()
    return any(item.lower() == target for item in path.resolve().parts)


def validate_automation_workbook_target(macro_workbook, automation_workbook):
    """确认自动化副本目标不会误覆盖重要文件."""
    macro_path = macro_workbook.resolve()
    automation_path = automation_workbook.resolve()
    if macro_path == automation_path:
        raise ConfigError("run.automation_workbook 不能与 paths.macro_workbook 指向同一个文件.")
    if automation_path.exists() and not path_has_part(automation_path, ".generated"):
        raise ConfigError(
            f"run.automation_workbook 已存在且不在 .generated 目录下, 为避免误覆盖已停止: {automation_path}"
        )


def resolve_run_dir(root_path, run_path):
    """根据 root_path 和 Description.Path 定位 run 目录."""
    raw_path = Path(run_path).expanduser()
    if raw_path.is_absolute():
        return raw_path.resolve()
    return (root_path / raw_path).resolve()
