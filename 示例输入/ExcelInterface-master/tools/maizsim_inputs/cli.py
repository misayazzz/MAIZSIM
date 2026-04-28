"""命令行入口."""

from pathlib import Path
import argparse
import sys

from .config import read_config
from .errors import ConfigError
from .excel_macro import prepare_and_run
from .model_files import copy_model_files_to_run_dirs
from .model_files import find_model_file_sources
from .run_files import normalize_run_files
from .shared_inputs import copy_water_bound_to_run_dirs
from .shared_inputs import find_water_bound_source
from .soil_grid import generate_soil_grids
from .weather_files import rewrite_weather_files
from .workbook_validation import validate_workbook


def parse_args(arguments=None):
    """解析命令行参数."""
    parser = argparse.ArgumentParser(
        description="Generate Maizsim input folders by calling the Excel VBA interface from a TOML config."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the TOML config file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and workbook links without copying the macro workbook or running Excel.",
    )
    return parser.parse_args(arguments)


def main(arguments=None):
    """执行命令行入口."""
    args = parse_args(arguments)
    config_path = Path(args.config).expanduser().resolve()
    try:
        config = read_config(config_path)
        validation = validate_workbook(config["paths"]["input_excel_file"], config["run"]["selected_ids"])
        print(
            f"配置校验通过. selected_ids={validation['selected_count']}, "
            f"Description 可用 run 数={validation['available_run_count']}."
        )
        water_bound_source = find_water_bound_source(config["paths"])
        print(f"WaterBound.DAT 来源文件: {water_bound_source}")
        model_file_sources = find_model_file_sources()
        model_file_names = ", ".join(source.name for source in model_file_sources)
        print(f"模型运行文件来源: {model_file_names}")
        if args.dry_run:
            print(
                f"dry-run 完成, 未复制宏工作簿, 未调用 Excel, 未重写天气文件, 未重命名 run 文件, "
                f"未复制 WaterBound.DAT, 未复制模型运行文件, 未改写 run 文件."
            )
            return 0
        prepare_and_run(config)
        print(f"宏调用完成. 自动化副本: {config['run']['automation_workbook']}")
        weather_results = rewrite_weather_files(config["paths"], validation["runs"])
        weather_row_count = sum(result["rows"] for result in weather_results)
        print(f"天气文件已按显式日期格式重写. run 数={len(weather_results)}, 行数={weather_row_count}.")
        run_file_results = normalize_run_files(config["paths"], validation["runs"])
        print(f"run 文件已规范化为 run.dat. run 数={len(run_file_results)}.")
        water_bound_results = copy_water_bound_to_run_dirs(config["paths"], validation["runs"])
        print(f"WaterBound.DAT 已复制并改写 run 文件引用. run 数={len(water_bound_results)}.")
        model_file_results = copy_model_files_to_run_dirs(config["paths"], validation["runs"])
        print(f"模型运行文件已复制. run 数={len(model_file_results)}, 文件数={len(model_file_sources)}.")
        grid_results = generate_soil_grids(config, validation["runs"])
        print(f"soil/grid 生成完成. run 数={len(grid_results)}.")
        return 0
    except ConfigError as exc:
        sys.stderr.write(f"错误: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"未处理错误: {exc}\n")
        return 1
