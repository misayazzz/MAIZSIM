"""样本目录准备和参数文件回写."""

from pathlib import Path
import shutil

from .config import SensitivityConfigError


RUN_DAT_FILES = [
    "LOAM2D.wea",
    "LOAM2D.tim",
    "BiologyDefault.bio",
    "WyeClimate.dat",
    "Loam2D.nit",
    "NitrogenDefault.sol",
    "GasID.gas.gas",
    "Loam_200cm.soi",
    "MulchGeo1.mul",
    "LOAM2D.man",
    "LOAM2D.irr",
    "LOAM2D.drp",
    "WaterMovDefault.dat",
    "WaterBound.DAT",
    "LOAM2D.ini",
    "PI34M91.var",
    "LOAM2D.grd",
    "LOAM2D.nod",
    "MassBl.dat",
    "LOAM2D.g01",
    "LOAM2D.g02",
    "LOAM2D.G03",
    "LOAM2D.G04",
    "LOAM2D.G05",
    "LOAM2D.G06",
    "LOAM2D.G07",
    "MassBl.out",
    "MassBlRunOff.out",
    "MassBlMulch.out",
]

STALE_OUTPUT_NAMES = {
    "2DSOIL03.LOG",
    "createError.log",
    "LOAM2D.g01",
    "LOAM2D.g02",
    "LOAM2D.G03",
    "LOAM2D.G04",
    "LOAM2D.G05",
    "LOAM2D.G06",
    "LOAM2D.G07",
    "MassBl.dat",
    "MassBl.out",
    "MassBlRunOff.out",
    "MassBlMulch.out",
    "plantstress.crp",
    "stdout.txt",
    "stderr.txt",
}


def format_number(value):
    """格式化模型输入文件中的数值."""
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.8g}"


def copy_ignore(directory, names):
    """忽略基线目录中的旧输出文件."""
    return [name for name in names if name in STALE_OUTPUT_NAMES]


def ensure_new_analysis_dir(analysis_dir):
    """创建新的分析目录, 已存在且非空时停止."""
    if analysis_dir.exists() and any(analysis_dir.iterdir()):
        raise SensitivityConfigError(f"分析目录已存在且非空, 为避免覆盖已停止: {analysis_dir}")
    analysis_dir.mkdir(parents=True, exist_ok=True)


def write_run_dat(sample_dir):
    """在样本目录中写入相对路径 run.dat."""
    run_dat_path = sample_dir / "run.dat"
    text = "\n".join(RUN_DAT_FILES) + "\n"
    run_dat_path.write_text(text, encoding="utf-8")


def prepare_sample_dir(baseline_run_dir, sample_dir):
    """从基线目录复制样本目录并重写 run.dat."""
    if sample_dir.exists():
        raise SensitivityConfigError(f"样本目录已存在, 为避免覆盖已停止: {sample_dir}")
    shutil.copytree(baseline_run_dir, sample_dir, ignore=copy_ignore)
    write_run_dat(sample_dir)


def find_next_data_line(lines, start_index):
    """从指定位置向后查找数据行."""
    for index in range(start_index + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("[") and not stripped.startswith("*"):
            return index
    raise SensitivityConfigError("无法在参数文件中定位数据行.")


def replace_crop_line(lines, values):
    """回写作物物候和叶片参数行."""
    line_index = None
    for index, line in enumerate(lines):
        if "TassellInit" in line:
            line_index = find_next_data_line(lines, index)
            break
    if line_index is None:
        raise SensitivityConfigError("PI34M91.var 中未找到 TassellInit 参数段.")

    tokens = lines[line_index].split()
    if len(tokens) < 7:
        raise SensitivityConfigError("PI34M91.var 作物参数行列数不足.")

    field_indexes = {
        "JuvenileLeaves": 0,
        "StayGreen": 2,
        "LM_min": 3,
        "Rmax_LTAR": 4,
        "Rmax_LTIR": 5,
        "PhyllFrmTassel": 6,
    }
    for name, value in values.items():
        if name in field_indexes:
            tokens[field_indexes[name]] = format_number(value)
    lines[line_index] = " " + "             ".join(tokens) + " \n"


def replace_root_diff_line(lines, values):
    """回写根系空间扩散参数行."""
    line_index = None
    for index, line in enumerate(lines):
        if "Diffusivity and geotropic velocity" in line:
            line_index = find_next_data_line(lines, index)
            break
    if line_index is None:
        raise SensitivityConfigError("PI34M91.var 中未找到 RootDiff 参数段.")

    tokens = lines[line_index].split()
    if len(tokens) < 3:
        raise SensitivityConfigError("PI34M91.var 根系扩散参数行列数不足.")

    if "Diffx" in values:
        tokens[0] = format_number(values["Diffx"])
    if "Diffz" in values:
        tokens[1] = format_number(values["Diffz"])
    lines[line_index] = " " + "             ".join(tokens) + " \n"


def write_variety_file(sample_dir, values):
    """回写 PI34M91.var 中的作物和根系参数."""
    path = sample_dir / "PI34M91.var"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    replace_crop_line(lines, values)
    replace_root_diff_line(lines, values)
    path.write_text("".join(lines), encoding="utf-8")


def write_soil_file(sample_dir, values):
    """回写 Loam_200cm.soi 中的土壤水力参数."""
    path = sample_dir / "Loam_200cm.soi"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if len(lines) < 3:
        raise SensitivityConfigError("Loam_200cm.soi 行数不足.")

    line_index = 2
    tokens = lines[line_index].split()
    if len(tokens) < 14:
        raise SensitivityConfigError("Loam_200cm.soi 参数行列数不足.")

    field_indexes = {
        "thetaR": [0, 2],
        "thetaS": [1, 3, 8],
        "Alfa": [4],
        "n": [5],
        "Ks": [6, 7],
    }
    for name, indexes in field_indexes.items():
        if name in values:
            for index in indexes:
                tokens[index] = format_number(values[name])
    lines[line_index] = " " + "\t ".join(tokens) + "\n"
    path.write_text("".join(lines), encoding="utf-8")


def validate_parameter_values(values):
    """校验实际写入参数是否满足模型约束."""
    theta_r = values.get("thetaR")
    theta_s = values.get("thetaS")
    if theta_r is not None and theta_s is not None and not (0 <= theta_r < theta_s < 1):
        raise SensitivityConfigError(f"土壤含水量约束不满足: thetaR={theta_r}, thetaS={theta_s}")
    if values.get("Alfa", 1) <= 0:
        raise SensitivityConfigError(f"Alfa 必须大于 0: {values.get('Alfa')}")
    if values.get("n", 2) <= 1:
        raise SensitivityConfigError(f"n 必须大于 1: {values.get('n')}")
    if values.get("Ks", 1) <= 0:
        raise SensitivityConfigError(f"Ks 必须大于 0: {values.get('Ks')}")
    if values.get("Diffx", 0) < 0:
        raise SensitivityConfigError(f"Diffx 必须非负: {values.get('Diffx')}")
    if values.get("Diffz", 0) < 0:
        raise SensitivityConfigError(f"Diffz 必须非负: {values.get('Diffz')}")


def write_parameters(sample_dir, values):
    """回写样本目录中的作物和土壤参数."""
    validate_parameter_values(values)
    write_variety_file(sample_dir, values)
    write_soil_file(sample_dir, values)
