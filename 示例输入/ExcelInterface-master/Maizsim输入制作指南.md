# Maizsim ExcelInterface 输入制作指南

本文档作为完整背景资料保留。如果你的目标是直接使用 Python + TOML 调用 Excel 宏生成输入目录, 请优先阅读 `Python构建模型输入文件指南.md`。

本文档根据 `ExcelInterface-master/README.md`, `ExcelInterface/How to use the Excel tool.docx`, 示例 Excel 参数表和天气 CSV 文件整理, 用于说明如何制作 Maizsim/2DSOIL 的输入文件。

## 1. 推荐从示例表复制开始

不建议从空白 Excel 新建参数表。建议先判断研究场景, 再复制最接近的示例参数表作为模板。各示例的作用如下:

| 案例目录 | 参数表 | 主要作用 | 运行情况简述 | 适合基于它生成的算例 |
|---|---|---|---|---|
| `MDEasternShore (maize)` | `ExcelInterface-master/Example input/MDEasternShore (maize)/MD-DE inputs.xlsx` | Maryland Eastern Shore 玉米案例, 覆盖 Wye 和 Del 两个地点的小时天气运行, 无显式灌溉, 结构相对简单。 | 共 7 个 run。主要包括 Wye 多年份运行, Del 多年份运行, 以及 Del 在相近天气和管理条件下的不同土壤对照。 | 适合作为第一套自定义玉米算例模板, 尤其适合无灌溉, 小时天气, 地点/年份/土壤对照, 土壤水分或作物状态同化。 |
| `Kansas` | `ExcelInterface-master/Example input/Kansas/kansas inputs.xlsx` | Kansas 多站点玉米案例, 同时包含日天气和小时天气, 以及 `AshDry`/`AshIrr` 水分处理标签。 | 共 13 个 run。主要包括 Ashland 小时天气下的 `AshDry`/`AshIrr` 标签对照, 其他站点日天气运行, 以及若干显式补充灌溉运行。`AshDry` 不应直接理解为完全无灌溉。 | 适合生成多地点, 多天气尺度, 水分处理对比, 水分管理或补充灌溉相关算例。 |
| `AgmipET2` | `ExcelInterface-master/Example input/AgmipET2/AGMIPET2Sim.xlsx` | AgMIP ET2 玉米模拟示例, 覆盖多年份, 多地点和多水分管理条件。 | 共 20 个 run。主要包括 Mead 灌溉/雨养对照, Bush 不同灌溉系统或水分管理处理, 并跨多个年份。 | 适合生成批量运行, 多年份, 多处理, 灌溉系统对比或 AgMIP 背景下的扩展验证算例。 |
| `CO2_Respiration_CaseStudy1` | `ExcelInterface-master/Example input/CO2_Respiration_CaseStudy1/CaseStudy1.xlsx` | CO2/土壤呼吸参数敏感性案例, 重点是气体扩散和土壤过程参数变化。 | 共 87 个 run。主要包括基准运行, 气体扩散参数敏感性, 土壤过程参数敏感性, 以及部分双参数组合运行。 | 适合生成土壤 CO2, 土壤呼吸, 气体扩散, 气体参数敏感性或土壤参数反演算例。 |
| `CO2_Respiration_CaseStudy2` | `ExcelInterface-master/Example input/CO2_Respiration_CaseStudy2/CaseStudy2.xlsx` | CO2/土壤呼吸的最小单运行案例, 只有一个主运行。 | 共 1 个 run, 即 Sacramento California 的单运行检查案例。 | 适合快速检查 Excel 接口, 天气读取和 CO2/气体模块设置, 不适合作为正式批量研究模板。 |
| `Tropical_Temperate_Study` | `ExcelInterface-master/Example input/Tropical_Temperate_Study/Temperate_Tropical_Sites.xlsx` | 热带 Rahuri 与温带 Marshall 的多年对比案例, 使用日天气, 每个地点覆盖多个年份。 | 共 26 个 run。主要是 2 个地点各 13 年的逐年运行, 用于热带/温带和年际气候对比。 | 适合生成跨气候带, 多年气候差异, 热带/温带模型表现对比或方法泛化检验算例。 |

