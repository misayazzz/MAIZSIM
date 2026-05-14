"""Lightweight orchestration for MAIZSIM IES experiments."""

from __future__ import annotations

import csv
import importlib
import inspect
import math
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import FrameworkConfig, ParameterConfig
from .errors import (
    ModelRunError,
    ObservationError,
    OutputReadError,
    ParameterWriteError,
    WorkflowError,
)
from .metrics import normalized_rmse, rmse


@dataclass(frozen=True)
class ObservationData:
    rows: tuple[dict[str, str], ...]
    values: tuple[float, ...]
    std: tuple[float, ...]
    ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowResult:
    run_dir: Path
    parameter_files: tuple[Path, ...]
    forecast_files: tuple[Path, ...]
    rmse_file: Path
    dry_run: bool = False
    juvenile_leaves: int | None = None


def run_single_ies(
    config: FrameworkConfig,
    dry_run: bool = False,
    juvenile_leaves: int | None = None,
) -> WorkflowResult:
    """Run one continuous-parameter IES experiment."""
    observations = _load_observations(config)
    parameter_sets = _generate_prior(config)
    experiment_dir = _experiment_dir(config, juvenile_leaves)
    stats_dir = experiment_dir / "statistics_da"
    update_dir = stats_dir / "Kalman_Update"
    results_dir = experiment_dir / "results"
    update_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    parameter_files = []
    forecast_files = []
    initial_file = stats_dir / "Initial-Params.txt"
    _write_parameter_file(
        initial_file,
        parameter_sets,
        config.parameters,
        juvenile_leaves=juvenile_leaves,
    )
    parameter_files.append(initial_file)

    rmse_rows = []
    if dry_run:
        rmse_file = results_dir / "rmse_summary.csv"
        rmse_rows.append(
            {
                "iteration": "dry_run",
                "rmse": "",
                "normalized_rmse": "",
                "status": "dry_run_no_forecast",
                "message": (
                    f"loaded {len(observations.values)} observations and generated "
                    f"{len(parameter_sets)} prior ensemble members"
                ),
                "juvenile_leaves": _format_optional_int(juvenile_leaves),
            }
        )
        _write_rmse_summary(rmse_file, rmse_rows)
        return WorkflowResult(
            run_dir=experiment_dir,
            parameter_files=tuple(parameter_files),
            forecast_files=tuple(forecast_files),
            rmse_file=rmse_file,
            dry_run=True,
            juvenile_leaves=juvenile_leaves,
        )

    _validate_model_inputs(config)

    for iteration in range(config.assimilation.n_iter):
        forecast_matrix = _run_forecast_iteration(
            config,
            parameter_sets,
            observations,
            iteration,
            experiment_dir,
            juvenile_leaves,
        )
        forecast_file = results_dir / f"forecast_matrix_iter_{iteration}.csv"
        _write_forecast_matrix(forecast_file, forecast_matrix, observations)
        forecast_files.append(forecast_file)

        simulated_mean = _ensemble_mean(forecast_matrix)
        normalized_error = normalized_rmse(
            simulated_mean,
            observations.values,
            observations.std,
        )
        rmse_rows.append(
            {
                "iteration": str(iteration),
                "rmse": f"{rmse(simulated_mean, observations.values):.10g}",
                "normalized_rmse": f"{normalized_error:.10g}",
                "status": "forecast_complete",
                "message": "",
                "juvenile_leaves": _format_optional_int(juvenile_leaves),
            }
        )

        parameter_sets = _update_parameter_sets(
            config,
            parameter_sets,
            forecast_matrix,
            observations,
            iteration,
        )
        iter_file = update_dir / f"Iter-{iteration + 1}-Params.txt"
        _write_parameter_file(
            iter_file,
            parameter_sets,
            config.parameters,
            juvenile_leaves=juvenile_leaves,
        )
        parameter_files.append(iter_file)

    rmse_file = results_dir / "rmse_summary.csv"
    _write_rmse_summary(rmse_file, rmse_rows)
    return WorkflowResult(
        run_dir=experiment_dir,
        parameter_files=tuple(parameter_files),
        forecast_files=tuple(forecast_files),
        rmse_file=rmse_file,
        juvenile_leaves=juvenile_leaves,
    )


