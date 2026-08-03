# MAIZSIM IES 数据同化框架

MAIZSIM有限供水等效滴灌线源的30 mm三土壤验证入口为`python -m da_framework.mode6_30mm_validation`，三网格和三时间步收敛入口为`python -m da_framework.mode6_convergence --kind grid|time`。输入输出契约、守恒方程和当前验收结果见[FINITE_SUPPLY_DRIP_LINE_SOURCE.md](../FINITE_SUPPLY_DRIP_LINE_SOURCE.md)。

本目录放 MAIZSIM/2DSOIL 的第一版 IES 数据同化框架。所有配置、运行入口、示例观测和运行产物都限制在 `DA_Framework/` 下。

## 目录结构

```text
DA_Framework/
  README.md
  run_maizsim_ies.py
  maizsim_ies_example.toml
  examples/synthetic_observations.csv
  base_runs/SingleLayerLoam2D/
  da_framework/
    __init__.py
    config.py
    cli.py
    prior.py
    observation.py
    update.py
    workflow.py
    ensemble.py
    parameter_writer.py
    model_runner.py
    output_reader.py
    metrics.py
    errors.py
  tests/
```

## 默认设置

- 正式默认: `n_ensemble = 100`, `n_iter = 3`。
- 小 ensemble 只用于连通性测试, 不建议用于正式同化结论。
- 连续 IES 参数: `n`, `thetaS`, `LM_min`, `Rmax_LTAR`, `StayGreen`。
- `thetaS` 默认写入 `.soi` 字段 `ths`, `th`, `thk`。
- `JuvenileLeaves` 候选值为 `16, 17, 18, 19, 20`, 只做外层枚举, 不进入连续 IES 更新。

## 配置文件

示例配置: `DA_Framework/maizsim_ies_example.toml`。

关键段落:

```toml
[model]
base_run_dir = "base_runs/SingleLayerLoam2D"
executable = "2dMAIZSIM.exe"
run_file = "run.dat"
var_file = "PI34M91.var"
soi_file = "Loam_200cm.soi"
```

该示例路径指向 `DA_Framework/base_runs/SingleLayerLoam2D`。该目录是第一阶段单层均质壤土 base run, `run.dat` 使用相对路径, ensemble 成员复制后仍能独立运行。

base run 的土壤设置为一个材料:

```text
NumMat = 1
thetaS = 0.430
n = 1.560
thetaR = 0.078
```

验证窗口为 `2007-04-28` 到 `2007-07-04`, 覆盖 10 个 5 天间隔观测窗口, 用于快速检验 IES 连接 MAIZSIM/2DSOIL 的可行性。

## Base Run 要求

`base_run_dir` 应能独立运行 MAIZSIM, 至少包含:

```text
2dMAIZSIM.exe
Maizsim.dll
run.dat
*.var
*.soi
*.wea
*.tim
run.dat 引用的其他输入文件
```

模型运行命令等价于:

```powershell
.\2dMAIZSIM.exe .\run.dat
```

## 观测 CSV

观测文件使用长表格式:

```csv
date,variable,depth_top_cm,depth_bottom_cm,value,std
2007-05-20,LAI,,,0.000000,0.5
2007-05-20,theta,10,10,0.230161,0.05
2007-05-20,theta,30,30,0.244771,0.05
```

有效观测要求 `value` 非空且 `std > 0`。读取后按 `date -> variable -> depth_top_cm -> depth_bottom_cm` 固定排序。
示例观测参照 DA-AquaCrop `PythonKalman` 分支的设置: 5 天观测间隔, 每个窗口包含 `theta(10 cm)`, `theta(30 cm)` 和 `LAI`; `theta` 的 `std` 为 `0.05`, `LAI` 的 `std` 为 `0.5`。DA-AquaCrop 的 `obs_var.dat` 虽然命名为 var, 但代码按标准差读取; 本框架对应写入 `std` 列, 并在 IES 更新中按 `sqrt(n_iter)` 缩放。`theta` 来自 `G03` 的 `thNew` 体积含水量; 当 `depth_top_cm == depth_bottom_cm` 时, 框架按日尺度面积加权深度剖面对该点深度做线性插值。

## 运行命令

从仓库根目录:

```powershell
python DA_Framework/run_maizsim_ies.py --config DA_Framework/maizsim_ies_example.toml --dry-run
```

从 `DA_Framework/` 目录:

```powershell
python run_maizsim_ies.py --config maizsim_ies_example.toml --dry-run
```

正式单次 IES:

```powershell
python DA_Framework/run_maizsim_ies.py --config DA_Framework/maizsim_ies_example.toml
```

外层枚举 `JuvenileLeaves`:

```powershell
python DA_Framework/run_maizsim_ies.py --config DA_Framework/maizsim_ies_example.toml --juvenile-enum
```

## 输出

运行产物默认写入:

```text
DA_Framework/runs/experiment_001/
  statistics_da/Initial-Params.txt
  statistics_da/Kalman_Update/Iter-N-Params.txt
  results/forecast_matrix_iter_N.csv
  results/rmse_summary.csv
```

