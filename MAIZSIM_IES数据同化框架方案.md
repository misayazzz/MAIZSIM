# MAIZSIM IES 数据同化框架方案

## 说明

本文档合并了敏感参数候选方案和参照 `DA-AquaCrop` 仓库 `PythonKalman` 分支实现 MAIZSIM/2DSOIL IES 数据同化框架的设计方案。本文档只给出后续实现方案, 未实现代码。

目标是在新开对话中, 参照 `PythonKalman` 分支的纯 Python IES 框架, 为当前 MAIZSIM/2DSOIL 二维作物模型建立参数校准和数据同化流程。

参考仓库:

```text
https://github.com/misayazzz/DA-AquaCrop.git
branch: PythonKalman
参考提交: 7d417e6
```

## 同化目标和敏感参数候选集

后续 IES 数据同化实验的目标观测变量为:

- 土壤含水量: 模型输出中对应 `thNew`, 可按观测深度聚合。
- 叶面积指数: 模型输出中对应 `LAI`。

候选参数来自敏感性分析图中的综合敏感性排序。图中蓝色参数主要对应作物生长和 LAI, 绿色斜线参数主要对应土壤水分过程。

| 排序 | 参数 | 图中敏感性值 | 参数类别 | 主要关联观测变量 | 备注 |
|---:|---|---:|---|---|---|
| 1 | `JuvenileLeaves` | 0.79 | 作物物候 / 叶片发育 | LAI | 整数参数, 影响叶片出现和 LAI 时序。 |
| 2 | `LM_min` | 0.69 | 作物叶面积结构 | LAI | 连续参数, 影响潜在最大叶长和叶面积幅值。 |
| 3 | `n` | 0.40 | 土壤水力参数 | 土壤含水量 | van Genuchten 形状参数, 对含水量动态敏感。 |
| 4 | `thetaS` | 0.33 | 土壤水力参数 | 土壤含水量 | 饱和含水量, 影响可蓄水空间和含水量水平。 |
| 5 | `Rmax_LTAR` | 0.28 | 作物叶片发育速率 | LAI | 连续参数, 影响叶片出现速率和 LAI 达峰时间。 |
| 6 | `StayGreen` | 0.24 | 作物叶片衰老 / 保绿性 | LAI | 连续参数, 影响后期绿叶维持和 LAI 衰减。 |

建议将以下 6 个参数作为第一轮数据同化的候选参数池:

```text
JuvenileLeaves
LM_min
n
thetaS
Rmax_LTAR
StayGreen
```

第一版 IES 框架建议只更新连续参数:

```text
n
thetaS
LM_min
Rmax_LTAR
StayGreen
```

`JuvenileLeaves` 是整数参数, 不建议直接作为 IES 连续更新参数。推荐在外层枚举:

```text
JuvenileLeaves = 16, 17, 18, 19, 20
```

每个固定 `JuvenileLeaves` 情景下, 内层 IES 只更新上述连续参数。

## 参数边界和写入约束

以下边界来自当前 `sensitive` 分支中 `SingleLayerLoam2D` 算例的敏感性分析参数设置, 可作为第一轮同化的先验范围。

| 参数 | 当前值 | 下限 | 上限 | 类型 | 约束 |
|---|---:|---:|---:|---|---|
| `JuvenileLeaves` | 18 | 16 | 20 | 整数 | 外层枚举, 不进入连续 IES 更新。 |
| `LM_min` | 125.0 | 112.5 | 130.0 | 连续 | 保持为正值。 |
| `n` | 1.56 | 1.40 | 1.72 | 连续 | 必须大于 1。 |
| `thetaS` | 0.430 | 0.387 | 0.473 | 连续 | 满足 `thetaR < thetaS < 1`。 |
| `Rmax_LTAR` | 0.53 | 0.477 | 0.58 | 连续 | 保持为正值。 |
| `StayGreen` | 4.5 | 4.05 | 4.95 | 连续 | 保持为正值。 |

写入模型文件时需要注意:

