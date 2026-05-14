"""Run MAIZSIM model members and validate expected outputs."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ModelRunResult:
    """Result metadata for one external model run."""

    member_id: str
    run_dir: Path
    returncode: int
    stdout_path: Path
    stderr_path: Path
    success: bool
    message: str


def run_model(
    run_dir,
    executable="2dMAIZSIM.exe",
    run_file="run.dat",
    timeout_seconds=None,
) -> ModelRunResult:
    """Run MAIZSIM in ``run_dir`` and capture stdout/stderr logs."""
    run_path = Path(run_dir).expanduser().resolve()
    member_id = run_path.name
    stdout_path = run_path / "logs" / "stdout.txt"
    stderr_path = run_path / "logs" / "stderr.txt"

    if not run_path.is_dir():
        message = f"Run directory does not exist: {run_path}"
        return ModelRunResult(
            member_id,
            run_path,
            -1,
            stdout_path,
            stderr_path,
            False,
            message,
        )

    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    executable_input = Path(executable)
    run_file_input = Path(run_file)
    executable_path = _path_in_run_dir(run_path, executable_input)
    run_file_path = _path_in_run_dir(run_path, run_file_input)

    for required_path, label in (
        (executable_path, "Executable"),
        (run_file_path, "Run file"),
    ):
        if not required_path.is_file():
            message = f"{label} does not exist: {required_path}"
            _write_failure_logs(stdout_path, stderr_path, message)
            return ModelRunResult(
                member_id,
                run_path,
                -1,
                stdout_path,
                stderr_path,
                False,
                message,
            )

    command = [
        str(executable_path),
        str(run_file_path),
    ]

    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_file:
            with stderr_path.open("w", encoding="utf-8") as stderr_file:
                completed = subprocess.run(
                    command,
                    cwd=run_path,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=timeout_seconds,
                    check=False,
                )
    except subprocess.TimeoutExpired:
        message = f"Model run timed out after {timeout_seconds} seconds"
        _append_stderr(stderr_path, message)
        return ModelRunResult(
            member_id,
            run_path,
            -1,
            stdout_path,
            stderr_path,
            False,
            message,
        )
    except OSError as exc:
        message = f"Failed to run model: {exc}"
        _append_stderr(stderr_path, message)
        return ModelRunResult(
            member_id,
            run_path,
            -1,
            stdout_path,
            stderr_path,
            False,
            message,
        )

    success = completed.returncode == 0
    if success:
        message = "Model run completed successfully"
    else:
        message = f"Model run failed with return code {completed.returncode}"

    return ModelRunResult(
        member_id,
        run_path,
        completed.returncode,
        stdout_path,
        stderr_path,
        success,
        message,
    )


def check_required_outputs(
    run_dir,
    required_suffixes=(".g01", ".G03"),
) -> None:
    """Raise when required output suffixes are absent from ``run_dir``."""
    run_path = Path(run_dir)
    if not run_path.is_dir():
        raise FileNotFoundError(f"Run directory does not exist: {run_path}")

    suffixes = _normalise_suffixes(required_suffixes)
    output_files = [path for path in run_path.iterdir() if path.is_file()]
    missing_suffixes = [
        suffix
        for suffix in suffixes
        if not _has_file_with_suffix(output_files, suffix)
    ]

    if missing_suffixes:
        missing_text = ", ".join(missing_suffixes)
        raise FileNotFoundError(
            f"Missing required output suffixes in {run_path}: {missing_text}"
        )


def _path_in_run_dir(run_path: Path, input_path: Path) -> Path:
    if input_path.is_absolute():
        return input_path
    return run_path / input_path


def _write_failure_logs(
    stdout_path: Path,
    stderr_path: Path,
    message: str,
) -> None:
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text(f"{message}\n", encoding="utf-8")


def _append_stderr(stderr_path: Path, message: str) -> None:
    with stderr_path.open("a", encoding="utf-8") as stderr_file:
        stderr_file.write(f"{message}\n")


def _normalise_suffixes(required_suffixes) -> tuple[str, ...]:
    if isinstance(required_suffixes, str):
        return (required_suffixes,)
    return tuple(required_suffixes)


def _has_file_with_suffix(output_files: list[Path], suffix: str) -> bool:
    suffix_lower = suffix.lower()
    return any(
        path.name.lower().endswith(suffix_lower)
        for path in output_files
    )