def run_juvenile_enum(
    config: FrameworkConfig,
    dry_run: bool = False,
) -> tuple[WorkflowResult, ...]:
    """Run the outer JuvenileLeaves enumeration without continuous updates."""
    if not config.juvenile_leaves.enabled:
        raise WorkflowError("juvenile_leaves.enabled is false; enumeration is disabled")

    results = []
    for candidate in config.juvenile_leaves.candidates:
        results.append(
            run_single_ies(
                config,
                dry_run=dry_run,
                juvenile_leaves=candidate,
            )
        )
    _write_juvenile_enum_summary(config, results)
    return tuple(results)


def _load_observations(config: FrameworkConfig) -> ObservationData:
    module = _optional_module("observation")
    if module is not None:
        function = _first_function(
            module,
            ("load_observations", "read_observations", "read_observations_csv"),
        )
        if function is not None:
            result = _invoke(
                function,
                config=config,
                path=config.observation.file,
                observation_file=config.observation.file,
            )
            return _normalize_observations(result)
    return _read_observations_csv(config.observation.file)


def _generate_prior(config: FrameworkConfig) -> list[dict[str, float]]:
    module = _optional_module("prior")
    if module is not None:
        function = _first_function(
            module,
            ("generate_prior", "build_prior_ensemble", "sample_uniform_prior"),
        )
        if function is not None:
            result = _invoke(
                function,
                config=config,
                parameters=config.parameters,
                n_ensemble=config.assimilation.n_ensemble,
                random_seed=config.assimilation.random_seed,
                rng=config.assimilation.random_seed,
            )
            return _normalize_parameter_sets(result, config.parameters)
    return _generate_prior_fallback(config)


def _run_forecast_iteration(
    config: FrameworkConfig,
    parameter_sets: list[dict[str, float]],
    observations: ObservationData,
    iteration: int,
    experiment_dir: Path,
    juvenile_leaves: int | None,
) -> list[list[float]]:
    ensemble_module = _optional_module("ensemble")
    if ensemble_module is None:
        raise WorkflowError(
            "forecast requires da_framework.ensemble. Expected a function named "
            "run_forecast, run_ensemble_forecast, or forecast_ensemble."
        )

    forecast_function = _first_function(
        ensemble_module,
        ("run_forecast", "run_ensemble_forecast", "forecast_ensemble"),
    )
    if forecast_function is None:
        return _run_forecast_with_standard_modules(
            config,
            parameter_sets,
            observations,
            iteration,
            experiment_dir,
            juvenile_leaves,
            ensemble_module,
        )

    forecast_result = _invoke(
        forecast_function,
        config=config,
        parameter_sets=parameter_sets,
        observations=observations,
        iteration=iteration,
        experiment_dir=experiment_dir,
        juvenile_leaves=juvenile_leaves,
    )
    try:
        return _normalize_forecast_matrix(
            forecast_result,
            n_observations=len(observations.values),
            n_ensemble=len(parameter_sets),
        )
    except OutputReadError:
        pass

    output_module = _optional_module("output_reader")
    if output_module is None:
        raise WorkflowError(
            "ensemble forecast did not return a matrix, and "
            "da_framework.output_reader is not available"
        )
    read_function = _first_function(
        output_module,
        (
            "read_observation_matrix",
            "read_forecast_matrix",
            "map_outputs_to_observations",
        ),
    )
    if read_function is None:
        raise WorkflowError(
            "da_framework.output_reader is present but no observation-matrix "
            "reader function was found"
        )
    matrix_result = _invoke(
        read_function,
        config=config,
        forecast_result=forecast_result,
        observations=observations,
        iteration=iteration,
        experiment_dir=experiment_dir,
        juvenile_leaves=juvenile_leaves,
    )
    return _normalize_forecast_matrix(
        matrix_result,
        n_observations=len(observations.values),
        n_ensemble=len(parameter_sets),
    )