- `thetaS` 不应只更新单个字段, 应同步更新土壤文件中与饱和含水量对应的字段。
- `n` 应保持在大于 1 的范围内, 避免土壤水分特征曲线失去物理意义。
- `JuvenileLeaves` 进入模型前必须是整数。
- 所有参数更新后都应进行边界处理, 避免滤波发散导致模型运行失败。

## IES 框架下 JuvenileLeaves 的处理建议

`JuvenileLeaves` 是整数参数, 而 IES 通常基于连续参数扰动、近似高斯分布和参数-观测协方差更新。若直接把 `JuvenileLeaves` 当作普通连续参数放入 IES, 容易出现以下问题:

- IES 可能更新出 `17.43` 这类模型无法直接解释的连续值。
- 若在模型运行前强制四舍五入, 参数响应会变成阶梯函数。
- 在没有跨过整数边界时, IES 更新值变化但模型输出可能完全不变。
- 四舍五入导致的非连续响应会影响参数-观测协方差估计, 使更新不稳定。

因此, 推荐将 `JuvenileLeaves` 作为离散品种 / 物候参数处理, 不作为 IES 的普通连续更新参数。

### 推荐做法: 外层枚举 + 内层 IES

在允许范围内固定 `JuvenileLeaves` 的候选整数值:

```text
JuvenileLeaves = 16, 17, 18, 19, 20
```

对每一个固定取值分别运行一套 IES, 只更新其余连续敏感参数:

```text
n
thetaS
LM_min
Rmax_LTAR
StayGreen
```

最后使用 LAI 和土壤含水量观测共同计算目标函数, 比较不同 `JuvenileLeaves` 情景下的同化效果, 选择联合误差最小且验证期表现稳定的取值。

该做法的优点是:

- 符合 IES 更适合连续参数估计的数值假设。
- 避免整数参数四舍五入造成的不连续响应。
- `JuvenileLeaves` 只有 5 个候选值, 枚举成本可控。
- 每个整数情景可独立运行, 便于并行计算和结果比较。
- 结果解释清楚, 可将 `JuvenileLeaves` 视为离散物候结构参数。

若需要测试 `JuvenileLeaves` 对 IES 的影响, 也可以设置一个连续隐变量, 在每次模型运行前执行:

```text
JuvenileLeaves_model = round(clip(JuvenileLeaves_continuous, 16, 20))
```

但该方法不建议作为主方案。它会使 IES 更新空间与模型实际参数空间不一致, 容易造成协方差退化或参数更新效率低。

建议实验流程:

1. 建立 5 个离散情景, 分别固定 `JuvenileLeaves = 16, 17, 18, 19, 20`。
2. 每个情景下使用 IES 更新连续参数 `n`, `thetaS`, `LM_min`, `Rmax_LTAR`, `StayGreen`。
3. 所有情景使用相同的集合规模、观测误差设定、初始参数扰动范围和评价指标。
4. 用 LAI 与土壤含水量的联合目标函数比较 5 个情景。
5. 选择最优 `JuvenileLeaves` 后, 在正式同化实验中固定该整数值, 只在线更新连续参数。

论文或报告中可采用如下表述:

> 本研究将 `JuvenileLeaves` 作为离散品种参数处理。由于 IES 框架更适合连续参数估计, 本文对 `JuvenileLeaves` 在允许范围内进行离散枚举；在每一个固定的 `JuvenileLeaves` 情景下, 使用 IES 校准其余连续敏感参数, 并根据 LAI 与土壤含水量的联合目标函数选择最优参数组合。

## 总体实现判断

`PythonKalman` 分支的价值不在于可以直接复制代码, 而在于它已经形成了一套清晰的数据同化工程结构:

1. 读取参数配置和观测数据。
2. 生成先验参数集合。
3. 复制 base 模板为 ensemble 成员目录。
4. 对每个 ensemble 成员写入参数并运行前向模型。
5. 将模型输出映射到观测空间。
6. 使用 IES/Kalman gain 更新参数集合。
7. 保存每轮参数集合、健康度指标和 RMSE 评价。

MAIZSIM 与 SWAP/AquaCrop 的模型输入、输出文件完全不同, 因此不能直接照搬参数写入和输出读取模块。建议只复用框架思想和数学核心, 重新实现 MAIZSIM 专属的文件适配层。

