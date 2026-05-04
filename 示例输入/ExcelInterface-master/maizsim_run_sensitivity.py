"""ExcelInterface-master 根目录下的敏感性分析入口."""

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parent
SENSITIVITY_DIR = ROOT_DIR / "sensitivity_analysis"
DEFAULT_BOUNDS = ROOT_DIR / "Example input" / "SingleLayerLoam2D" / "sensitivity_parameter_bounds.toml"


def has_bounds_arg(arguments):
    """判断命令行是否已经显式传入参数边界文件."""
    for argument in arguments:
        if argument == "--bounds" or argument.startswith("--bounds="):
            return True
    return False


def build_forward_args(arguments):
    """补全默认参数边界路径并返回转发参数."""
    forward_args = list(arguments)
    if not has_bounds_arg(forward_args):
        forward_args = ["--bounds", str(DEFAULT_BOUNDS), *forward_args]
    return forward_args


def main():
    """调用 sensitivity_analysis 目录下的敏感性分析实现."""
    sys.path.insert(0, str(SENSITIVITY_DIR))
    from maizsim_sensitivity.cli import main as tool_main

    return tool_main(build_forward_args(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