def _update_parameter_sets(
    config: FrameworkConfig,
    parameter_sets: list[dict[str, float]],
    forecast_matrix: list[list[float]],
    observations: ObservationData,
    iteration: int,
) -> list[dict[str, float]]:
    module = _optional_module("update")
    if module is None:
        raise WorkflowError(
            "parameter update requires da_framework.update. Expected a function named "
            "update_parameters, ies_update, or update_ensemble."
        )
    function = _first_function(
        module,
        ("update_parameters", "ies_update", "update_ensemble"),
    )
    if function is None:
        raise WorkflowError(
            "da_framework.update is present but no update function was found"
        )

    parameter_names = [parameter.name for parameter in config.parameters]
    if "x_forecast" in inspect.signature(function).parameters:
        result = _invoke(
            function,
            x_forecast=_parameter_sets_to_matrix(parameter_sets, parameter_names),
            y_forecast=forecast_matrix,
            observations=observations.values,
            observation_std=observations.std,
            parameter_names=parameter_names,
            bounds_by_name=_bounds_by_name(config.parameters, module),
            rng=config.assimilation.random_seed + iteration + 1,
            n_iter_scale=config.assimilation.n_iter,
        )
        updated_sets = _parameter_sets_from_update_result(result, parameter_names)
    else:
        result = _invoke(
            function,
            config=config,
            parameter_sets=parameter_sets,
            forecast_matrix=forecast_matrix,
            observations=observations,
            observed=observations.values,
            observation_std=observations.std,
            iteration=iteration,
        )
        updated_sets = _normalize_parameter_sets(result, config.parameters)
    return [
        _apply_parameter_bounds(updated_set, previous_set, config.parameters)
        for updated_set, previous_set in zip(updated_sets, parameter_sets)
    ]


def _run_forecast_with_standard_modules(
    config: FrameworkConfig,
    parameter_sets: list[dict[str, float]],
    observations: ObservationData,
    iteration: int,
    experiment_dir: Path,
    juvenile_leaves: int | None,
    ensemble_module: Any,
) -> list[list[float]]:
    required_names = ("prepare_ensemble", "write_ensemble_parameters")
    missing_names = [
        name
        for name in required_names
        if not callable(getattr(ensemble_module, name, None))
    ]
    output_module = _optional_module("output_reader")
    if missing_names or output_module is None:
        missing_text = ", ".join(missing_names) if missing_names else "output_reader"
        raise WorkflowError(
            "forecast requires a high-level ensemble forecast function or the "
            f"standard module functions. Missing: {missing_text}"
        )
    build_vector = getattr(output_module, "build_simulation_vector", None)
    if not callable(build_vector):
        raise WorkflowError(
            "da_framework.output_reader must provide build_simulation_vector"
        )

    ensemble_dir = experiment_dir / "ensemble" / f"iter_{iteration:02d}"
    member_dirs = _prepare_ensemble_directories(
        config,
        ensemble_dir,
        len(parameter_sets),
        ensemble_module,
    )
    member_parameter_sets = _with_juvenile_leaves(parameter_sets, juvenile_leaves)
    ensemble_module.write_ensemble_parameters(
        member_dirs,
        member_parameter_sets,
        _model_parameter_file(config, ".var", "VAR"),
        _model_parameter_file(config, ".soi", "SOI"),
    )
    _run_member_models(config, member_dirs, ensemble_module)
    member_vectors = []
    for member_dir in member_dirs:
        try:
            vector = build_vector(member_dir, observations.rows)
        except Exception as exc:
            raise OutputReadError(
                f"failed to read outputs for ensemble member {member_dir}: {exc}"
            ) from exc
        member_vectors.append([float(value) for value in vector])
    return _normalize_forecast_matrix(
        member_vectors,
        n_observations=len(observations.values),
        n_ensemble=len(parameter_sets),
        preferred_orientation="ensemble_x_observations",
    )


def _prepare_ensemble_directories(
    config: FrameworkConfig,
    ensemble_dir: Path,
    n_ensemble: int,
    ensemble_module: Any,
) -> list[Path]:
    prepare_ensemble = ensemble_module.prepare_ensemble
    kwargs = _prepare_ensemble_kwargs(prepare_ensemble, config)
    return prepare_ensemble(
        config.model.base_run_dir,
        ensemble_dir,
        n_ensemble,
        **kwargs,
    )


def _prepare_ensemble_kwargs(function: Any, config: FrameworkConfig) -> dict[str, Any]:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return {}

    accepts_keywords = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    kwargs = {}
    if accepts_keywords or "minimal_outputs" in signature.parameters:
        kwargs["minimal_outputs"] = config.model.minimal_outputs
    if accepts_keywords or "run_file" in signature.parameters:
        kwargs["run_file"] = config.model.run_file
    return kwargs