## 第一阶段 base 算例建议

第一版 IES 框架不应直接从复杂多土层、多管理情景或多站点案例开始。建议先设置一个**单层均质壤土 base 算例**, 用它验证 MAIZSIM/2DSOIL 上 IES 参数同化流程是否可行。

推荐 base 算例特征:

- 土壤剖面为单层均质 loam。
- 土壤水力参数只有一组, 即 `thetaS`, `n`, `Alfa`, `thetaR`, `Ks` 不区分层。
- 作物品种参数固定为一个明确 `.var` 文件。
- 运行目录自包含, 包括 `2dMAIZSIM.exe`, `Maizsim.dll`, `run.dat`, `.var`, `.soi`, `.wea`, `.tim` 和其他必要输入。
- 模型能从命令行稳定运行:

```powershell
.\2dMAIZSIM.exe .\run.dat
```

优先使用壤土均质算例的原因:

- 参数维度低, 更容易判断 IES 更新是否合理。
- 土壤含水量输出与土壤水力参数之间关系更直接。
- 避免分层土壤中上层/下层参数可辨识性混淆。
- 更适合用合成观测先验证算法闭环。
- 后续扩展到分层土壤时, 可以把该单层案例作为对照基准。

推荐第一阶段验证目标:

1. 用壤土均质 base run 生成一组真值或合成观测。
2. 扰动连续参数 `n`, `thetaS`, `LM_min`, `Rmax_LTAR`, `StayGreen` 生成先验集合。
3. 同化 LAI 和 0-20 cm 土壤含水量。
4. 检查 IES 是否能降低观测空间 RMSE。
5. 检查后验参数是否仍在物理边界内。
6. 确认可重复运行和并行 ensemble 调度稳定。

只有在该均质壤土算例通过后, 再扩展到分层土壤、多深度土壤含水量观测、多年份或多地点验证。

## PythonKalman 中建议参考的部分

| 参考模块 | 可参考内容 | MAIZSIM 中的对应实现 |
|---|---|---|
| `RunThis.py` | 主入口结构, 命令行参数组织 | `RunMaizsimIES.py` 或 pixi task |
| `PythonCode/ies_workflow.py` | IES 主流程编排 | MAIZSIM IES workflow |
| `PythonCode/ies_update.py` | Kalman gain IES 数学更新, 边界半程回拉, 更新健康度 | 可高度复用思想, 但按 MAIZSIM 参数配置重写接口 |
| `PythonCode/ies_prior.py` | 先验参数集合生成 | 按 MAIZSIM 参数表生成截断正态或均匀集合 |
| `PythonCode/ies_observation.py` | 观测值和观测误差读取, 有效观测筛选 | 读取 LAI 和土壤含水量观测表 |
| `PythonCode/copy_files.py` | 复制 base 到 ensemble 成员目录 | 复制 MAIZSIM 自包含 run 目录 |
| `PythonCode/ies_forecast.py` | 参数写入、运行模型、读取模拟观测的组合 | MAIZSIM forecast 调度 |
| `PythonCode/forward_model_run.py` | 并行运行外部可执行模型, 检查输出 | 并行运行 `2dMAIZSIM.exe run.dat` |
| `PythonCode/get_forward_model_result.py` | 将模型输出转为观测空间矩阵 | 从 `g01/G03` 提取 LAI 和土壤含水量 |
| `tests/test_python_ies_core.py` | 核心数值和文件适配测试思路 | 建立 MAIZSIM IES 单元测试 |

## 不应直接照搬的部分

以下部分与 SWAP/AquaCrop 文件结构强绑定, 应在 MAIZSIM 中重写:

- `parameter.dat` 的解析格式。
- SWAP 的 `swap.swp` 参数表回写。
- AquaCrop/SWAP 作物文件 `CropD.crp` 的参数复写。
- `StaVari/SoilVari` 和 `StaVari/CropVari` 输出读取。
- SWAP 专属 RMSE replay 目录结构。

