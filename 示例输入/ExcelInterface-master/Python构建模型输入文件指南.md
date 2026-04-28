# 新手教程: 用 Python 生成 Maizsim 模型输入文件

本文档是当前推荐的主使用说明。按这里的步骤做, 可以从示例配置开始, 逐步生成自己的 Maizsim 输入目录。

如果你需要更完整的背景资料, 例如各示例表适合什么场景, `Climate` sheet 和天气 CSV 的区别, 或 Excel 参数表各 sheet 的作用, 请阅读 `Maizsim输入制作指南.md`。

这份教程面向第一次使用的人。目标很简单:

```text
Excel 参数表 + TOML 配置
        ↓
Python 自动调用 Excel 宏
        ↓
生成 Maizsim 需要的输入目录, 输入文件和 soil/grid 文件
```

你不需要手动打开 Excel 选择 ID。Python 会把配置写入 Excel 宏工作簿副本, 然后让原来的宏自动生成文件。

## 1. 先认识几个文件

| 文件 | 你需要怎么用 |
|---|---|
| `maizsim_input_example.toml` | 示例配置文件。第一次可以直接用它跑通。之后复制一份, 改成自己的配置。 |
| `maizsim_generate_inputs.py` | 主入口脚本。日常就运行这个文件。 |
| `Example input/.../*.xlsx` | Excel 参数表。里面的 `Description` sheet 决定有哪些 run 可以生成。 |
| `ExcelInterface/read plant filesV9_mulch (integrated).xlsm` | 原始 Excel 宏工作簿。不要直接改它。 |
| `.generated/read_plant_files_automation.xlsm` | Python 自动复制出来的宏工作簿副本。可以被覆盖。 |

日常只需要重点看两个文件:

```text
ExcelInterface-master/maizsim_input_example.toml
ExcelInterface-master/maizsim_generate_inputs.py
```

## 2. 第一次先跑通示例

先进入项目的 `示例输入` 目录:

```powershell
cd "E:\Paper\智慧农业\二维作物模型\MAIZSIM\示例输入"
```

先做检查, 不真正生成文件:

```powershell
pixi run check
```

如果看到类似输出, 说明配置和 Excel 参数表基本没问题:

```text
配置校验通过. selected_ids=1, Description 可用 run 数=7.
WaterBound.DAT 来源文件: ...
模型运行文件来源: 2dMAIZSIM.exe, Maizsim.dll
dry-run 完成, 未复制宏工作簿, 未调用 Excel, 未重命名 run 文件, 未复制 WaterBound.DAT, 未复制模型运行文件, 未改写 run 文件.
```

然后正式生成:

```powershell
pixi run filecheat
```

默认示例会生成 `MDEasternShore (maize)` 案例中的 `WYE07` 这个 run, 自动把宏生成的 `runWYE07.dat` 规范化为 `run.dat`, 把 `WaterBound.DAT`, `2dMAIZSIM.exe` 和 `Maizsim.dll` 放到 `Wye07` 目录, 改写 `run.dat` 中的引用路径, 并自动生成对应的 soil/grid 文件。

## 3. 什么时候用 dry-run

每次改完 TOML 或 Excel 参数表后, 都先运行:

```powershell
pixi run check
```

dry-run 的意思是“只检查, 不生成”。它会检查:

- TOML 字段有没有漏填。
- 路径是否存在。
- `selected_ids` 是否真的存在于 `Description.ID`。
- Excel 参数表中关键 sheet 和字段是否齐全。
- `WeatherID`, `ClimateID`, `SoilFile`, `Hybrid` 等引用是否能在对应 sheet 找到。
- 关键 ID 是否重复。

dry-run 通过后, 再去正式生成。这样更容易定位问题。

## 4. 复制一份自己的配置

不要直接改示例配置。建议复制一份:

```powershell
Copy-Item ExcelInterface-master\maizsim_input_example.toml ExcelInterface-master\maizsim_input_mycase.toml
```

之后运行自己的配置:

```powershell
pixi run python ExcelInterface-master/maizsim_generate_inputs.py --config ExcelInterface-master/maizsim_input_mycase.toml --dry-run
pixi run python ExcelInterface-master/maizsim_generate_inputs.py --config ExcelInterface-master/maizsim_input_mycase.toml
```