def _read_observations_csv(path: Path) -> ObservationData:
    if not path.exists():
        raise ObservationError(f"observation file does not exist: {path}")
    required_columns = {
        "date",
        "variable",
        "depth_top_cm",
        "depth_bottom_cm",
        "value",
        "std",
    }

    with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        if reader.fieldnames is None:
            raise ObservationError(f"observation file has no header: {path}")
        missing_columns = required_columns.difference(reader.fieldnames)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ObservationError(f"observation file is missing columns: {missing}")

        valid_rows = []
        for line_number, row in enumerate(reader, start=2):
            value = _parse_optional_float(row.get("value"))
            std_value = _parse_optional_float(row.get("std"))
            if value is None or std_value is None:
                continue
            if std_value <= 0:
                continue
            normalized_row = {
                "date": str(row.get("date", "")).strip(),
                "variable": str(row.get("variable", "")).strip(),
                "depth_top_cm": str(row.get("depth_top_cm", "")).strip(),
                "depth_bottom_cm": str(row.get("depth_bottom_cm", "")).strip(),
                "value": f"{value:.12g}",
                "std": f"{std_value:.12g}",
            }
            if not normalized_row["date"] or not normalized_row["variable"]:
                raise ObservationError(
                    f"observation row {line_number} must include date and variable"
                )
            normalized_row["observation_id"] = _observation_id(normalized_row)
            valid_rows.append(normalized_row)

    valid_rows.sort(key=_observation_sort_key)
    if not valid_rows:
        raise ObservationError("no valid observations found; require value and std > 0")

    values = tuple(float(row["value"]) for row in valid_rows)
    std = tuple(float(row["std"]) for row in valid_rows)
    ids = tuple(row["observation_id"] for row in valid_rows)
    return ObservationData(rows=tuple(valid_rows), values=values, std=std, ids=ids)


def _generate_prior_fallback(config: FrameworkConfig) -> list[dict[str, float]]:
    random_source = random.Random(config.assimilation.random_seed)
    parameter_sets = []
    for _ in range(config.assimilation.n_ensemble):
        member = {}
        for parameter in config.parameters:
            sampled_value = random_source.gauss(parameter.current, parameter.std)
            member[parameter.name] = _clip(
                sampled_value,
                parameter.lower,
                parameter.upper,
            )
        parameter_sets.append(member)
    return parameter_sets


def _validate_model_inputs(config: FrameworkConfig) -> None:
    base_run_dir = config.model.base_run_dir
    if not base_run_dir.is_dir():
        raise ModelRunError(
            "base_run_dir does not exist or is not a directory: "
            f"{base_run_dir}"
        )

    required_files = [
        ("model.executable", config.model.executable),
        ("model.run_file", config.model.run_file),
    ]
    if config.model.var_file:
        required_files.append(("model.var_file", config.model.var_file))
    if config.model.soi_file:
        required_files.append(("model.soi_file", config.model.soi_file))
    for parameter in config.parameters:
        if parameter.target_file:
            required_files.append(
                (f"{parameter.name}.target_file", parameter.target_file)
            )

    missing = []
    for label, file_name in required_files:
        candidate = _resolve_model_file(base_run_dir, file_name)
        if not candidate.exists():
            missing.append(f"{label}: {candidate}")

    if not _has_var_requirement(config) and not any(base_run_dir.glob("*.var")):
        missing.append("*.var: no cultivar file found and model.var_file is empty")
    if not _has_soi_requirement(config) and not any(base_run_dir.glob("*.soi")):
        missing.append("*.soi: no soil file found and model.soi_file is empty")

    if missing:
        missing_text = "\n  - ".join(missing)
        raise ModelRunError(
            "base run is not self-contained; forecast cannot start. Missing:\n"
            f"  - {missing_text}\n"
            "Provide a base_run_dir containing run.dat, .var, .soi, executable, dll, "
            "weather/timing files, and other files referenced by run.dat."
        )


