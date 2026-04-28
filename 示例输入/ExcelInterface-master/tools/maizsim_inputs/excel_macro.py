"""Excel COM 和 VBA 宏调用."""

import shutil

from .errors import ConfigError
from .path_utils import TOOLS_DIR
from .path_utils import validate_automation_workbook_target


PYTHON_CONFIG_SHEET = "_PythonConfig"
VBA_MODULE_NAME = "RunConfiguredIdsM"


def write_interface_paths(workbook, paths):
    """把 TOML 路径写入 Interface 页的 B1:B6."""
    sheet = workbook.Worksheets("Interface")
    ordered_fields = [
        "input_excel_file",
        "root_path",
        "maizsim_path",
        "create_soils",
        "excel_interface",
        "weather_csv_folder",
    ]
    for index, field_name in enumerate(ordered_fields, 1):
        sheet.Cells(index, 2).Value = str(paths[field_name])


def get_or_create_config_sheet(workbook):
    """获取或创建隐藏的 Python 配置 sheet."""
    for sheet in workbook.Worksheets:
        if sheet.Name == PYTHON_CONFIG_SHEET:
            sheet.Visible = -1
            sheet.Cells.Clear()
            return sheet
    sheet = workbook.Worksheets.Add(After=workbook.Worksheets(workbook.Worksheets.Count))
    sheet.Name = PYTHON_CONFIG_SHEET
    return sheet


def write_selected_ids(workbook, selected_ids):
    """把 selected IDs 写入隐藏配置 sheet."""
    sheet = get_or_create_config_sheet(workbook)
    sheet.Cells(1, 1).Value = "ID"
    for index, selected_id in enumerate(selected_ids, 2):
        sheet.Cells(index, 1).Value = selected_id
    sheet.Visible = 2


def import_vba_module(workbook, module_path):
    """导入非交互 VBA 包装模块."""
    vbproject = workbook.VBProject
    for component in list(vbproject.VBComponents):
        if component.Name == VBA_MODULE_NAME:
            vbproject.VBComponents.Remove(component)
            break
    vbproject.VBComponents.Import(str(module_path))


def prepare_and_run(config):
    """复制宏工作簿, 注入配置, 并调用非交互宏入口."""
    try:
        import win32com.client
    except ImportError as exc:
        raise ConfigError("缺少 pywin32. 请先运行 pixi add pywin32.") from exc

    paths = config["paths"]
    run = config["run"]
    automation_workbook = run["automation_workbook"]
    module_path = TOOLS_DIR / "vba" / "RunConfiguredIds.bas"

    if not module_path.exists():
        raise ConfigError(f"VBA 包装模块不存在: {module_path}")

    validate_automation_workbook_target(paths["macro_workbook"], automation_workbook)
    automation_workbook.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths["macro_workbook"], automation_workbook)

    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = run["visible_excel"]
    excel.DisplayAlerts = False
    excel.EnableEvents = False
    excel.AutomationSecurity = 1
    workbook = None
    try:
        workbook = excel.Workbooks.Open(str(automation_workbook), ReadOnly=False)
        try:
            write_interface_paths(workbook, paths)
            write_selected_ids(workbook, run["selected_ids"])
            import_vba_module(workbook, module_path)
        except Exception as exc:
            raise ConfigError(
                "无法写入或导入 VBA 模块. 请确认 Excel 已启用 Trust access to the VBA project object model."
            ) from exc

        workbook.Save()
        excel.Run(f"'{workbook.Name}'!RunConfiguredIds")
        if run["save_after_run"]:
            workbook.Save()
    finally:
        if workbook is not None:
            workbook.Close(SaveChanges=run["save_after_run"])
        excel.Quit()