如果目标只是先跑通自己的第一套输入, 优先从 `MDEasternShore (maize)` 复制。它的运行数量少, 管理设置相对简单, 更容易定位天气, 土壤, 品种和路径配置问题。若研究问题明确涉及灌溉, 多地点或 CO2/土壤呼吸, 再选择对应案例作为模板。

复制后尽量保留原 sheet 名和表头。不同示例中表头大小写和拼写可能略有差异, 例如 `SoilFile`, `soilFile`, `SoilFIle`, 宏通常依赖这些表头。

## 2. 准备目录结构

建议正式运行目录使用英文路径, 避免空格和特殊字符。例如:

```text
D:\maizsim_case\
  ExcelInterface\
  CreateSoils\
  runs\
    Water.DAT
    WaterBound.DAT
```

其中:

| 目录或文件 | 作用 |
|---|---|
| `ExcelInterface` | 存放 Excel 宏接口文件, 如 `read plant filesV9_mulch (integrated).xlsm` |
| `Models` | 存放 `2dMAIZSIM.exe` 和 `Maizsim.dll`, Python/TOML 流程会自动复制到每个 selected run 目录 |
| `CreateSoils` | 存放 `CreateSoilFiles.exe`, `Rosetta.exe`, `GridGenDll.dll` 等工具 |
| `runs` | 模拟根目录, 每个 run 会在其下生成一个子目录 |
| `Water.DAT`, `WaterBound.DAT` | 通用水分参数文件, 通常放在模拟根目录或示例指定位置。Python/TOML 流程会把 `WaterBound.DAT` 自动复制到每个 selected run 目录, 并改写 `run.dat` 引用 |

## 3. 在 Excel 接口中设置路径

打开宏接口文件:

```text
ExcelInterface-master/ExcelInterface/read plant filesV9_mulch (integrated).xlsm
```

首页通常需要设置:

```text
Input excel file:        参数表 xlsx
Root Path:               模拟根目录, 如 D:\maizsim_case\runs
MaizsimPath:             Excel 接口需要写入的模型程序目录
CreateSoils:             CreateSoilFiles.exe 所在目录
ExcelInterface:          read plant filesV9_mulch (integrated).xlsm 所在目录
Weather CSV File Folder: 天气 CSV 所在目录
```

在 Python/TOML 流程中, `2dMAIZSIM.exe` 和 `Maizsim.dll` 的复制来源固定为 `Models` 目录, 不是 `MaizsimPath` 字段。`MaizsimPath` 仍会写入 Excel 接口, 以保持宏原始字段完整。

设置完成后启用宏, 选择需要运行的 `ID`, 再执行生成流程。

## 4. 参数表的核心逻辑

`Description` 是主表。每一行代表一个模拟运行。其他 sheet 通过 ID 与 `Description` 关联。

常见关联关系如下:

| `Description` 字段 | 对应 sheet 或文件 | 含义 |
|---|---|---|
| `ID` | 多个管理表 | 每个模拟的唯一编号 |
| `WeatherID` | `Weather`, 天气 CSV | 天气序列编号 |
| `ClimateID` | `Climate`, `Weather`, 天气 CSV | 地点或气候编号 |
| `SoilFile` | `Soil`, `GridRatio` | 土壤剖面和网格文件编号 |
| `Hybrid` | `Variety` | 品种参数 |
| `Biology` | `Biology` | 生物过程参数 |
| `Solute` | `Solute` | 溶质参数 |
| `Gas_CO2`, `Gas_O2`, `Gas_File` | `Gas` | 气体扩散参数 |
| `MulchGeo` | `MulchGeo` | 覆盖物几何参数 |
| `MulchDecomp` | `MulchDecomp` | 覆盖物分解参数 |
| `path`, `Path` | 输出目录 | 每个模拟生成文件的子目录 |

简单理解:

```text
Description = run 索引表
ClimateID = 地点和气候读取规则
WeatherID = 一套天气时间序列
SoilFile = 一套土壤剖面和网格配置
```

