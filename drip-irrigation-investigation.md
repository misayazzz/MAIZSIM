# MAIZSIM滴灌湿润体实现调查与验证记录

记录日期：2026-05-26

## 结论

如果目标只是让滴灌水进入MAIZSIM，并在季节尺度检查水量、根区水分和作物响应，现有工程主线仍可作为可运行基线。

如果目标是精细模拟滴灌湿润体形态，尤其要和HYDRUS二维`theta(x,z,t)`图对比，当前实现不够，必须继续改。原因不是绘图不够细，也不是`.drp`滴灌量单位错误，而是当前`DripSpreadMode=2`没有真正复现HYDRUS SurfaceDrip的供水受限主动集算法。

当前能确认的事实：

- 已有同网格、同土壤参数、同初始压力头、同`2 L/h`持续`2 h`事件的HYDRUS Drip1/Drip2二维对照链路。
- 图像已经标出滴头位置、地表源区和湿润锋，目标3验收脚本已经检查二维IoU、湿润宽深、储水残差、峰值位置、体积加权`Delta theta`误差、G05闭合和PNG标注。
- 严格零蒸发基线下，`DripSpreadMode=2`当前为`13 pass / 11 fail`，未达到目标3。
- `wAppl=2239.65 cm/hour`不是单位错误。HYDRUS官方轴对称边界权重为`0.892996`，`2 L/h = 2000 cm3/h`，所以`wAppl = 2000 / 0.892996 = 2239.65`；Fortran内部再乘`Width`恢复为体积流量。
- Drip1的峰值位置旧报错为`17.575 cm`，是评价指标把HYDRUS平台峰值当成单点峰值造成的假失败。平台感知指标修正后，Drip1峰值距离为`0.0 cm`。

当前不能再写成：

- “Drip1/Drip2低`Ks`保护版都通过二维形态验收。”
- “Drip2目标3全项通过。”
- “45个工程回归算例全部通过严格精度验收。”
- “当前已经复现HYDRUS SurfaceDrip物理边界。”

## 当前保留的代码改动

本轮保留的是验证口径修正，不保留新的Fortran物理边界实验。

### 零VPD基线修正

文件：`DA_Framework/da_framework/hydrus_aligned_validation.py`

旧的`LOAM2D.wea`写`RH=98`，且MAIZSIM气象头文件启用了相对湿度读取时会把RH封顶到`0.98`。这会让“无滴灌baseline”仍有小的蒸发驱动，从而放大滴灌相对baseline的增湿量。

当前修正：

- `LOAM2D.wea`写`RH=100`。
- 新增`write_zero_weather_header_file()`，生成`WyeClimate.dat`并关闭`Rel_humid`标志，使常温无辐射条件下VPD真正为零。
- `prepare_hydrus_aligned_runs()`在baseline和drip目录都写入该头文件。

这会改变HYDRUS对照结果，因此旧的`tmp/codex_goal3_lowks_outputs_*`不能再作为最终证据，必须使用`tmp/codex_goal3_lowks_novpd_outputs_*`。

### 峰值平台指标修正

文件：`DA_Framework/da_framework/hydrus_2d_comparison.py`

旧指标取HYDRUS最大`Delta theta`的单个`idxmax`点，再与MAIZSIM最大点求距离。Drip1中HYDRUS表层最大值是平台，不是孤立点；MAIZSIM峰值落在这个平台上时，旧指标仍可能报出十几厘米偏差。

当前修正为：

- 找出HYDRUS和MAIZSIM各自最大值平台。
- 计算两个峰值平台之间的最近距离。
- 如果MAIZSIM峰值点落在HYDRUS峰值平台内，距离记为`0.0 cm`。

新增测试：`test_compare_theta_fields_uses_nearest_peak_plateau_distance`。

### `wAppl`口径注释

文件：`DA_Framework/da_framework/hydrus_aligned_validation.py`

