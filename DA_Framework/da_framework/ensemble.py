"""Prepare and run MAIZSIM ensemble member directories."""

from __future__ import annotations

import fnmatch
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from pathlib import Path

try:
    from .model_runner import ModelRunResult, check_required_outputs, run_model
except ImportError:
    from model_runner import ModelRunResult, check_required_outputs, run_model


OUTPUT_PATTERNS = (
    "*.g01",
    "*.g02",
    "*.G03",
    "*.G04",
    "*.G05",
    "*.G06",
    "*.G07",
    "2DSOIL03.LOG",
    "MassBl*.out",
)

HARDLINK_SUFFIXES = frozenset((".exe", ".dll"))
MINIMAL_OUTPUT_NONE_PATTERNS = (
    "*.G04",
    "*.G05",
    "*.G06",
    "*.G07",
    "MassBl.out",
    "MassBlRunOff.out",
    "MassBlMulch.out",
)


def member_name(index) -> str:
    """Return a zero-padded ensemble member directory name."""
    if index < 0:
        raise ValueError("Member index must be non-negative")
    return f"{index:06d}"


def prepare_member_directory(
    base_run_dir,
    member_dir,
    clean_outputs=True,
    minimal_outputs=False,
    run_file="run.dat",
) -> Path:
    """Copy a base MAIZSIM run directory into one ensemble member directory."""
    base_path = Path(base_run_dir)
    member_path = Path(member_dir)

    if not base_path.is_dir():
        raise FileNotFoundError(
            f"Base run directory does not exist: {base_path}"
    )
    _validate_copy_target(base_path, member_path)

    if clean_outputs:
        _clean_outputs(member_path)
    shutil.copytree(
        base_path,
        member_path,
        dirs_exist_ok=True,
        ignore=_ignore_member_copy_outputs,
        copy_function=_copy_member_file,
    )
    if minimal_outputs:
        _write_minimal_outputs(member_path, run_file)
    return member_path


def prepare_ensemble(
    base_run_dir,
    ensemble_dir,
    n_ensemble,
    minimal_outputs=False,
    run_file="run.dat",
) -> list[Path]:
    """Prepare all ensemble member directories from one base run directory."""
    if n_ensemble < 0:
        raise ValueError("n_ensemble must be non-negative")

    ensemble_path = Path(ensemble_dir)
    ensemble_path.mkdir(parents=True, exist_ok=True)

    member_dirs = []
    for index in range(1, n_ensemble + 1):
        member_dir = ensemble_path / member_name(index)
        member_dirs.append(
            prepare_member_directory(
                base_run_dir,
                member_dir,
                minimal_outputs=minimal_outputs,
                run_file=run_file,
            )
        )
    return member_dirs


def write_ensemble_parameters(
    member_dirs,
    parameter_frame,
    var_file,
    soi_file,
) -> None:
    """Write one parameter row into each ensemble member directory."""
    member_paths = [Path(member_dir) for member_dir in member_dirs]
    if len(parameter_frame) != len(member_paths):
        raise ValueError(
            "parameter_frame row count must match member_dirs count: "
            f"{len(parameter_frame)} != {len(member_paths)}"
        )

    parameter_writer = _load_parameter_writer()
    for index, member_dir in enumerate(member_paths):
        member_parameters = _get_parameter_row(parameter_frame, index)
        parameter_writer.write_member_parameters(
            member_dir,
            member_parameters,
            var_file,
            soi_file,
        )


def run_ensemble(
    member_dirs,
    max_workers=12,
    timeout_seconds=None,
) -> list[ModelRunResult]:
    """Run all ensemble members, preserving the input order in results."""
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")

    member_paths = [Path(member_dir) for member_dir in member_dirs]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(
            executor.map(
                _run_member,
                member_paths,
                repeat(timeout_seconds),
            )
        )


def check_ensemble_outputs(member_dirs) -> None:
    """Validate required outputs for every ensemble member."""
    missing_messages = []
    for member_dir in member_dirs:
        try:
            check_required_outputs(member_dir)
        except FileNotFoundError as exc:
            missing_messages.append(str(exc))

    if missing_messages:
        raise FileNotFoundError(
            "One or more ensemble members are missing required outputs: "
            + "; ".join(missing_messages)
        )


def _validate_copy_target(base_path: Path, member_path: Path) -> None:
    base_resolved = base_path.resolve()
    member_resolved = member_path.resolve()
    if member_resolved == base_resolved:
        raise ValueError("Member directory must differ from base_run_dir")
    try:
        member_resolved.relative_to(base_resolved)
    except ValueError:
        return
    raise ValueError("Member directory cannot be inside base_run_dir")


def _clean_outputs(member_path: Path) -> None:
    if not member_path.exists():
        return
    for path in member_path.rglob("*"):
        if path.is_file() and _is_output_file(path):
            path.unlink()


def _ignore_member_copy_outputs(_directory, names) -> set[str]:
    return {
        name
        for name in names
        if _is_output_file(Path(name))
    }


def _copy_member_file(src, dst) -> Path:
    src_path = Path(src)
    dst_path = Path(dst)
    if _is_hardlink_candidate(src_path):
        try:
            os.link(src_path, dst_path)
            return dst_path
        except OSError:
            pass
    return Path(shutil.copy2(src_path, dst_path))


def _is_hardlink_candidate(path: Path) -> bool:
    return path.suffix.lower() in HARDLINK_SUFFIXES


def _is_output_file(path: Path) -> bool:
    name = path.name.lower()
    return any(
        fnmatch.fnmatchcase(name, pattern.lower())
        for pattern in OUTPUT_PATTERNS
    )


def _write_minimal_outputs(member_path: Path, run_file) -> None:
    run_path = _resolve_member_run_file(member_path, run_file)
    lines = _read_text_lines(run_path)
    minimal_lines = [_minimal_output_line(line) for line in lines]
    with run_path.open("w", encoding="utf-8", newline="") as file_obj:
        file_obj.writelines(minimal_lines)


def _resolve_member_run_file(member_path: Path, run_file) -> Path:
    run_path = Path(run_file)
    if not run_path.is_absolute():
        return member_path / run_path

    member_resolved = member_path.resolve()
    run_resolved = run_path.resolve()
    try:
        run_resolved.relative_to(member_resolved)
    except ValueError as exc:
        raise ValueError(
            "run_file must be inside member_dir when minimal_outputs is enabled"
        ) from exc
    return run_path


def _read_text_lines(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as file_obj:
        return file_obj.read().splitlines(keepends=True)


def _minimal_output_line(line: str) -> str:
    body, line_ending = _split_line_ending(line)
    if _is_minimal_output_reference(body.strip()):
        return f"NONE{line_ending}"
    return line


def _is_minimal_output_reference(text: str) -> bool:
    if not text:
        return False
    name = Path(text).name.lower()
    return any(
        fnmatch.fnmatchcase(name, pattern.lower())
        for pattern in MINIMAL_OUTPUT_NONE_PATTERNS
    )


def _split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def _load_parameter_writer():
    try:
        from . import parameter_writer
    except ImportError:
        import parameter_writer
    return parameter_writer


def _get_parameter_row(parameter_frame, index):
    if hasattr(parameter_frame, "iloc"):
        return parameter_frame.iloc[index]
    return parameter_frame[index]


def _run_member(member_dir: Path, timeout_seconds) -> ModelRunResult:
    return run_model(member_dir, timeout_seconds=timeout_seconds)