def _write_parameter_file(
    path: Path,
    parameter_sets: list[dict[str, float]],
    parameters: tuple[ParameterConfig, ...],
    juvenile_leaves: int | None,
) -> None:
    fieldnames = ["member"]
    if juvenile_leaves is not None:
        fieldnames.append("JuvenileLeaves")
    fieldnames.extend(parameter.name for parameter in parameters)

    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for index, parameter_set in enumerate(parameter_sets, start=1):
            row = {"member": f"{index:06d}"}
            if juvenile_leaves is not None:
                row["JuvenileLeaves"] = str(juvenile_leaves)
            for parameter in parameters:
                row[parameter.name] = f"{parameter_set[parameter.name]:.12g}"
            writer.writerow(row)


def _write_forecast_matrix(
    path: Path,
    forecast_matrix: list[list[float]],
    observations: ObservationData,
) -> None:
    if len(forecast_matrix) != len(observations.rows):
        raise OutputReadError(
            "forecast matrix row count does not match observations: "
            f"{len(forecast_matrix)} != {len(observations.rows)}"
        )
    member_count = len(forecast_matrix[0]) if forecast_matrix else 0
    member_columns = [f"member_{index:06d}" for index in range(1, member_count + 1)]
    fieldnames = [
        "observation_id",
        "date",
        "variable",
        "depth_top_cm",
        "depth_bottom_cm",
        "observed",
        "std",
        *member_columns,
    ]

    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for observation_row, matrix_row in zip(observations.rows, forecast_matrix):
            row = {
                "observation_id": observation_row["observation_id"],
                "date": observation_row["date"],
                "variable": observation_row["variable"],
                "depth_top_cm": observation_row["depth_top_cm"],
                "depth_bottom_cm": observation_row["depth_bottom_cm"],
                "observed": observation_row["value"],
                "std": observation_row["std"],
            }
            for column, value in zip(member_columns, matrix_row):
                row[column] = f"{value:.12g}"
            writer.writerow(row)


def _write_rmse_summary(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "iteration",
        "rmse",
        "normalized_rmse",
        "status",
        "message",
        "juvenile_leaves",
    ]
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _write_juvenile_enum_summary(
    config: FrameworkConfig,
    results: list[WorkflowResult],
) -> None:
    enum_dir = config.output.run_root / config.output.experiment_name
    enum_dir.mkdir(parents=True, exist_ok=True)
    summary_file = enum_dir / "juvenile_enum_summary.csv"
    with summary_file.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            fieldnames=["JuvenileLeaves", "experiment_dir", "rmse_summary", "dry_run"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "JuvenileLeaves": _format_optional_int(result.juvenile_leaves),
                    "experiment_dir": str(result.run_dir),
                    "rmse_summary": str(result.rmse_file),
                    "dry_run": str(result.dry_run).lower(),
                }
            )


def _normalize_observations(result: Any) -> ObservationData:
    if isinstance(result, ObservationData):
        return result
    if (
        hasattr(result, "specs")
        and hasattr(result, "values")
        and hasattr(result, "std")
    ):
        values = tuple(float(value) for value in result.values)
        std = tuple(float(value) for value in result.std)
        rows = []
        for spec, value, std_value in zip(result.specs, values, std):
            row = _row_from_observation_spec(spec, value, std_value)
            rows.append(row)
        ids = tuple(row["observation_id"] for row in rows)
        return ObservationData(rows=tuple(rows), values=values, std=std, ids=ids)
    if hasattr(result, "rows") and hasattr(result, "values") and hasattr(result, "std"):
        rows = tuple(dict(row) for row in result.rows)
        values = tuple(float(value) for value in result.values)
        std = tuple(float(value) for value in result.std)
        ids = tuple(
            row.get("observation_id", _observation_id(row))
            for row in rows
        )
        return ObservationData(rows=rows, values=values, std=std, ids=ids)
    if isinstance(result, (list, tuple)):
        if len(result) == 3 and not isinstance(result[0], dict):
            rows, values, std = result
            rows = tuple(dict(row) for row in rows)
            ids = tuple(
                row.get("observation_id", _observation_id(row))
                for row in rows
            )
            return ObservationData(
                rows=rows,
                values=tuple(float(value) for value in values),
                std=tuple(float(value) for value in std),
                ids=ids,
            )
        if result and isinstance(result[0], dict):
            rows = tuple(dict(row) for row in result)
            values = tuple(float(row["value"]) for row in rows)
            std = tuple(float(row["std"]) for row in rows)
            ids = tuple(
                row.get("observation_id", _observation_id(row))
                for row in rows
            )
            return ObservationData(rows=rows, values=values, std=std, ids=ids)
    raise ObservationError(
        "observation module returned an unsupported object; expected ObservationData, "
        "(rows, values, std), or a list of row dictionaries"
    )