实现过程中, 如果对 MAIZSIM/2DSOIL 二维作物模型的耦合过程、变量含义、单位转换、文件读写顺序或参数生效位置有任何不确定, 应首先阅读当前仓库根目录下的源码, 而不是直接依据参考仓库或敏感性分析脚本推断。重点源码位置包括:

```text
Crop source/
Soil Source/
```

优先核对:

- MAIZSIM 与 2DSOIL 之间交换哪些状态变量。
- `LAI`, `LeafWP`, `ThetaAvail`, `AWUPS`, `MaxRootDepth` 等变量在代码中如何计算和传递。
- `.var`, `.soi`, `run.dat` 中的字段实际在哪里被读取。
- `g01`, `G03`, `G05` 输出字段的单位和输出频率。
- 土壤含水量、根系吸水和作物 LAI 之间的耦合路径。

MAIZSIM 需要围绕以下文件重建适配:

- 模型运行文件: `2dMAIZSIM.exe`, `Maizsim.dll`, `run.dat`。
- 作物品种参数: `PI34M91.var` 或对应 `.var` 文件。
- 土壤水力参数: `Loam_200cm.soi` 或对应 `.soi` 文件。
- 作物输出: `*.g01`。
- 土壤剖面输出: `*.G03`。
- 水量平衡输出: `*.G05`, 可作为扩展评价。

## 推荐目录结构

实现时应在当前 MAIZSIM 仓库根目录下新建独立目录:

```text
DA_Framework/
```

建议结构:

```text
DA_Framework/
  README.md
  run_maizsim_ies.py
  maizsim_ies_example.toml
  da_framework/
    __init__.py
    cli.py
    config.py
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
    test_ies_update.py
    test_observation.py
    test_parameter_writer.py
    test_output_reader.py
```

其中 `DA_Framework/da_framework/` 放 Python 包代码, `DA_Framework/tests/` 放最小单元测试, `DA_Framework/maizsim_ies_example.toml` 放配置模板, `DA_Framework/run_maizsim_ies.py` 作为主入口。

不建议把 IES 框架代码放入 `示例输入/ExcelInterface-master/tools/`。该目录已有职责是生成 MAIZSIM 输入文件, 而 IES 框架涉及 ensemble 管理、参数更新、模型运行和观测评价, 独立为 `DA_Framework/` 更清晰。

## 参数配置设计

参数配置建议使用 TOML, 每个参数包含:

```toml
[[parameters]]
name = "n"
current = 1.56
lower = 1.40
upper = 1.72
std = 0.08
target_file = "Loam_200cm.soi"
target_fields = ["n"]

[[parameters]]
name = "thetaS"
current = 0.430
lower = 0.387
upper = 0.473
std = 0.02
target_file = "Loam_200cm.soi"
target_fields = ["ths", "thm", "thk"]
```

作物参数建议写入 `.var`:

```text
LM_min      -> PI34M91.var 第一组作物参数行第 4 列
Rmax_LTAR   -> PI34M91.var 第一组作物参数行第 5 列
StayGreen   -> PI34M91.var 第一组作物参数行第 3 列
```

土壤参数建议写入 `.soi`:

```text
n       -> Loam_200cm.soi 第 3 行第 6 列
thetaS  -> ths, thm, thk 同步更新
```

必须保留物理约束:

```text
0 <= thetaR < thetaS < 1
n > 1
所有正值参数保持 > 0
```

## 观测数据设计

目标观测变量:

```text
LAI
soil_water_content
```

推荐使用长表格式, 比 `obs_loc.dat/obs_var.dat` 更适合 MAIZSIM 的多变量、多深度观测:

```csv
date,variable,depth_top_cm,depth_bottom_cm,value,std
2007-06-20,LAI,,,1.25,0.15
2007-06-20,theta,0,20,0.226,0.03
2007-06-30,LAI,,,2.10,0.20
2007-06-30,theta,0,20,0.214,0.03
```

读取时转成 IES 使用的一维观测向量:

```text
d: m x 1
R: m x m 对角矩阵, 对角线为 std^2
有效观测: std > 0 且 value 非缺失
```

观测空间顺序必须固定, 例如按:

```text
date 升序 -> variable -> depth_top_cm -> depth_bottom_cm
```