新增注释说明`KAT=1`时`wAppl`是体积流量除以HYDRUS轴对称边界积分权重，Fortran再乘`Width`恢复原始滴头流量。这个值看起来很大，但G05闭合显示输入量约`3.18 mm`，与`4 L`事件量一致。

## 官方HYDRUS基准

两个官方工程均来自HYDRUS SurfaceDrip公开示例。

| 工程 | 土壤 | 几何 | 节点/单元 | 初始条件 | 滴灌事件 |
| --- | --- | --- | --- | --- | --- |
| `Drip1` | 壤土 | `KAT=1`轴对称 | `1532/2927` | `h=-100 cm` | `2 L/h`持续`2 h` |
| `Drip2` | 砂壤土 | `KAT=1`轴对称 | `1532/2927` | `h=-100 cm` | `2 L/h`持续`2 h` |

土壤参数：

| 工程 | `theta_r` | `theta_s` | `alpha` (`cm^-1`) | `n` | `Ks` (`cm/h`) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `0.078` | `0.430` | `0.036` | `1.56` | `1.04000` |
| `Drip2` | `0.065` | `0.410` | `0.075` | `1.89` | `4.42083` |

HYDRUS在`Delta theta >= 0.005`下的2 h湿润体指标：

| 工程 | 湿润宽度 | 湿润深度 | 储水增量 |
| --- | ---: | ---: | ---: |
| `Drip1` | `28.055 cm` | `18.476 cm` | `3.983 L` |
| `Drip2` | `21.904 cm` | `23.026 cm` | `3.997 L` |

说明：这里的“宽度”是`KAT=1`径向`x`跨度，不是左右对称直径。

## 严格零VPD二维对照结果

验证命令：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_aligned_validation `
  --project-file tmp\codex_hydrus_official\drip\Drip1.h3d3 `
  --workspace tmp\codex_goal3_lowks_novpd_runs_Drip1 `
  --output-dir tmp\codex_goal3_lowks_novpd_outputs_Drip1 `
  --prefix Drip1LowKsNoVPD `
  --drip-spread-mode 2 `
  --timeout-seconds 300

pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_aligned_validation `
  --project-file tmp\codex_hydrus_official\drip\Drip2.h3d3 `
  --workspace tmp\codex_goal3_lowks_novpd_runs_Drip2 `
  --output-dir tmp\codex_goal3_lowks_novpd_outputs_Drip2 `
  --prefix Drip2LowKsNoVPD `
  --drip-spread-mode 2 `
  --timeout-seconds 300
```

目标3验收命令：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_goal3_acceptance `
  --summary tmp\codex_goal3_lowks_novpd_outputs_Drip1\Drip1LowKsNoVPD_aligned_validation_summary.csv `
  --summary tmp\codex_goal3_lowks_novpd_outputs_Drip2\Drip2LowKsNoVPD_aligned_validation_summary.csv `
  --output-csv tmp\codex_goal3_lowks_novpd_acceptance\goal3_acceptance.csv
```

结果：`13 pass / 11 fail`。

| 工程 | HYDRUS储水 | MAIZSIM储水 | 储水残差 | 全局IoU | HYDRUS宽度 | MAIZSIM宽度 | HYDRUS深度 | MAIZSIM深度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1LowKsNoVPD` | `3.983 L` | `4.922 L` | `+0.939 L` | `0.853` | `28.055 cm` | `29.758 cm` | `18.476 cm` | `20.053 cm` |
| `Drip2LowKsNoVPD` | `3.997 L` | `89.280 L` | `+85.283 L` | `0.201` | `21.904 cm` | `50.000 cm` | `23.026 cm` | `43.101 cm` |

G05诊断：

| 工程 | `DripInput` | `DripActualInfil` | `DripHydraulicExcess` | G05闭合 |
| --- | ---: | ---: | ---: | --- |
| `Drip1LowKsNoVPD` | `3.184 mm` | `2.932 mm` | `0.253 mm` | 通过 |
| `Drip2LowKsNoVPD` | `3.192 mm` | `3.179 mm` | `0.013 mm` | 通过 |