def _normalize_parameter_sets(
    result: Any,
    parameters: tuple[ParameterConfig, ...],
) -> list[dict[str, float]]:
    parameter_names = [parameter.name for parameter in parameters]
    if hasattr(result, "to_dict"):
        result = result.to_dict(orient="records")
    if not isinstance(result, (list, tuple)):
        raise WorkflowError("parameter ensemble must be a list of dictionaries")

    normalized_sets = []
    for index, item in enumerate(result, start=1):
        if not isinstance(item, dict):
            raise WorkflowError(f"parameter member {index} is not a dictionary")
        normalized_member = {}
        for parameter_name in parameter_names:
            if parameter_name not in item:
                raise WorkflowError(
                    f"parameter member {index} is missing {parameter_name}"
                )
            normalized_member[parameter_name] = float(item[parameter_name])
        normalized_sets.append(normalized_member)
    return normalized_sets


def _parameter_sets_from_update_result(
    result: Any,
    parameter_names: list[str],
) -> list[dict[str, float]]:
    if hasattr(result, "updated_parameters"):
        result = result.updated_parameters
    try:
        rows = [list(row) for row in result]
    except TypeError as exc:
        raise WorkflowError("updated parameters are not iterable") from exc

    if len(rows) == len(parameter_names):
        columns = list(zip(*rows))
    else:
        columns = rows
    parameter_sets = []
    for member_values in columns:
        if len(member_values) != len(parameter_names):
            raise WorkflowError("updated parameter matrix has an invalid shape")
        parameter_sets.append(
            {
                name: float(value)
                for name, value in zip(parameter_names, member_values)
            }
        )
    return parameter_sets


def _parameter_sets_to_matrix(
    parameter_sets: list[dict[str, float]],
    parameter_names: list[str],
) -> list[list[float]]:
    return [
        [float(parameter_set[name]) for parameter_set in parameter_sets]
        for name in parameter_names
    ]


def _bounds_by_name(
    parameters: tuple[ParameterConfig, ...],
    update_module: Any,
) -> dict[str, Any]:
    bounds_class = getattr(update_module, "ParameterBounds", None)
    bounds = {}
    for parameter in parameters:
        if callable(bounds_class):
            bounds[parameter.name] = bounds_class(
                parameter.name,
                parameter.lower,
                parameter.upper,
            )
        else:
            bounds[parameter.name] = {
                "lower": parameter.lower,
                "upper": parameter.upper,
            }
    return bounds


def _normalize_forecast_matrix(
    result: Any,
    n_observations: int,
    n_ensemble: int,
    preferred_orientation: str | None = None,
) -> list[list[float]]:
    if isinstance(result, dict):
        for key in ("forecast_matrix", "matrix", "values"):
            if key in result:
                result = result[key]
                break
    elif hasattr(result, "forecast_matrix"):
        result = result.forecast_matrix
    elif hasattr(result, "matrix"):
        result = result.matrix
    elif hasattr(result, "to_numpy"):
        result = result.to_numpy()

    rows = _matrix_to_float_rows(result)

    valid_orientations = {
        "observations_x_ensemble",
        "ensemble_x_observations",
    }
    if (
        preferred_orientation is not None
        and preferred_orientation not in valid_orientations
    ):
        raise OutputReadError(
            "unsupported forecast matrix orientation preference: "
            f"{preferred_orientation!r}"
        )

    observations_by_ensemble = (
        len(rows) == n_observations
        and all(len(row) == n_ensemble for row in rows)
    )
    ensemble_by_observations = (
        len(rows) == n_ensemble
        and all(len(row) == n_observations for row in rows)
    )

    if preferred_orientation == "observations_x_ensemble":
        if observations_by_ensemble:
            return rows
        raise _forecast_shape_error(n_observations, n_ensemble)

    if preferred_orientation == "ensemble_x_observations":
        if ensemble_by_observations:
            return [list(column) for column in zip(*rows)]
        raise _forecast_shape_error(n_observations, n_ensemble)

    if observations_by_ensemble:
        return rows
    if ensemble_by_observations:
        return [list(column) for column in zip(*rows)]
    raise _forecast_shape_error(n_observations, n_ensemble)


