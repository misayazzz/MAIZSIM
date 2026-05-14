"""Configuration loading for the MAIZSIM IES framework."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigError

DEFAULT_PARAMETER_NAMES = ("n", "thetaS", "LM_min", "Rmax_LTAR", "StayGreen")
DEFAULT_PARAMETER_NAME_SET = frozenset(DEFAULT_PARAMETER_NAMES)
THETA_S_TARGET_FIELDS = ("ths", "th", "thk")


@dataclass(frozen=True)
class ParameterConfig:
    name: str
    current: float
    lower: float
    upper: float
    std: float
    target_file: str = ""
    target_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssimilationConfig:
    n_ensemble: int = 100
    n_iter: int = 3
    random_seed: int = 20240514


@dataclass(frozen=True)
class JuvenileLeavesConfig:
    candidates: tuple[int, ...] = (16, 17, 18, 19, 20)
    enabled: bool = True


@dataclass(frozen=True)
class ModelConfig:
    base_run_dir: Path
    executable: str = "2dMAIZSIM.exe"
    run_file: str = "run.dat"
    var_file: str = ""
    soi_file: str = ""
    minimal_outputs: bool = False
    max_workers: int = 12
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class ObservationConfig:
    file: Path


@dataclass(frozen=True)
class OutputConfig:
    run_root: Path = Path("DA_Framework/runs")
    experiment_name: str = "experiment_001"


@dataclass(frozen=True)
class FrameworkConfig:
    model: ModelConfig
    observation: ObservationConfig
    parameters: tuple[ParameterConfig, ...]
    assimilation: AssimilationConfig = field(default_factory=AssimilationConfig)
    juvenile_leaves: JuvenileLeavesConfig = field(
        default_factory=JuvenileLeavesConfig
    )
    output: OutputConfig = field(default_factory=OutputConfig)


def load_config(path: str | Path) -> FrameworkConfig:
    """Load and validate a TOML configuration file."""
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise ConfigError(f"configuration file does not exist: {config_path}")

    try:
        with config_path.open("rb") as file_obj:
            raw_config = tomllib.load(file_obj)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {config_path}: {exc}") from exc

    if not isinstance(raw_config, dict):
        raise ConfigError("configuration root must be a TOML table")

    model_config = _load_model_config(raw_config, config_path)
    observation_config = _load_observation_config(raw_config, config_path)
    assimilation_config = _load_assimilation_config(raw_config)
    juvenile_config = _load_juvenile_config(raw_config)
    output_config = _load_output_config(raw_config, config_path)
    parameter_config = _load_parameters(raw_config)

    config = FrameworkConfig(
        model=model_config,
        observation=observation_config,
        parameters=parameter_config,
        assimilation=assimilation_config,
        juvenile_leaves=juvenile_config,
        output=output_config,
    )
    _validate_config(config)
    return config


def _load_model_config(raw_config: dict[str, Any], config_path: Path) -> ModelConfig:
    table = _required_table(raw_config, "model")
    base_run_dir = _required_value(table, "base_run_dir", "model")

    return ModelConfig(
        base_run_dir=_resolve_path(base_run_dir, config_path),
        executable=_optional_string(table, "executable", "2dMAIZSIM.exe"),
        run_file=_optional_string(table, "run_file", "run.dat"),
        var_file=_optional_string(table, "var_file", ""),
        soi_file=_optional_string(table, "soi_file", ""),
        minimal_outputs=_optional_bool(table, "minimal_outputs", False),
        max_workers=_optional_int(table, "max_workers", 12),
        timeout_seconds=_optional_float_or_none(table, "timeout_seconds"),
    )


def _load_observation_config(
    raw_config: dict[str, Any],
    config_path: Path,
) -> ObservationConfig:
    table = _required_table(raw_config, "observation")
    observation_file = _required_value(table, "file", "observation")
    return ObservationConfig(file=_resolve_path(observation_file, config_path))


def _load_assimilation_config(raw_config: dict[str, Any]) -> AssimilationConfig:
    table = _optional_table(raw_config, "assimilation")
    return AssimilationConfig(
        n_ensemble=_optional_int(table, "n_ensemble", 100),
        n_iter=_optional_int(table, "n_iter", 3),
        random_seed=_optional_int(table, "random_seed", 20240514),
    )


def _load_juvenile_config(raw_config: dict[str, Any]) -> JuvenileLeavesConfig:
    table = _optional_table(raw_config, "juvenile_leaves")
    candidates = table.get("candidates", (16, 17, 18, 19, 20))
    if not isinstance(candidates, (list, tuple)):
        raise ConfigError("juvenile_leaves.candidates must be an array")
    return JuvenileLeavesConfig(
        candidates=tuple(
            _to_int(value, "juvenile_leaves.candidates")
            for value in candidates
        ),
        enabled=_optional_bool(table, "enabled", True),
    )


def _load_output_config(raw_config: dict[str, Any], config_path: Path) -> OutputConfig:
    table = _optional_table(raw_config, "output")
    run_root = _resolve_path(table.get("run_root", "DA_Framework/runs"), config_path)
    return OutputConfig(
        run_root=run_root,
        experiment_name=_optional_string(table, "experiment_name", "experiment_001"),
    )


def _load_parameters(raw_config: dict[str, Any]) -> tuple[ParameterConfig, ...]:
    raw_parameters = raw_config.get("parameters")
    if raw_parameters is None:
        return _default_parameters()
    if not isinstance(raw_parameters, list):
        raise ConfigError("parameters must be an array of TOML tables")

    parameters = []
    for index, raw_parameter in enumerate(raw_parameters, start=1):
        if not isinstance(raw_parameter, dict):
            raise ConfigError(f"parameters[{index}] must be a TOML table")
        section = f"parameters[{index}]"
        name = str(_required_value(raw_parameter, "name", section))
        target_fields = raw_parameter.get("target_fields", ())
        if not isinstance(target_fields, (list, tuple)):
            raise ConfigError(f"{section}.target_fields must be an array")
        target_fields = tuple(str(field) for field in target_fields)
        if name == "thetaS" and "target_fields" in raw_parameter:
            _validate_theta_s_target_fields(section, target_fields)
        parameters.append(
            ParameterConfig(
                name=name,
                current=_required_float(raw_parameter, "current", section),
                lower=_required_float(raw_parameter, "lower", section),
                upper=_required_float(raw_parameter, "upper", section),
                std=_required_float(raw_parameter, "std", section),
                target_file=_optional_string(raw_parameter, "target_file", ""),
                target_fields=target_fields,
            )
        )
    return tuple(parameters)


def _default_parameters() -> tuple[ParameterConfig, ...]:
    return (
        ParameterConfig("n", 1.56, 1.40, 1.72, 0.08, target_fields=("n",)),
        ParameterConfig(
            "thetaS",
            0.430,
            0.387,
            0.473,
            0.02,
            target_fields=THETA_S_TARGET_FIELDS,
        ),
        ParameterConfig(
            "LM_min",
            125.0,
            112.5,
            130.0,
            5.0,
            target_fields=("LM_min",),
        ),
        ParameterConfig(
            "Rmax_LTAR",
            0.53,
            0.477,
            0.58,
            0.025,
            target_fields=("Rmax_LTAR",),
        ),
        ParameterConfig(
            "StayGreen",
            4.5,
            4.05,
            4.95,
            0.225,
            target_fields=("StayGreen",),
        ),
    )


def _validate_config(config: FrameworkConfig) -> None:
    if config.assimilation.n_ensemble <= 0:
        raise ConfigError("assimilation.n_ensemble must be positive")
    if config.assimilation.n_iter <= 0:
        raise ConfigError("assimilation.n_iter must be positive")
    if config.model.max_workers <= 0:
        raise ConfigError("model.max_workers must be positive")
    if config.model.timeout_seconds is not None and config.model.timeout_seconds <= 0:
        raise ConfigError("model.timeout_seconds must be positive when provided")
    if not config.output.experiment_name.strip():
        raise ConfigError("output.experiment_name must not be empty")
    if not config.parameters:
        raise ConfigError("at least one parameter is required")

    seen_names = set()
    for parameter in config.parameters:
        if parameter.name in seen_names:
            raise ConfigError(f"duplicate parameter name: {parameter.name}")
        seen_names.add(parameter.name)
        if parameter.name == "JuvenileLeaves":
            raise ConfigError(
                "JuvenileLeaves is discrete; configure it under juvenile_leaves "
                "and do not include it in continuous parameters"
            )
        if parameter.lower >= parameter.upper:
            raise ConfigError(f"{parameter.name}: lower must be less than upper")
        if not parameter.lower <= parameter.current <= parameter.upper:
            raise ConfigError(f"{parameter.name}: current must be within bounds")
        if parameter.std <= 0:
            raise ConfigError(f"{parameter.name}: std must be positive")

    unknown_names = seen_names.difference(DEFAULT_PARAMETER_NAME_SET)
    if unknown_names:
        unknown_text = ", ".join(sorted(unknown_names))
        allowed_text = ", ".join(DEFAULT_PARAMETER_NAMES)
        raise ConfigError(
            "unsupported continuous parameter(s): "
            f"{unknown_text}. Allowed parameters are exactly: {allowed_text}"
        )

    missing_names = DEFAULT_PARAMETER_NAME_SET.difference(seen_names)
    if missing_names:
        missing_text = ", ".join(
            name for name in DEFAULT_PARAMETER_NAMES if name in missing_names
        )
        allowed_text = ", ".join(DEFAULT_PARAMETER_NAMES)
        raise ConfigError(
            "continuous parameters must include exactly "
            f"{allowed_text}; missing: {missing_text}"
        )

    if not config.juvenile_leaves.candidates:
        raise ConfigError("juvenile_leaves.candidates must not be empty")


def _validate_theta_s_target_fields(
    section: str,
    target_fields: tuple[str, ...],
) -> None:
    if target_fields != THETA_S_TARGET_FIELDS:
        expected = ", ".join(THETA_S_TARGET_FIELDS)
        actual = ", ".join(target_fields) if target_fields else "<empty>"
        raise ConfigError(
            f"{section}.target_fields for thetaS must be exactly "
            f"{expected}; got: {actual}"
        )


def _resolve_path(value: Any, config_path: Path) -> Path:
    raw_path = Path(str(value)).expanduser()
    if raw_path.is_absolute():
        return raw_path

    config_dir = config_path.parent.resolve()
    cwd = Path.cwd().resolve()
    roots = []
    if config_dir.name == "DA_Framework":
        roots.append(config_dir.parent)
    roots.extend([cwd, config_dir])

    seen_roots = set()
    candidates = []
    for root in roots:
        if root in seen_roots:
            continue
        seen_roots.add(root)
        candidates.append(root / raw_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate

    if config_dir.name == "DA_Framework" and raw_path.parts:
        first_part = raw_path.parts[0]
        if first_part in {"DA_Framework", "示例输入", "Crop source", "Soil Source"}:
            return config_dir.parent / raw_path
    return config_dir / raw_path


def _required_table(raw_config: dict[str, Any], key: str) -> dict[str, Any]:
    table = raw_config.get(key)
    if not isinstance(table, dict):
        raise ConfigError(f"missing required [{key}] table")
    return table


def _optional_table(raw_config: dict[str, Any], key: str) -> dict[str, Any]:
    table = raw_config.get(key, {})
    if not isinstance(table, dict):
        raise ConfigError(f"[{key}] must be a TOML table")
    return table


def _required_value(table: dict[str, Any], key: str, section: str) -> Any:
    if key not in table:
        raise ConfigError(f"missing required {section}.{key}")
    return table[key]


def _required_float(table: dict[str, Any], key: str, section: str) -> float:
    return _to_float(_required_value(table, key, section), f"{section}.{key}")


def _optional_string(table: dict[str, Any], key: str, default: str) -> str:
    value = table.get(key, default)
    if value is None:
        return default
    return str(value)


def _optional_bool(table: dict[str, Any], key: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be a boolean")
    return value


def _optional_int(table: dict[str, Any], key: str, default: int) -> int:
    return _to_int(table.get(key, default), key)


def _optional_float_or_none(table: dict[str, Any], key: str) -> float | None:
    if key not in table:
        return None
    return _to_float(table[key], key)


def _to_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{name} must be an integer")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if integer != value and not isinstance(value, str):
        raise ConfigError(f"{name} must be an integer")
    return integer


def _to_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ConfigError(f"{name} must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be numeric") from exc
