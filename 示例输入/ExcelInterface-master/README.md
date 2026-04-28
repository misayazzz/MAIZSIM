# ExcelInterface

本版本及其输入文件适用于 2DSOIL 3.1.2.0 和 Maizsim 1.8.1, 上传日期为 2025-09-23.

这是一个基于 Excel 的接口, 用于创建作物模型所需的输入文件.
输入数据存储在 Excel 电子表格中.
一个特殊的 Excel 文件包含 VBA 代码, 可从电子表格中提取数据, 并创建运行 Maizsim 所需的文件夹结构和输入文件. 天气源 CSV 需要预先准备; VBA 程序会在每个运行目录中生成 `.wea` 天气文件和 `grid1.bat` 文件. 当前 Python/TOML 自动化流程会在宏完成后把 `run<ID>.dat` 规范化为 `run.dat`, 复制 `WaterBound.DAT` 和 `Models` 中的模型运行文件到每个 selected run 目录, 改写 `run.dat` 引用, 并直接调用 `CreateSoilFiles.exe` 创建 grid 和 soil 文件, `grid1.bat` 保留为人工排查手段.

Models 文件夹中包含可执行程序.

## 推荐阅读顺序

如果你是第一次用本接口生成模型输入, 优先阅读 `Python构建模型输入文件指南.md`. 它是当前推荐的主使用说明, 按新手操作流程说明如何用 Python + TOML 自动调用 Excel 宏生成输入目录.

如果你需要理解示例表应该选哪个, `Climate` 和天气 CSV 有什么区别, 或者想查看更完整的 Excel 参数表背景, 再阅读 `Maizsim输入制作指南.md`.

可用示例包括 Kansas dryland 数据, Maryland Eastern Shore 数据, 以及 AgmipET2 数据.
其中 Maryland Eastern Shore 示例已发表于 Kim et al., 2012.
AgmipET2 示例来自 Kimball et al. 的论文: https://doi.org/10.1016/j.agrformet.2023.109396

2024-05-23 新增了 Maizsim 的输入和输出文件, 这些文件用于我们在 Geoderma 发表的 CO2 模型测试.
2026-01-30 新增了用于比较 Maizsim 在热带和温带地点表现的文件, 相关论文正在审稿中.

## 目录说明

| 文件夹 | 作用 |
|---|---|
| `CreateSoilFIles` | 生成 2DSOIL 网格和土壤文件的工具目录, 包含 `CreateSoilFiles.exe`, `Rosetta.exe`, `GridGenDll.dll` 和 `vangenuch.xls`. |
| `Example input` | 示例输入数据目录, 包含不同研究案例的 Excel 参数表, 天气 CSV, 水分参数文件和中文整理说明. |
| `ExcelInterface` | Excel 宏接口和使用文档目录, 主要用于从 Excel 参数表生成 Maizsim 所需输入文件和运行目录结构. |
| `Variable Documentation` | 变量说明目录, 按模块保存输入字段说明, 如气候, 作物品种, 土壤, 网格比例, 溶质和输出文件等. |

## Example input 案例说明

| 案例文件夹 | 作用 |
|---|---|
| `AgmipET2` | AgMIP ET2 玉米模拟示例, 覆盖多年份, 多地点和多水分管理条件, 适合测试批量输入生成和灌溉/雨养对比. |
| `CO2_Respiration_CaseStudy1` | CO2/土壤呼吸参数敏感性案例, 重点是气体扩散和土壤过程参数变化, 适合研究土壤 CO2, 土壤呼吸或相关参数反演. |
| `CO2_Respiration_CaseStudy2` | CO2/土壤呼吸的最小单运行案例, 适合快速检查 Excel 接口, 天气读取和气体模块设置. |
| `Kansas` | Kansas 多站点玉米模拟案例, 包含日天气和小时天气, 多地点, `AshDry`/`AshIrr` 处理标签和补充灌溉运行. |
| `MDEasternShore (maize)` | Maryland Eastern Shore 玉米案例, 覆盖 Wye 和 Del 两个地点的小时天气运行, 适合无显式灌溉条件下的地点, 年份和土壤对照分析. |
| `Tropical_Temperate_Study` | 热带 Rahuri 与温带 Marshall 的多年对比案例, 适合比较气候带差异, 年际天气差异和跨气候带泛化表现. |

运行模型时, 推荐使用 `pixi run filecheat` 生成的 selected run 目录. Python/TOML 流程会把 `2dMAIZSIM.exe` 和 `Maizsim.dll` 复制到每个 run 目录, 并把最终 run 文件命名为 `run.dat`.
例如, 如果已生成 `d:/agmipET2/run_01`, 则进入该目录后运行模型:

```powershell
cd d:/agmipET2/run_01
./2dMAIZSIM.exe ./run.dat
```

如果使用本仓库中的文件夹结构, 同样进入具体 run 目录:

```text
Y:\ExcelInterface\Example input\AgmipET2\run_01
```

则可按如下方式运行模型:

```powershell
./2dMAIZSIM.exe ./run.dat
```

在接口中, 文件应按如下方式设置:

```text
Input excel file:        Y:\ExcelInterface\Example input\AgmipET2\AGMIPET2Sim.xlsx
Root Path:               Y:\ExcelInterface\Example input\AgmipET2
MaizsimPath:             Y:\ExcelInterface
CreateSoils:             Y:\ExcelInterface\CreateSoilFIles
ExcelInterface:          Y:\ExcelInterface\ExcelInterface
Weather CSV File Folder: Y:\ExcelInterface\Example input\AgmipET2
```
