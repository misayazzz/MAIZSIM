"""ExcelInterface-master 根目录下的 Maizsim 输入生成入口."""

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = ROOT_DIR / "tools"
DEFAULT_CONFIG = ROOT_DIR / "maizsim_input_example.toml"


def has_config_arg(arguments):
    """判断命令行是否已经显式传入配置文件."""
    for argument in arguments:
        if argument == "--config" or argument.startswith("--config="):
            return True
    return False


def build_forward_args(arguments):
    """补全默认配置路径并返回转发参数."""
    forward_args = list(arguments)
    if not has_config_arg(forward_args):
        forward_args = ["--config", str(DEFAULT_CONFIG), *forward_args]
    return forward_args


def main():
    """调用 tools 目录下的主实现."""
    sys.path.insert(0, str(TOOLS_DIR))
    from maizsim_inputs.cli import main as tool_main

    return tool_main(build_forward_args(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