解释：

- G05闭合通过，说明`.drp`体积输入没有爆炸。
- Drip2的`G03`二维土壤水分场爆炸到`89.280 L`，说明问题发生在地表压力/径流/入渗路径进入水分场后，而不是滴灌输入文件。
- Drip1主体轮廓接近，但储水偏高`0.939 L`，仍超过目标3阈值`0.4 L`。
- 严格零VPD基线下，旧文档中“Drip2全项通过”的说法失效。

输出图：

- `tmp/codex_goal3_lowks_novpd_outputs_Drip1/Drip1LowKsNoVPD_aligned_fields.png`
- `tmp/codex_goal3_lowks_novpd_outputs_Drip2/Drip2LowKsNoVPD_aligned_fields.png`

## 已否定的实现尝试

这些尝试都已撤回，不能作为最终方案。

| 尝试 | 结果 | 判断 |
| --- | --- | --- |
| 直接在`WaterMover()`中把滴灌节点切为`CodeW=4,h=0` | Drip1和Drip2在滴灌开始附近超时 | 当前求解器中`h=0`不是供水受限边界，会破坏收敛 |
| 用`DripLimitedPondingScale=0.01`缩小ponding影响 | Drip1和Drip2均超时 | 经验缩放不是稳定物理修正 |
| 把滴灌通量改为普通`CodeW=0` flux | 可运行，但Drip1欠湿、Drip2几乎不湿润 | 普通通量路径不能表达HYDRUS SurfaceDrip动态湿润区 |
| 对所有`DripSpreadMode=2`旁路地表径流 | Drip2仍爆炸到`68.882 L`，IoU仅`0.208` | 简单旁路不是根因修复 |
| 强制`DripMode=3`近地表直接源项对照 | Drip1可运行但不达标，Drip2超时 | 直接源项不能替代目标3物理边界 |

关键诊断：

- HYDRUS SurfaceDrip不是简单横向扩展半径。
- 它需要“先按Neumann通量施加；若所需压力头大于零，则该节点切为`h=0`Dirichlet；实际可入渗通量`Qa`进入土体；超额`Q-Qa`继续给邻近节点；重复直到总滴灌通量被处理完”的主动集过程。
- 当前MAIZSIM直接切`h=0`时没有供水上限，后处理再把`QAct`裁剪到需求量只能修正诊断，不能修正已经进入土体的水分场。
- 因此若目标是和HYDRUS二维图对比，必须在求解器层面实现供水受限主动集，而不是调`DripWetWidthMax`或画图阈值。

## 代码层面应如何继续改

目标3下，建议新增一个独立于通用地表径流的`DripSpreadMode=3`或重构`DripSpreadMode=2`，核心要求如下：

1. 以HYDRUS地表边界段为活动集，初始只激活滴头节点或滴头边界段。
2. 在一个时间步内按供水受限通量求解Richards方程。
3. 对每个活动边界段检查`h`和实际`QAct`：
   - 若通量边界导致`h > 0`，把该段切为`h=0`压力边界。
   - 记录该段实际可接纳通量`Qa`。
   - 只允许`Qa`进入水分方程。
4. 将超额`Q-Qa`按HYDRUS方向规则分配到相邻地表段。
5. 活动集变化后重解，直到总滴灌通量被接纳、转为未入渗水，或达到稳定停止条件。
6. 把剩余未接纳水写入`DripHydraulicExcess`或独立的滴灌未入渗输出，而不是让通用`surfaceWaterBalanceAdjustment.for`把它反复横向再分配。
7. 给主动集外循环加最大迭代次数、最小时间步、质量闭合断言和失败诊断。

验收必须同时满足：