def _forecast_shape_error(
    n_observations: int,
    n_ensemble: int,
) -> OutputReadError:
    return OutputReadError(
        "forecast matrix shape must be observations x ensemble "
        f"({n_observations} x {n_ensemble}) or its transpose"
    )


def _run_member_models(
    config: FrameworkConfig,
    member_dirs: list[Path],
    ensemble_module: Any,
) -> None:
    use_default_runner = (
        config.model.executable == "2dMAIZSIM.exe"
        and config.model.run_file == "run.dat"
        and callable(getattr(ensemble_module, "run_ensemble", None))
    )
    if use_default_runner:
        run_results = ensemble_module.run_ensemble(
            member_dirs,
            max_workers=config.model.max_workers,
            timeout_seconds=config.model.timeout_seconds,
        )
    else:
        run_results = _run_member_models_directly(config, member_dirs)

    failed = [
        result
        for result in run_results
        if not getattr(result, "success", False)
    ]
    if failed:
        messages = []
        for result in failed[:5]:
            messages.append(
                f"{getattr(result, 'member_id', '?')}: "
                f"{getattr(result, 'message', '')} "
                f"(stderr={getattr(result, 'stderr_path', '')})"
            )
        raise ModelRunError(
            "one or more ensemble members failed: " + "; ".join(messages)
        )

    check_outputs = getattr(ensemble_module, "check_ensemble_outputs", None)
    if callable(check_outputs):
        try:
            check_outputs(member_dirs)
        except Exception as exc:
            raise ModelRunError(f"ensemble output check failed: {exc}") from exc


def _run_member_models_directly(
    config: FrameworkConfig,
    member_dirs: list[Path],
) -> list[Any]:
    model_runner = _optional_module("model_runner")
    if model_runner is None or not callable(getattr(model_runner, "run_model", None)):
        raise WorkflowError(
            "non-default executable/run_file requires "
            "da_framework.model_runner.run_model"
        )

    run_model = model_runner.run_model
    with ThreadPoolExecutor(max_workers=config.model.max_workers) as executor:
        futures = [
            executor.submit(
                run_model,
                member_dir,
                executable=config.model.executable,
                run_file=config.model.run_file,
                timeout_seconds=config.model.timeout_seconds,
            )
            for member_dir in member_dirs
        ]
        return [future.result() for future in futures]


def _with_juvenile_leaves(
    parameter_sets: list[dict[str, float]],
    juvenile_leaves: int | None,
) -> list[dict[str, float]]:
    if juvenile_leaves is None:
        return parameter_sets
    return [
        {**parameter_set, "JuvenileLeaves": float(juvenile_leaves)}
        for parameter_set in parameter_sets
    ]


def _model_parameter_file(
    config: FrameworkConfig,
    suffix: str,
    label: str,
) -> str:
    if suffix == ".var" and config.model.var_file:
        return config.model.var_file
    if suffix == ".soi" and config.model.soi_file:
        return config.model.soi_file

    target_files = [
        parameter.target_file
        for parameter in config.parameters
        if parameter.target_file.lower().endswith(suffix)
    ]
    if target_files:
        return target_files[0]

    candidates = sorted(config.model.base_run_dir.glob(f"*{suffix}"))
    if len(candidates) == 1:
        return candidates[0].name
    raise ParameterWriteError(
        f"{label} file is not configured; set model.{suffix[1:]}_file or "
        f"parameter target_file"
    )


def _matrix_to_float_rows(result: Any) -> list[list[float]]:
    if result is None:
        raise OutputReadError("forecast matrix is None")
    try:
        rows = list(result)
    except TypeError as exc:
        raise OutputReadError("forecast matrix is not iterable") from exc
    matrix = []
    for row in rows:
        try:
            values = list(row)
        except TypeError as exc:
            raise OutputReadError("forecast matrix row is not iterable") from exc
        matrix_row = []
        for value in values:
            float_value = float(value)
            if not math.isfinite(float_value):
                raise OutputReadError("forecast matrix contains non-finite values")
            matrix_row.append(float_value)
        matrix.append(matrix_row)
    return matrix