## 5. TOML 里最需要改什么

TOML 分两段: `[paths]` 和 `[run]`。

### 5.1 paths: 告诉宏文件在哪里

`[paths]` 主要是各种文件夹路径。第一次做自己的算例时, 最常改这几个:

```toml
[paths]

input_excel_file = "Example input/MDEasternShore (maize)/MD-DE inputs.xlsx"
root_path = "Example input/MDEasternShore (maize)"
weather_csv_folder = "Example input/MDEasternShore (maize)"
```

含义如下:

| 字段 | 简单理解 |
|---|---|
| `input_excel_file` | 你的 Excel 参数表。 |
| `root_path` | 生成 run 子目录的位置。 |
| `weather_csv_folder` | 天气 CSV 文件所在目录。 |
| `macro_workbook` | 原始宏工作簿, 通常不用改。 |

其他路径通常先保持示例值不变, 等你确定模型程序和工具目录位置后再改。

原始宏会生成 `run<ID>.dat`, 并把其中的 `WaterBound.DAT` 写成模拟根目录公共文件。Python/TOML 流程会在宏完成后先把 `run<ID>.dat` 规范化为 `run.dat`, 再把 `WaterBound.DAT` 复制到每个 selected run 目录, 并把对应 `run.dat` 中的引用改写到该 run 目录下的文件。

同一流程还会从 `Models` 目录复制 `2dMAIZSIM.exe` 和 `Maizsim.dll` 到每个 selected run 目录, 方便进入单个算例目录后直接运行模型。

### 5.2 run: 告诉宏要生成哪些 ID

`[run]` 里最重要的是 `selected_ids`:

```toml
[run]

selected_ids = ["WYE07"]
```

这个 ID 必须来自 Excel 参数表的 `Description` sheet。

如果要一次生成多个 run:

```toml
selected_ids = ["WYE07", "WYE08"]
```

`[run]` 里还有一个通常保持默认的输出字段:

| 字段 | 简单理解 |
|---|---|
| `automation_workbook` | 自动化宏工作簿副本路径, 通常放在 `.generated` 下。 |

## 6. 如何找到 selected_ids

打开你的 Excel 参数表, 找到 `Description` sheet。

`ID` 这一列就是可以写入 `selected_ids` 的候选值。例如:

```text
ID
WYE07
WYE08
DEL07
```

如果你想生成 `WYE07`, TOML 写:

```toml
selected_ids = ["WYE07"]
```

如果 TOML 写了不存在的 ID, dry-run 会报错, 不会继续调用 Excel 宏。

## 7. 相对路径可以怎么写

TOML 中可以写相对路径。推荐相对于 `ExcelInterface-master` 写, 这样最短也最清楚:

```toml
[paths]

input_excel_file = "Example input/MDEasternShore (maize)/MD-DE inputs.xlsx"
macro_workbook = "ExcelInterface/read plant filesV9_mulch (integrated).xlsm"

[run]

automation_workbook = ".generated/read_plant_files_automation.xlsm"
```

Python 在调用 Excel 宏前, 会把这些路径解析成绝对路径, 再写入 Excel 接口。

如果路径一直报错, 可以临时改成绝对路径排查。例如:

```toml
input_excel_file = "E:/Paper/智慧农业/二维作物模型/MAIZSIM/示例输入/ExcelInterface-master/Example input/MDEasternShore (maize)/MD-DE inputs.xlsx"
```

## 8. 正式生成后看哪里

输出位置由两个地方决定:

```text
TOML 的 root_path
Excel 参数表 Description sheet 里的 Path
```

例如:

```toml
root_path = "Example input/MDEasternShore (maize)"
selected_ids = ["WYE07"]
```

如果 `Description` 里 `WYE07` 的 `Path` 是 `Wye07`, 那么输出目录通常就在:

```text
ExcelInterface-master/Example input/MDEasternShore (maize)/Wye07
```

生成后重点检查这些文件:

```text
run.dat
WYE07.wea
grid1.bat
*.lyr
WyeSoil.soi
WYE07.grd
WYE07.nod
WaterBound.DAT
2dMAIZSIM.exe
Maizsim.dll
```

