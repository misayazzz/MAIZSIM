"""二维土壤网格生成."""

from pathlib import Path
import subprocess

from .errors import ConfigError
from .path_utils import resolve_run_dir


INTERMEDIATE_FILES = [
    "output",
    "element_elm",
    "grid_bnd",
    "datagen2.dat",
]


def format_process_output(result):
    """整理外部程序输出, 用于错误提示."""
    parts = []
    stdout = result.stdout.strip() if result.stdout else ""
    stderr = result.stderr.strip() if result.stderr else ""
    if stdout:
        parts.append(f"stdout: {stdout}")
    if stderr:
        parts.append(f"stderr: {stderr}")
    if not parts:
        return "无输出."
    return "\n".join(parts)


def require_non_empty_file(path, label):
    """确认生成文件存在且非空."""
    if not path.is_file():
        raise ConfigError(f"{label} 未生成: {path}")
    if path.stat().st_size <= 0:
        raise ConfigError(f"{label} 为空文件: {path}")


def clean_intermediate_files(run_dir):
    """删除 CreateSoilFiles 生成的临时文件."""
    for file_name in INTERMEDIATE_FILES:
        target = run_dir / file_name
        if target.exists():
            target.unlink()


def generate_run_soil_grid(paths, run):
    """为单个 run 生成二维土壤网格和 soil 文件."""
    create_soils_exe = paths["create_soils"] / "CreateSoilFiles.exe"
    if not create_soils_exe.is_file():
        raise ConfigError(f"CreateSoilFiles.exe 不存在: {create_soils_exe}")

    run_id = run["id"]
    run_dir = resolve_run_dir(paths["root_path"], run["path"])
    if not run_dir.is_dir():
        raise ConfigError(f"{run_id} 的 run 目录不存在: {run_dir}")

    layer_file = run_dir / f"{run_id}.lyr"
    if not layer_file.is_file():
        raise ConfigError(f"{run_id} 的 layer 文件不存在: {layer_file}")

    soil_file = Path(run["soil_file"]).name
    soil_name = Path(soil_file).stem
    command = [
        str(create_soils_exe),
        str(layer_file),
        "/GN",
        run_id,
        "/SN",
        soil_name,
    ]
    result = subprocess.run(command, cwd=run_dir, capture_output=True, text=True)
    if result.returncode != 0:
        output = format_process_output(result)
        raise ConfigError(f"{run_id} 网格生成失败, exit code={result.returncode}.\n{output}")

    clean_intermediate_files(run_dir)
    require_non_empty_file(run_dir / soil_file, f"{run_id} soil 文件")
    require_non_empty_file(run_dir / f"{run_id}.grd", f"{run_id} grid 文件")
    require_non_empty_file(run_dir / f"{run_id}.nod", f"{run_id} node 文件")

    return {
        "id": run_id,
        "run_dir": run_dir,
        "soil_file": run_dir / soil_file,
        "grid_file": run_dir / f"{run_id}.grd",
        "node_file": run_dir / f"{run_id}.nod",
    }


def generate_soil_grids(config, runs):
    """为 selected runs 批量生成二维土壤网格."""
    results = []
    for run in runs:
        results.append(generate_run_soil_grid(config["paths"], run))
    return results
