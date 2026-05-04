"""敏感性分析配置读取和校验."""

from pathlib import Path
import tomllib


class SensitivityConfigError(Exception):
    """敏感性分析配置错误."""


def load_toml(path):
    """读取 TOML 文件并返回字典."""
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError as exc:
        raise SensitivityConfigError(f"配置文件不存在: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SensitivityConfigError(f"TOML 解析失败: {exc}") from exc


def find_project_dir(bounds_path):
    """定位 ExcelInterface-master 项目目录."""
    for candidate in [bounds_path.parent, *bounds_path.parents]:
        if (candidate / "maizsim_generate_inputs.py").is_file() and (candidate / "tools").is_dir():
            return candidate
    raise SensitivityConfigError(f"无法从参数边界文件定位 ExcelInterface-master 目录: {bounds_path}")


def require_section(config, section_name):
    """读取必需配置段."""
    section = config.get(section_name)
    if not isinstance(section, dict):
        raise SensitivityConfigError(f"缺少 [{section_name}] 配置段.")
    return section


def resolve_project_path(project_dir, value, field_name):
    """按 ExcelInterface-master 项目目录解析路径."""
    if not isinstance(value, str) or not value.strip():
        raise SensitivityConfigError(f"{field_name} 必须是非空字符串路径.")
    raw_path = Path(value).expanduser()
    if raw_path.is_absolute():
        return raw_path.resolve()
    return (project_dir / raw_path).resolve()


def require_file(path, field_name):
    """确认路径是文件."""
    if not path.is_file():
        raise SensitivityConfigError(f"{field_name} 必须指向文件: {path}")


def require_directory(path, field_name):
    """确认路径是目录."""
    if not path.is_dir():
        raise SensitivityConfigError(f"{field_name} 必须指向目录: {path}")


def validate_parameters(parameters):
    """校验参数列表并返回标准化参数."""
    if not isinstance(parameters, list) or not parameters:
        raise SensitivityConfigError("parameters 必须是非空列表.")

    result = []
    names = set()
    for index, parameter in enumerate(parameters, 1):
        if not isinstance(parameter, dict):
            raise SensitivityConfigError(f"第 {index} 个参数必须是表.")
        name = parameter.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SensitivityConfigError(f"第 {index} 个参数缺少 name.")
        if name in names:
            raise SensitivityConfigError(f"参数 name 重复: {name}")
        names.add(name)

        for field_name in ["current", "lower", "upper"]:
            value = parameter.get(field_name)
            if not isinstance(value, (int, float)):
                raise SensitivityConfigError(f"参数 {name} 的 {field_name} 必须是数值.")
        if parameter["lower"] >= parameter["upper"]:
            raise SensitivityConfigError(f"参数 {name} 的 lower 必须小于 upper.")

        value_type = parameter.get("value_type")
        if value_type not in ["continuous", "integer"]:
            raise SensitivityConfigError(f"参数 {name} 的 value_type 只支持 continuous 或 integer.")

        target_file = parameter.get("target_file")
        target_fields = parameter.get("target_fields")
        if not isinstance(target_file, str) or not target_file.strip():
            raise SensitivityConfigError(f"参数 {name} 缺少 target_file.")
        if not isinstance(target_fields, list) or not target_fields:
            raise SensitivityConfigError(f"参数 {name} 缺少 target_fields.")
        result.append(parameter)
    return result


def validate_output_metrics(metrics):
    """校验输出指标配置."""
    if not isinstance(metrics, list) or not metrics:
        raise SensitivityConfigError("output_metrics 必须是非空列表.")
    result = []
    names = set()
    for index, metric in enumerate(metrics, 1):
        if not isinstance(metric, dict):
            raise SensitivityConfigError(f"第 {index} 个输出指标必须是表.")
        name = metric.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SensitivityConfigError(f"第 {index} 个输出指标缺少 name.")
        if name in names:
            raise SensitivityConfigError(f"输出指标 name 重复: {name}")
        names.add(name)
        result.append(metric)
    return result


def trajectories_for_mode(config, mode):
    """根据运行模式读取 Morris 轨迹数."""
    defaults = require_section(config, "morris_defaults")
    field_name = f"{mode}_trajectories"
    value = defaults.get(field_name)
    if not isinstance(value, int) or value <= 0:
        raise SensitivityConfigError(f"morris_defaults.{field_name} 必须是正整数.")
    return value


def read_config(bounds_path):
    """读取参数边界配置并完成路径标准化."""
    bounds_path = Path(bounds_path).expanduser().resolve()
    raw_config = load_toml(bounds_path)
    project_dir = find_project_dir(bounds_path)

    metadata = require_section(raw_config, "metadata")
    parallel = require_section(raw_config, "parallel_execution")
    defaults = require_section(raw_config, "morris_defaults")
    parameters = validate_parameters(raw_config.get("parameters"))
    output_metrics = validate_output_metrics(raw_config.get("output_metrics"))

    baseline_run_dir = resolve_project_path(project_dir, parallel.get("baseline_run_dir"), "parallel_execution.baseline_run_dir")
    run_root = resolve_project_path(project_dir, parallel.get("run_root"), "parallel_execution.run_root")
    require_directory(baseline_run_dir, "parallel_execution.baseline_run_dir")

    case_id = metadata.get("case_id", "LOAM2D")
    if not isinstance(case_id, str) or not case_id.strip():
        raise SensitivityConfigError("metadata.case_id 必须是非空字符串.")

    num_levels = defaults.get("num_levels", 4)
    seed = defaults.get("seed", 20260429)
    if not isinstance(num_levels, int) or num_levels < 2:
        raise SensitivityConfigError("morris_defaults.num_levels 必须是大于等于 2 的整数.")
    if not isinstance(seed, int):
        raise SensitivityConfigError("morris_defaults.seed 必须是整数.")
    rejection_max_attempts = defaults.get("rejection_max_attempts", 100)
    if not isinstance(rejection_max_attempts, int) or rejection_max_attempts <= 0:
        raise SensitivityConfigError("morris_defaults.rejection_max_attempts 必须是正整数.")
    defaults["rejection_max_attempts"] = rejection_max_attempts
    rejection_tolerance = defaults.get("rejection_tolerance", 1e-9)
    if not isinstance(rejection_tolerance, (int, float)) or rejection_tolerance < 0:
        raise SensitivityConfigError("morris_defaults.rejection_tolerance 必须是非负数值.")
    defaults["rejection_tolerance"] = float(rejection_tolerance)
    analysis_scaled = defaults.get("analysis_scaled", False)
    if not isinstance(analysis_scaled, bool):
        raise SensitivityConfigError("morris_defaults.analysis_scaled 必须是布尔值.")
    if any(parameter["value_type"] == "integer" for parameter in parameters) and not analysis_scaled:
        raise SensitivityConfigError("存在整数参数时 morris_defaults.analysis_scaled 必须为 true.")
    defaults["analysis_scaled"] = analysis_scaled

    timeout_seconds = parallel.get("timeout_seconds", 900)
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise SensitivityConfigError("parallel_execution.timeout_seconds 必须是正整数.")
    slow_seconds = parallel.get("slow_seconds", 120)
    if not isinstance(slow_seconds, int) or slow_seconds <= 0:
        raise SensitivityConfigError("parallel_execution.slow_seconds 必须是正整数.")

    return {
        "bounds_path": bounds_path,
        "project_dir": project_dir,
        "case_id": case_id.strip(),
        "baseline_run_dir": baseline_run_dir,
        "run_root": run_root,
        "parameters": parameters,
        "output_metrics": output_metrics,
        "morris_defaults": defaults,
        "timeout_seconds": timeout_seconds,
        "slow_seconds": slow_seconds,
    }
