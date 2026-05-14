# MAIZSIM IES 数据同化框架

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

## 第一版限制

- `workflow.py` 通过约定接口调用 `prior`, `observation`, `ensemble`, `output_reader`, `update` 等模块；接口缺失时, dry-run 使用内置兜底逻辑, 正式 forecast 会提示缺少接口。
- 参数写入、模型运行和 `g01/G03` 解析由低层模块负责；workflow 只做配置、目录、迭代、指标和文件保存编排。
- 内置 `base_run_dir` 是快速验证算例, 不是完整真实观测实验。
- `JuvenileLeaves` 只作为外层枚举标签传入 workflow, 不作为连续参数更新。