这样每个 ensemble 成员输出的模拟观测向量 `Y[:, i]` 才能与真实观测向量 `d` 一一对应。

## 输出映射设计

### LAI

从 `*.g01` 读取:

```text
Date/date
time
LAI
```

处理建议:

- 如果 `g01` 是小时输出, 对同一天 LAI 取日均值或指定观测时刻值。
- 如果实测 LAI 是日尺度, 推荐取当天日均值。
- 如果观测日期模型无输出, 可先报错, 不建议默认插值；后续可显式增加插值选项。

### 土壤含水量

从 `*.G03` 读取:

```text
Date
Y
thNew
Area
```

处理建议:

- 观测为 0-20 cm 时, 对 `0 <= Y <= 20` 的节点按 `Area` 加权平均。
- 如果有多个深度, 每个深度区间分别按 `Area` 加权。
- 如果观测是点位土壤水分, 需要明确 `X/Y` 位置匹配规则, 不应混用层平均。

推荐第一阶段只做层平均:

```text
theta_0_20 = sum(thNew_i * Area_i) / sum(Area_i), for 0 <= Y_i <= 20
```

## IES 数学核心

保持 PythonKalman 分支中的 Kalman gain IES 结构:

```text
X_f: p x Ne 参数 forecast 集合
Y_f: m x Ne 模拟观测 forecast 集合
d:   m x 1 观测向量
R:   m x m 观测误差协方差
```

集合异常:

```text
X' = X_f - mean(X_f)
Y' = Y_f - mean(Y_f)
```

协方差:

```text
C_xy = X' Y'^T / (Ne - 1)
C_yy = Y' Y'^T / (Ne - 1)
```

Kalman 增益:

```text
K = C_xy (C_yy + R)^-1
```

扰动观测更新:

```text
X_a = X_f + K (d + e - Y_f)
```

其中 `e` 为按观测误差生成的扰动。多轮 IES 可参考 PythonKalman 的做法, 将观测标准差按 `sqrt(NIter)` 放大, 避免重复使用同一观测时权重过高。

参数越界处理建议沿用“半程回拉”:

```text
若 x < lower: x = (x_forecast + lower) / 2
若 x > upper: x = (x_forecast + upper) / 2
```

## Ensemble 运行设计

MAIZSIM 应以一个已经能独立运行的 base run 目录作为模板:

```text
base_run_dir/
  2dMAIZSIM.exe
  Maizsim.dll
  run.dat
  *.var
  *.soi
  *.wea
  *.tim
  ...
```

IES 运行时建议在 `DA_Framework/runs/` 下生成:

```text
DA_Framework/
  runs/
    experiment_001/
      ensemble/
        000001/
        000002/
        ...
      statistics_da/
        Initial-Params.txt
        Kalman_Update/
          Iter-1-Params.txt
          Iter-2-Params.txt
      results/
        forecast_matrix_iter_0.csv
        forecast_matrix_iter_1.csv
        rmse_summary.csv
```

这样可以把框架代码、配置和运行产物都限制在 `DA_Framework/` 内, 避免污染模型源码和示例输入目录。

每个 ensemble 成员流程:

1. 从 `base_run_dir` 复制到成员目录。
2. 清理旧输出, 如 `*.g01`, `*.G03`, `*.G05`, `2DSOIL03.LOG`。
3. 写入该成员参数到 `.var` 和 `.soi`。
4. 确保 `run.dat` 使用成员目录内的相对路径或正确绝对路径。
5. 执行:

```powershell
.\2dMAIZSIM.exe .\run.dat
```

6. 检查关键输出:

```text
*.g01
*.G03
```

7. 读取输出并映射到观测空间。

## 建议实现顺序

新开对话实现时建议按以下顺序推进, 不要一开始就写完整大框架:

1. **只实现 IES 数学核心**
   - 输入小矩阵 `X_f`, `Y_f`, `d`, `std`。
   - 验证更新结果与显式公式一致。
   - 实现边界半程回拉。

2. **实现观测读取**
   - 读取长表观测 CSV。
   - 生成固定顺序的一维观测向量和标准差向量。
   - 测试缺失值和 `std <= 0` 的筛选。

