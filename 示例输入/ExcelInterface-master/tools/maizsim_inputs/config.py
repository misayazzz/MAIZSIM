"""TOML 配置读取和标准化."""

import tomllib

from .errors import ConfigError
from .path_utils import require_directory
from .path_utils import require_file
from .path_utils import resolve_existing_path
from .path_utils import resolve_output_path


def load_toml_config(config_path):
    """读取 TOML 文件并返回配置字典."""
    try:
        with config_path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML 解析失败: {exc}") from exc


def require_section(config, section_name):
    """读取必需配置段."""
    section = config.get(section_name)
    if not isinstance(section, dict):
        raise ConfigError(f"缺少 [{section_name}] 配置段.")
    return section


def read_optional_bool(section, field_name, default_value):
    """读取可选布尔值, 避免把字符串误判为 True."""
    if field_name not in section:
        return default_value
    value = section[field_name]
    if not isinstance(value, bool):
        raise ConfigError(f"run.{field_name} 必须是 true 或 false.")
    return value


def read_config(config_path):
    """读取并标准化配置."""
    config = load_toml_config(config_path)
    paths_section = require_section(config, "paths")
    run_section = require_section(config, "run")

    required_path_fields = [
        "input_excel_file",
        "root_path",
        "maizsim_path",
        "create_soils",
        "excel_interface",
        "macro_workbook",
        "weather_csv_folder",
    ]
    paths = {}
    for field_name in required_path_fields:
        if field_name not in paths_section:
            raise ConfigError(f"缺少 paths.{field_name}.")
        paths[field_name] = resolve_existing_path(paths_section[field_name], config_path, f"paths.{field_name}")

    require_file(paths["input_excel_file"], "paths.input_excel_file")
    require_file(paths["macro_workbook"], "paths.macro_workbook")
    require_directory(paths["root_path"], "paths.root_path")
    require_directory(paths["maizsim_path"], "paths.maizsim_path")
    require_directory(paths["create_soils"], "paths.create_soils")
    require_directory(paths["excel_interface"], "paths.excel_interface")
    require_directory(paths["weather_csv_folder"], "paths.weather_csv_folder")

    selected_ids = run_section.get("selected_ids")
    if not isinstance(selected_ids, list) or not selected_ids:
        raise ConfigError("run.selected_ids 必须是非空字符串列表.")
    cleaned_ids = []
    for index, selected_id in enumerate(selected_ids, 1):
        if not isinstance(selected_id, str) or not selected_id.strip():
            raise ConfigError(f"run.selected_ids 第 {index} 项必须是非空字符串.")
        cleaned_ids.append(selected_id.strip())

    if "automation_workbook" not in run_section:
        raise ConfigError("缺少 run.automation_workbook.")

    run = {
        "selected_ids": cleaned_ids,
        "automation_workbook": resolve_output_path(
            run_section["automation_workbook"], config_path, "run.automation_workbook"
        ),
        "visible_excel": read_optional_bool(run_section, "visible_excel", False),
        "save_after_run": read_optional_bool(run_section, "save_after_run", True),
    }
    return {"paths": paths, "run": run}