## 5. 最少需要检查的 sheet

通常一个新模拟至少需要检查这些 sheet:

| sheet | 需要填写或核对的内容 |
|---|---|
| `Description` | 每个模拟一行, 设置 ID, 天气, 土壤, 品种, 输出路径等 |
| `Climate` | 经纬度, 天气变量开关, 单位转换系数, 平均风速/RH/CO2 |
| `Weather` | `ClimateID`, `WeatherID`, 天气 CSV 来源, 日/小时类型 |
| `Time` | 起止日期, 时间步长, `Daily/Hourly`, `WeatherDaily/WeatherHourly` |
| `Init` | 种植密度, 经纬度, 海拔, 播期, 结束日期, 行距, 播深 |
| `Soil` | 土层深度, 初始水势或含水量类型, NO3/NH4, 温度, 质地, 容重等 |
| `GridRatio` | 网格比例, 播深, 根系初始范围, 底边界条件 |
| `Variety` | 玉米品种参数 |
| `Fertilization` | 施肥日期, 用量, 深度, 有机残体或粪肥输入 |
| `Irrig`, `Irrig_data` | 灌溉日期或日期范围, 灌溉量, 深度, 类型 |
| `Tillage` | 是否耕作, 播前天数, 深度 |
| `Solute`, `Gas`, `Biology`, `WaterMovParam` | 可先复制示例默认值, 再按研究问题修改 |

## 6. `Climate` sheet 与天气 CSV 的区别

`Climate` sheet 是地点和天气解释规则。天气 CSV 是逐日或逐小时的实际气象序列。

| 项目 | `Climate` sheet | 天气 CSV |
|---|---|---|
| 作用 | 定义地点信息, 变量开关, 单位转换和缺测默认值 | 提供模型运行所需的时间序列天气数据 |
| 粒度 | 通常一个 `ClimateID` 一行 | 每个日期或每个小时一行 |
| 是否随时间变化 | 基本不随时间变化 | 随日期或小时变化 |
| 典型字段 | `Latitude`, `Longitude`, `DailyWind`, `RelHumid`, `DailyCO2`, `Bsolar`, `Erain`, `AvgWind`, `RH`, `AvgCO2` | `date`, `hour`, `srad`, `wind`, `RH`, `rain`, `tmax`, `tmin`, `temperature`, `CO2` |
| 主要回答 | 这个地点在哪里, 有哪些天气变量, 单位怎么转换, 缺测时用什么默认值 | 每一天或每小时的辐射, 温度, 降雨, 风速, 湿度, CO2 是多少 |

中间还有一个 `Weather` sheet, 作用是桥接 `Description`, `Climate` 和天气 CSV:

```text
Description -> WeatherID / ClimateID
Weather sheet -> 指定 WeatherID 来自哪个 CSV, 是 daily 还是 hourly
Climate sheet -> 指定 ClimateID 的地点和转换规则
天气 CSV -> 存放实际逐日或逐小时数据
```

同一个 `ClimateID` 可以对应多个 `WeatherID`。例如同一地点和同一经纬度下, 不同年份或不同处理可以使用不同天气序列。

## 7. 天气 CSV 格式

示例天气 CSV 表头:

```text
Dummy,ClimateID,WeatherID,jday,date,hour,srad,wind,RH,rain,tmax,tmin,temperature,CO2
```

基本规则:

- 所有列名都应保留, 即使某些列为空。
- 日天气通常需要 `tmax` 和 `tmin`。
- 小时天气通常需要 `hour` 和 `temperature`。
- `wind`, `RH`, `CO2` 可根据 `Climate` 中开关决定是否填写。
- `ClimateID` 和 `WeatherID` 必须能在 Excel 的 `Climate`, `Weather`, `Description` 中对应上。
- 降雨和辐射列建议至少前几行使用 `0.0001` 这类小数, 避免 Excel 或 SQL 自动把整列识别成整数。
- 单位不一致时, 优先在 `Climate` 表中设置转换系数。例如降雨输入为 mm, 而模型需要 cm 时, 可设置 `Erain=0.1`。