- Drip1和Drip2均通过目标3接受门，而不是只通过一个土壤。
- `G03`二维`Delta theta`图和HYDRUS图肉眼一致。
- 储水残差小于`0.4 L`。
- 湿润宽度误差小于`1 cm`，深度误差小于`3 cm`。
- G05输入、实际入渗、压力损失和未入渗水量闭合。
- 根系场景中额外输出`Delta theta + root density`叠加图，说明湿润体是否进入根区。

## 根系二维图

官方HYDRUS Drip1/Drip2是无作物短时算例，不能直接验证根系吸水。作物场景必须另外输出根系分布图。

当前已有图：

- `tmp/codex_precision_drip_validation/precision_delta_theta_root_overlay_0601.png`
- `tmp/codex_precision_drip_validation/precision_root_density_0601.png`

这些图只回答“MAIZSIM作物算例中滴灌增湿区是否覆盖根区”，不能替代HYDRUS官方Drip1/Drip2湿润体物理验证。

## 45例工程回归矩阵

`drip_precision_validation.py`仍会跑3种土壤、3种网格、5类场景，共45个工程回归记录。

正确表述是：

- 45个记录可以生成。
- 水量闭合、湿润宽度上限和根区响应等工程检查可作为回归保护。
- 这些记录不是HYDRUS二维湿润体精细物理验收。
- 不能再写“45个算例全部通过严格目标3验收”。

## 验证命令

构建：

```powershell
msbuild maizsim07.sln /p:Configuration=Release /p:Platform=x64
```

相关单元测试：

```powershell
pixi run --manifest-path pixi.toml python -m unittest DA_Framework.tests.test_hydrus_aligned_validation DA_Framework.tests.test_hydrus_2d_comparison DA_Framework.tests.test_hydrus_goal3_acceptance
```

本轮已完成：

- `msbuild`成功，0个错误，73个既有警告。
- 相关Python单元测试`26 tests`通过。
- 严格零VPD Drip1/Drip2二维验证已运行。
- 目标3接受门已运行，当前`13 pass / 11 fail`。
- bypass-all和直接源项等实验性Fortran改动已撤回。

## 文献判断

HYDRUS官方说明把SurfaceDrip列为特殊边界条件，并明确其动态湿润面积算法：先在滴头节点施加Neumann通量；若容纳该通量所需压力头大于零，就把该节点切为零压力Dirichlet边界，计算实际入渗`Qa`；超额`Q-Qa`继续施加到邻近节点，迭代直到整个灌水通量被处理完。这个描述与当前MAIZSIM缺失的机制完全对应。

Kandelous和Simunek的HYDRUS-2D滴灌研究也说明，评价滴灌模型不能只看总水量，需要看水分在滴头周围的精确分布和湿润尺寸。该研究用实验水分分布和湿润尺寸评价HYDRUS-2D，报告体积含水量RMSE和湿润尺寸RMSE。Kandelous和Simunek后续比较数值、解析和经验模型时，也把湿润区尺寸误差作为核心指标。

因此，从文献和HYDRUS算法定义看，目标3的合理实现不是经验横向铺开，也不是事后裁剪`QAct`诊断值，而是供水受限、质量闭合、可重解的动态活动边界。

参考资料：

- HYDRUS Special Boundary Conditions, Surface Drip Irrigation：<https://www.pc-progress.com/en/OnlineHelp/HYDRUS3/SpecialBoundaryConditions1.html>
- Kandelous, M. M. and Simunek, J. 2010. Numerical simulations of water movement in a subsurface drip irrigation system under field and laboratory conditions using HYDRUS-2D：<https://www.pc-progress.com/Documents/Jirka/Kandelous_Simunek_AWM_2010.pdf>
- Kandelous, M. M. and Simunek, J. 2010. Comparison of numerical, analytical, and empirical models to estimate wetting patterns for surface and subsurface drip irrigation：<https://link.springer.com/article/10.1007/s00271-009-0205-9>
