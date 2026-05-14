"""Metrics used by the MAIZSIM IES workflow."""

from __future__ import annotations

import math
from collections.abc import Iterable


def rmse(simulated: Iterable[float], observed: Iterable[float]) -> float:
    """Return root mean squared error for paired simulated and observed values."""
    simulated_values = _as_float_list(simulated, "simulated")
    observed_values = _as_float_list(observed, "observed")
    _validate_pair_lengths(simulated_values, observed_values)

    squared_error = [
        (sim_value - obs_value) ** 2
        for sim_value, obs_value in zip(simulated_values, observed_values)
    ]
    return math.sqrt(sum(squared_error) / len(squared_error))


def normalized_rmse(
    simulated: Iterable[float],
    observed: Iterable[float],
    std: Iterable[float],
) -> float:
    """Return RMSE after scaling each residual by observation standard deviation."""
    simulated_values = _as_float_list(simulated, "simulated")
    observed_values = _as_float_list(observed, "observed")
    std_values = _as_float_list(std, "std")
    _validate_pair_lengths(simulated_values, observed_values)
    _validate_pair_lengths(simulated_values, std_values)

    normalized_error = []
    for sim_value, obs_value, std_value in zip(
        simulated_values,
        observed_values,
        std_values,
    ):
        if std_value <= 0:
            raise ValueError("std values must be positive")
        normalized_error.append(((sim_value - obs_value) / std_value) ** 2)
    return math.sqrt(sum(normalized_error) / len(normalized_error))


def _as_float_list(values: Iterable[float], name: str) -> list[float]:
    result = []
    for value in values:
        try:
            float_value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} contains a non-numeric value: {value!r}") from exc
        if not math.isfinite(float_value):
            raise ValueError(f"{name} contains a non-finite value: {value!r}")
        result.append(float_value)
    return result


def _validate_pair_lengths(left: list[float], right: list[float]) -> None:
    if not left:
        raise ValueError("metrics require at least one paired value")
    if len(left) != len(right):
        raise ValueError(
            "metrics require sequences with the same length: "
            f"{len(left)} != {len(right)}"
        )