## 8. 用 Excel 宏生成输入文件

操作流程:

1. 打开 `read plant filesV9_mulch (integrated).xlsm`。
2. 启用宏。
3. 填写参数表路径, 模拟根目录, 模型程序目录, `CreateSoils` 目录和天气 CSV 目录。
4. 点击选择 ID 并运行宏。
5. 宏会按 `Description.path` 或 `Description.Path` 创建各模拟子目录。
6. 每个子目录中会生成 Maizsim 输入文件和 `grid1.bat`。

如果只手动运行 Excel 宏, soil/grid 文件通常还需要运行 `grid1.bat`。如果使用本文档中的 Python/TOML 流程, `pixi run filecheat` 会在宏完成后自动生成 soil/grid 文件。

## 8.1 使用 Python/TOML 自动调用 Excel 宏

如果不想每次手动打开 Excel 接口, 可以使用 Python 脚本读取 TOML 配置, 自动写入接口路径, 指定需要生成的 `Description.ID`, 并调用现有 VBA 宏生成输入目录。

相关文件:

| 文件 | 作用 |
|---|---|
| `maizsim_input_example.toml` | 示例配置文件, 每个字段前都有注释, 说明用途, 必填性和注意事项。 |
| `maizsim_generate_inputs.py` | 根目录入口脚本, 默认读取同级 `maizsim_input_example.toml`, 适合日常调用。 |
| `tools/maizsim_generate_inputs.py` | 兼容旧命令的入口脚本, 需要显式传入 `--config`。 |
| `tools/maizsim_inputs/` | 主实现模块包, 负责读取 TOML, 校验参数表, 复制宏工作簿副本, 调用 Excel 宏。 |
| `tools/vba/RunConfiguredIds.bas` | 非交互 VBA 包装入口, 从隐藏 sheet `_PythonConfig` 读取 selected IDs, 不再弹窗选择 ID。 |

使用前需要满足:

- 在 Windows 上安装 Microsoft Excel。
- pixi 环境中安装 `pywin32`。
- Excel 信任中心启用 `Trust access to the VBA project object model`, 否则 Python 无法向自动化副本导入 VBA 包装模块。
- TOML 中可以使用相对路径。脚本会优先按配置文件所在目录解析, 也会尝试当前命令运行目录, 工作区目录和 `ExcelInterface-master` 目录。调用 Excel 宏前, 脚本会把这些路径转换为绝对路径并写入 `Interface!B1:B6`。
- 为了减少歧义, 建议在 `示例输入` 目录下执行命令。

先执行 dry-run 校验配置和参数表关联:

```powershell
pixi run check
```

dry-run 会检查:

- TOML 必填字段是否存在。
- 路径是否存在。
- `selected_ids` 是否存在于 `Description.ID`。
- 参数表是否包含宏依赖的关键 sheet 和字段。
- 所选 run 中的天气, 气候, 土壤, 品种, 生物学, 溶质, 气体, 覆盖物, 水分运动, 耕作, 时间, 初始条件和施肥等引用是否能在对应 sheet 中找到。

确认无误后执行生成:

```powershell
pixi run filecheat
```

脚本不会修改原始宏工作簿 `read plant filesV9_mulch (integrated).xlsm`。它会复制一个自动化副本到 TOML 中的 `run.automation_workbook`, 再向副本写入路径和隐藏配置 sheet, 调用 `RunConfiguredIds` 宏, 自动把宏生成的 `run<ID>.dat` 规范化为 `run.dat`, 自动把 `WaterBound.DAT` 复制到每个 selected run 目录并改写 `run.dat` 引用, 自动复制 `2dMAIZSIM.exe` 和 `Maizsim.dll`, 最后自动调用 `CreateSoilFiles.exe` 生成 soil/grid 文件。若要使用其他 TOML 配置, 仍可显式传入 `--config`:

```powershell
pixi run python ExcelInterface-master/maizsim_generate_inputs.py --config ExcelInterface-master/your_config.toml --dry-run
```