def _apply_parameter_bounds(
    parameter_set: dict[str, float],
    previous_set: dict[str, float],
    parameters: tuple[ParameterConfig, ...],
) -> dict[str, float]:
    bounded = {}
    for parameter in parameters:
        value = parameter_set[parameter.name]
        if parameter.lower <= value <= parameter.upper:
            bounded[parameter.name] = value
            continue
        previous = previous_set.get(parameter.name, parameter.current)
        if value < parameter.lower:
            bounded[parameter.name] = (previous + parameter.lower) / 2
        else:
            bounded[parameter.name] = (previous + parameter.upper) / 2
        bounded[parameter.name] = _clip(
            bounded[parameter.name],
            parameter.lower,
            parameter.upper,
        )
    return bounded


def _ensemble_mean(forecast_matrix: list[list[float]]) -> list[float]:
    means = []
    for row in forecast_matrix:
        if not row:
            raise OutputReadError("forecast matrix has an empty ensemble row")
        means.append(sum(row) / len(row))
    return means


def _optional_module(name: str) -> Any:
    try:
        return importlib.import_module(f".{name}", package=__package__)
    except ModuleNotFoundError as exc:
        expected_name = f"{__package__}.{name}"
        if exc.name == expected_name:
            return None
        raise


def _first_function(module: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        function = getattr(module, name, None)
        if callable(function):
            return function
    return None


def _invoke(function: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(function)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return function(**kwargs)

    accepted_kwargs = {
        name: value
        for name, value in kwargs.items()
        if name in signature.parameters
    }
    return function(**accepted_kwargs)


def _experiment_dir(config: FrameworkConfig, juvenile_leaves: int | None) -> Path:
    if juvenile_leaves is None:
        return config.output.run_root / config.output.experiment_name
    return (
        config.output.run_root
        / f"{config.output.experiment_name}_JL{juvenile_leaves}"
    )


def _observation_id(row: dict[str, str]) -> str:
    return "|".join(
        [
            str(row.get("date", "")).strip(),
            str(row.get("variable", "")).strip(),
            str(row.get("depth_top_cm", "")).strip(),
            str(row.get("depth_bottom_cm", "")).strip(),
        ]
    )


def _row_from_observation_spec(spec: Any, value: float, std: float) -> dict[str, str]:
    row = {
        "date": _format_spec_value(getattr(spec, "date", "")),
        "variable": _format_spec_value(getattr(spec, "variable", "")),
        "depth_top_cm": _format_spec_value(getattr(spec, "depth_top_cm", "")),
        "depth_bottom_cm": _format_spec_value(getattr(spec, "depth_bottom_cm", "")),
        "value": f"{value:.12g}",
        "std": f"{std:.12g}",
    }
    row["observation_id"] = _observation_id(row)
    return row


def _format_spec_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _observation_sort_key(row: dict[str, str]) -> tuple[str, str, float, float]:
    return (
        row["date"],
        row["variable"],
        _sort_float(row["depth_top_cm"]),
        _sort_float(row["depth_bottom_cm"]),
    )


def _sort_float(value: str) -> float:
    parsed_value = _parse_optional_float(value)
    if parsed_value is None:
        return -math.inf
    return parsed_value


def _parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed_value = float(text)
    except ValueError as exc:
        raise ObservationError(f"non-numeric observation value: {value!r}") from exc
    if not math.isfinite(parsed_value):
        raise ObservationError(f"non-finite observation value: {value!r}")
    return parsed_value


def _resolve_model_file(base_run_dir: Path, file_name: str) -> Path:
    path = Path(file_name)
    if path.is_absolute():
        return path
    return base_run_dir / path


def _has_var_requirement(config: FrameworkConfig) -> bool:
    return bool(config.model.var_file) or any(
        parameter.target_file.lower().endswith(".var")
        for parameter in config.parameters
    )


def _has_soi_requirement(config: FrameworkConfig) -> bool:
    return bool(config.model.soi_file) or any(
        parameter.target_file.lower().endswith(".soi")
        for parameter in config.parameters
    )


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _format_optional_int(value: int | None) -> str:
    if value is None:
        return ""
    return str(value)