如果这些文件存在, 且目录中没有保留 `runWYE07.dat`, 说明 Excel 宏, `run.dat` 规范化, 模型运行文件复制和 soil/grid 自动生成步骤都已经完成。

## 9. grid1.bat 是做什么的

Python 调用 Excel 宏后, 会生成 `grid1.bat`。

`grid1.bat` 不是 Python 脚本, 它记录了生成土壤和网格文件的原始批处理命令。当前 `pixi run filecheat` 会在宏完成后由 Python 直接调用 `CreateSoilFiles.exe`, 因此正常流程不需要手动运行 `grid1.bat`。也就是说:

```text
Python + Excel 宏: 生成 run 文件, 天气文件, layer 文件, grid1.bat 等
Python + CreateSoilFiles.exe: 继续生成 soil/grid 相关文件
grid1.bat: 保留为人工排查或手动重跑依据
```

如果模型运行时提示缺少 soil 或 grid 文件, 通常先重新执行 `pixi run filecheat` 并查看错误信息。只有排查批处理命令本身时, 才需要进入对应 run 目录手动执行 `grid1.bat`。

## 10. Python 到底做了什么

正式运行时, Python 会按顺序做这些事:

1. 读取 TOML。
2. 检查路径和 Excel 参数表。
3. 复制原始 `.xlsm` 到 `.generated` 下。
4. 打开这个宏工作簿副本。
5. 把 TOML 里的路径写入 Excel 的 `Interface` 页。
6. 把 `selected_ids` 写入隐藏 sheet `_PythonConfig`。
7. 导入一个不弹窗的 VBA 入口。
8. 调用原来的 Excel 写文件宏。
9. 保存并关闭 Excel。
10. 把宏生成的 `run<ID>.dat` 规范化为 `run.dat`。
11. 把 `WaterBound.DAT` 复制到每个 selected run 目录, 并改写对应 `run.dat` 中的引用路径。
12. 把 `Models` 目录中的 `2dMAIZSIM.exe` 和 `Maizsim.dll` 复制到每个 selected run 目录。
13. 调用 `CreateSoilFiles.exe` 为每个 selected run 生成 soil/grid 文件。

关键点: Python 不重新实现模型输入文件格式。真正写文件的逻辑仍然是原来的 Excel VBA 宏。

## 11. 常见错误

### 11.1 路径不存在

常见报错:

```text
错误: paths.input_excel_file 路径不存在.
```

处理方法:

- 先确认文件是否真的存在。
- 检查路径是不是相对于 `ExcelInterface-master` 写的。
- 临时改成绝对路径排查。

### 11.2 selected_id 不存在

常见报错:

```text
错误: selected_id WYE99 不存在于 Description.ID.
```

处理方法:

- 打开 Excel 参数表。
- 查看 `Description` sheet 的 `ID` 列。
- 把 TOML 的 `selected_ids` 改成真实存在的 ID。

### 11.3 布尔值写错

错误写法:

```toml
visible_excel = "false"
```

正确写法:

```toml
visible_excel = false
```

`true` 和 `false` 不能加引号。

### 11.4 Excel 不允许导入 VBA

如果报错提示无法导入 VBA 模块, 需要在 Excel 中开启:

```text
Trust access to the VBA project object model
```

开启后关闭 Excel, 再重新运行 Python 命令。

## 12. 新建自己算例的最小路线

第一次做自己的算例, 建议只改最少内容:

1. 复制一个最接近的示例 Excel 参数表。
2. 复制 `maizsim_input_example.toml`。
3. 在新 TOML 中修改 `input_excel_file`, `root_path`, `weather_csv_folder`。
4. 在 Excel 参数表的 `Description` sheet 中确认要运行的 `ID`。
5. 把这个 ID 写入 `selected_ids`。
6. 运行 dry-run。
7. dry-run 通过后正式生成。
8. 检查输出目录和关键文件, 包括 `.soi`, `.grd`, `.nod`。

先跑通一个 ID, 再扩展到多个 ID。不要一开始同时修改大量 sheet, 否则很难判断错误来自哪里。