3. **实现 MAIZSIM 输出读取**
   - 从已有 `LOAM2D.g01` 提取 LAI。
   - 从已有 `LOAM2D.G03` 提取 0-20 cm 面积加权 `thNew`。
   - 用合成观测日期测试输出映射。
   - 若对输出字段含义、单位或时间尺度不确定, 先查 `Crop source/` 和 `Soil Source/` 中对应输出代码。

4. **实现参数写入**
   - 用临时目录复制 `.var/.soi`。
   - 写入 `n`, `thetaS`, `LM_min`, `Rmax_LTAR`, `StayGreen`。
   - 读取文件确认字段被正确替换。
   - 若不确定参数是否真实生效或是否需要同步更新多个字段, 先查根目录源码中读取 `.var/.soi` 的逻辑。

5. **实现单成员 forecast**
   - 复制 base run。
   - 写参数。
   - 运行模型。
   - 读取模拟观测向量。

6. **实现 ensemble forecast**
   - 并行运行多个成员。
   - 失败成员记录日志并停止或按策略剔除。
   - 输出 `Y_f` 矩阵。

7. **实现完整 IES workflow**
   - 生成先验 `X_0`。
   - forecast 得到 `Y_0`。
   - IES 更新得到 `X_1`。
   - 重复迭代。
   - 保存每轮参数集合和 RMSE。

8. **实现 JuvenileLeaves 外层枚举**
   - 固定 `JuvenileLeaves = 16..20`。
   - 每个情景运行一套连续参数 IES。
   - 比较联合 RMSE, 选择最优整数值。

## 最小验证标准

第一版实现不要求一次跑大规模同化, 但至少应满足:

1. IES 更新公式有单元测试。
2. 参数越界半程回拉有单元测试。
3. `.var/.soi` 参数写入有单元测试。
4. `g01/G03` 输出读取有单元测试。
5. 使用 2-3 个 ensemble 成员能完成一次 forecast。
6. 使用合成观测能完成 1 次 IES 更新。
7. 输出文件中能看到:

```text
statistics_da/Initial-Params.txt
statistics_da/Kalman_Update/Iter-1-Params.txt
results/rmse_summary.csv
```

## 推荐在新对话中给 Codex 的实现提示

可以在新对话中直接使用下面的任务描述:

```text
请根据 MAIZSIM_IES数据同化框架方案.md, 在 Use 分支的仓库根目录新建 DA_Framework 文件夹, 并在该文件夹下实现 MAIZSIM/2DSOIL 的 IES 数据同化框架第一版。

要求:
1. 不直接拷贝 DA-AquaCrop 代码, 只参照其 PythonKalman 分支的架构。
2. 所有新增框架代码、配置模板、测试和运行说明都放在 DA_Framework/ 下。
3. 第一版只更新连续参数 n, thetaS, LM_min, Rmax_LTAR, StayGreen。
4. JuvenileLeaves 只做外层枚举设计, 不进入连续 IES 更新。
5. 不新增依赖, 使用当前 pixi.toml 中已有 numpy, pandas, pyemu 等依赖。
6. 对 MAIZSIM/2DSOIL 耦合过程、参数生效位置或输出字段含义有任何不确定时, 先读根目录下 Crop source/ 和 Soil Source/ 源码。
7. 修改后运行最小相关测试。
```

## 风险和注意事项

- IES 假定参数更新近似连续, 因此整数参数不应直接进入更新。
- LAI 与土壤含水量的观测误差尺度不同, 必须通过观测标准差归一化影响。
- 土壤含水量观测是层平均还是点位值必须明确, 否则输出映射会引入结构误差。
- `thetaS` 写入时必须同步更新相关饱和含水量字段, 不能只改单列。
- 每个 ensemble 成员必须使用独立目录, 避免输出文件相互覆盖。
- 前向模型失败时必须保留 `stdout/stderr` 或日志路径, 否则后续无法定位数值崩溃原因。
- 对二维作物模型耦合过程有任何不确定时, 首先阅读根目录下 `Crop source/` 和 `Soil Source/` 源码, 再决定参数写入、观测映射或状态变量定义。