`--dry-run` 只读取配置、读取观测并生成先验集合, 不运行 `2dMAIZSIM.exe`。

## 测试命令

仓库已有 pixi 环境时:

```powershell
pixi run --manifest-path pixi.toml python -m compileall DA_Framework/da_framework DA_Framework/tests DA_Framework/run_maizsim_ies.py
pixi run --manifest-path pixi.toml python -m unittest discover -s DA_Framework/tests
```

也可用当前 Python 3.12:

```powershell
python -m compileall DA_Framework/da_framework DA_Framework/tests DA_Framework/run_maizsim_ies.py
python -m unittest discover -s DA_Framework/tests
```

## 滴灌验证工具

当前运行时只有固定接触区有限供水等效滴灌线源。示例输入生成器接受`EmitterFlowLph`、`EmitterSpacingCm`、`ContactWidthCm`、事件起止时刻和一个`x=0`地表节点；它拒绝旧格式的`wAppl`、`DripMode`、`DripWetWidthMax`、`DripSpreadMode`和`DripSourceWidth`。旧的`drip_validation`、`drip_regression`、`drip_precision_validation`和`hydrus_aligned_validation`是历史研究辅助代码，不是当前`.drp`输入生成器或验收入口；它们生成的旧格式不能被当前Fortran滴灌入口接受。

求解器保留原Mode6的Newton活动边界内核：有限供水只在`[0, ContactWidthCm]`固定接触区内守恒分配；通量边界若需要正压力，该节点切换为`h=0`水头边界。求解失败只能缩小同一Richards子步并重算，不能回退、跳步或放宽闭合阈值。未入渗水先进入固定接触区的局部积水，超过`hCritS`容量后记入溢流账本，不扩大接触区。G05输出包括：

```text
DripMode6Accepted
DripMode6Remaining
DripMode6HeadNodes
DripMode6FluxNodes
DripMode6Iterations
DripMode6SolverLimit
DripMode6BoundaryLimit
DripMode6ClosureResidual
DripMode6StepCuts
DripMode6NonlinearCuts
DripMode6SupplyCuts
DripMode6MassCuts
DripMode6MinDtDays
```

`da_framework.mode6_30mm_validation`用于笛卡尔半域的单源30 mm事件验证。滴灌带固定在地表对称轴`x=0`；壤土、砂壤土和黏壤土均使用相同的滴头流量、间距、接触宽度和事件历时。湿润宽度、深度和面积在停水时刻计算，阈值为`delta_theta=0.005`，采用三角形单元内线性插值，并报告远端横边界、底边界和局部加密区截断。三网格GCI仅在单调、正表观阶且进入渐近区时有效。

三种质地的标准van Genuchten参数需补充MAIZSIM近饱和导水率桥接参数。验证工具沿用HUTD06七层材料的一致规则：`Kk = 0.9 Ks`、`thk = ths - 0.004`，并拒绝`Kk = Ks`或`thk = ths`。后两种退化输入会关闭近饱和桥接；尤其在较小`n`的黏壤土中，会保留Mualem导水率在饱和端附近的奇异斜率，不能把由此产生的Newton失败误判为滴灌边界机制失败。

HUTD06的`KAT=2`表示Cartesian垂直剖面，滴灌源在数学上是单位出平面长度上的线源。验证脚本使用滴头间距把L/h换算为半域线供水率；其中30 mm表示整个半域上的等效灌水深度，而不是接触区局部水深。

`da_framework.faloye_2025_reference`提供Faloye等（2025）的10组地表点源湿润宽度/深度汇总值及可审计来源信息。该数据缺少完整土壤水力参数、硬盘层参数、滴头作用面积、原始重复和`±`统计量定义，且三维点源几何与HUTD06线源不直接兼容，因此只允许用于趋势和量级软诊断，不能单独判定通过或论文就绪。

相关最小测试命令：

```powershell
pixi run --manifest-path pixi.toml python -m pytest DA_Framework/tests/test_maizsim_drip_inputs.py DA_Framework/tests/test_mode6_fortran_contract.py DA_Framework/tests/test_mode6_active_boundary_scenarios.py DA_Framework/tests/test_mode6_30mm_validation.py DA_Framework/tests/test_hutd06_grid_refinement.py DA_Framework/tests/test_faloye_2025_reference.py -q
```

## 第一版限制

- `workflow.py` 通过约定接口调用 `prior`, `observation`, `ensemble`, `output_reader`, `update` 等模块；接口缺失时, dry-run 使用内置兜底逻辑, 正式 forecast 会提示缺少接口。
- 参数写入、模型运行和 `g01/G03` 解析由低层模块负责；workflow 只做配置、目录、迭代、指标和文件保存编排。
- 内置 `base_run_dir` 是快速验证算例, 不是完整真实观测实验。
- `JuvenileLeaves` 只作为外层枚举标签传入 workflow, 不作为连续参数更新。