## 9. 生成 soil/grid 文件

使用 Python/TOML 流程时, `pixi run filecheat` 会自动生成网格和土壤文件, 不需要手动执行 `grid1.bat`。自动生成完成后, 每个 run 目录中应出现 `.soi`, `.grd`, `.nod` 文件。

同一流程还会把 `WaterBound.DAT` 放到每个 selected run 目录下, 因为原始宏生成的 `run<ID>.dat` 默认引用模拟根目录中的公共 `WaterBound.DAT`, Python/TOML 流程会在规范化为 `run.dat` 后把引用改写到对应 run 目录。这样多个算例可以各自保留自己的水分边界文件副本。

同一流程还会把 `Models` 目录中的 `2dMAIZSIM.exe` 和 `Maizsim.dll` 复制到每个 selected run 目录, 方便进入单个算例目录后直接运行模型。

如果只手动运行 Excel 宏, 或需要排查 `CreateSoilFiles.exe` 命令, 可以用 `grid1.bat` 手动重跑。

可在模拟根目录下使用批处理遍历:

```bat
for /R "D:\maizsim_case\runs" %%g in (.) do (
  pushd %%g
  if exist grid1.bat grid1.bat
  popd
)
```

单个目录中 `grid1.bat` 的典型内容类似:

```bat
D:\Maizsim07\CreateSoils\CreateSoilFiles.exe "D:\MAIZSIM07\AgMipEt\Iowa06\Iowa06.lyr" /GN Iowa06 /SN Harps
del output
del element_elm
del grid_bnd
del datagen2.dat
Dir *.* > dir.txt
```

## 10. 运行模型

进入 selected run 目录后运行:

```powershell
.\2dMAIZSIM.exe .\run.dat
```

如果使用仓库示例结构, 可以进入 `Wye07` 目录后运行:

```powershell
.\2dMAIZSIM.exe .\run.dat
```

其中 `run.dat` 是 Python/TOML 流程把宏生成的 `run<ID>.dat` 规范化后的最终 run 文件。

## 11. 制作完成后的检查清单

生成输入前建议逐项检查:

- `Description.ID` 每行唯一。
- `Description.path` 或 `Description.Path` 每行唯一或符合预期。
- 所有 ID 在对应 sheet 中能找到。
- `ClimateID` 和 `WeatherID` 同时匹配 Excel 表和天气 CSV。
- `Time` 中日/小时设置与天气文件一致。
- 土层 `Bottom depth` 递增。
- 土壤 `Sand + Silt + Clay` 接近 100。
- 如果 `HNew` 表示基质势, 通常应为负值。
- 播期, 结束日期, 施肥日期和灌溉日期均落在天气数据范围内。
- `Water.DAT` 和 `WaterBound.DAT` 放在模型期望的位置, 其中 `WaterBound.DAT` 会由 `pixi run filecheat` 自动补齐到每个 selected run 目录, 并同步改写 `run.dat` 引用。
- `2dMAIZSIM.exe` 和 `Maizsim.dll` 会由 `pixi run filecheat` 自动复制到每个 selected run 目录。
- 运行 `pixi run filecheat` 后子目录中确实生成 grid/soil 相关文件。
- 运行 `.\2dMAIZSIM.exe .\run.dat` 后无路径错误, 文件缺失错误或天气读取错误。

## 12. 建议的首个自定义案例流程

如果是第一次制作自己的输入, 建议按以下顺序做:

1. 复制 `MDEasternShore (maize)/MD-DE inputs.xlsx`。
2. 只保留或只运行其中一个 `Description.ID`。
3. 先只修改 `Path`, `WeatherID`, `ClimateID`, 播期, 结束日期和天气 CSV。
4. 确认宏能生成文件。
5. 确认 `pixi run filecheat` 能生成 soil/grid 文件。
6. 确认 `.\2dMAIZSIM.exe .\run.dat` 能启动并运行。
7. 再逐步修改土壤, 品种, 施肥, 灌溉和气体参数。

不要一开始同时修改大量 sheet。先让一个最小运行成功, 再扩展到批量模拟。
