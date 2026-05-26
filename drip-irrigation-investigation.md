# MAIZSIM滴灌湿润体实现调查与验证记录

记录日期：2026-05-24

最新更新：2026-05-26

## 当前结论

如果目标只是让滴灌水进入MAIZSIM，并检查季节尺度水量、根区水分和作物响应，现有滴灌源项已经可以工作。

如果目标是精细模拟滴灌湿润体形态，尤其要和HYDRUS二维`theta(x,z,t)`图对比，旧实现不够，必须用二维场、湿润锋轮廓、储水量和根区叠加图共同验收。当前代码已经补齐了这套验证链路，但物理边界模型仍应分成两条线看：

- 稳定工程主线：`DripSpreadMode=1`，对低`Ks`壤土自动使用`DripMode=3`近地表直接源项；这是当前最稳定的HYDRUS二维形态对照基线。
- 实验压力边界线：`DripSpreadMode=2`，不再使用HYDRUS最终湿润宽度作为输入，而是按当前土壤导水能力估算活动地表宽度，并通过`WaterMover`地表通量路径进入水分方程。该线在砂壤土Drip2结果较好，但在壤土Drip1严重失真，不能声称已经复现HYDRUS SurfaceDrip主动集算法。

因此当前可以说：

- 已具备和官方HYDRUS Drip1/Drip2做同网格、同土壤参数、同初始压力头、同滴灌事件的二维图像对照工具链。
- 二维图已经标出滴头位置和地表源区，points CSV已经输出湿润体布尔掩膜，便于复核湿润体面积、宽度、深度和连通范围。
- 作物算例已经额外输出二维根系密度图和`Delta theta`+根系等值线叠加图，用来判断滴灌增湿区是否进入根区。

当前不能说：

- 已完整复现HYDRUS有限元SurfaceDrip压力头受限边界。
- 壤土和砂壤土都已在`DripSpreadMode=2`压力边界线下通过。
- 45个工程回归算例全部通过严格精度验收；最新检查中`case_count=45`通过，但HYDRUS曲线宽度误差最大`1.47 cm`，该项仍为`fail`，主要出现在壤土早期宽度受网格/边界段表达能力限制的算例。

## 代码层面的最新实现

### Fortran核心

相关文件：

- `Soil Source/Drip.FOR`
- `Soil Source/Watmov.for`
- `Soil Source/PuSurface.ins`
- `Soil Source/OUTPUT.FOR`

`.drp`事件行仍兼容6、11、12和13字段：

```text
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax DripSpreadMode
```

关键字段：

- `wAppl`：输入单位为`cm/h`，Fortran内部换算为`cm/day`。
- `DripSpreadMode=0`：旧的入渗受限触发扩展模式。
- `DripSpreadMode=1`：稳定工程主线。按目标湿润宽度激活地表范围；对低`Ks`HYDRUS对齐算例，Python工具会使用`DripMode=3`近地表直接源项。
- `DripSpreadMode=2`：实验压力边界线。当前不是完整HYDRUS主动集，而是按局部导水能力估算活动宽度，再通过`WaterMover`地表通量路径求解。
- `DripWetWidthMax`：地表最大湿润宽度或半径口径。`KAT=1`且滴头在轴线时按径向区间`[0,R]`解释。
- `DripMode=1/2`：压力补偿模式，要求`DripHIn>0`。
- `DripMode=3`：近地表直接源项模式，不走压力补偿公式，`DripPcMax`表示直接源项深度。

本轮核心修正：

- `KAT=1`轴对称下，不再简单把`Width(k)`当横向长度；地表活动范围按边界段几何区间求交，再用环带面积比例计算边界积分权重。
- `DripSpreadMode=2`默认不再从HYDRUS最终湿润宽度反填`DripWetWidthMax`，避免把验证目标当作模型输入。
- `DripSpreadMode=2`活动宽度改为由局部容量估算决定：从滴头中心向相邻地表节点扩展，直到`ConSat * 局部压力修正因子 * 边界宽度`的合计容量能覆盖滴灌通量，或达到默认最大宽度。
- `DripSpreadMode=2`不再强制18秒小步长；之前该尝试会导致官方算例明显超时。
- `DripSpreadMode=2`不再绕过普通地表处理；它仍通过`WaterMover`求解，不直接改`ThNew/hNew`。
- G05新增`DripActualInfil`，并区分`DripInput`、`DripActualInfil`和`DripHydraulicExcess`，用于检查边界输入、实际接纳入渗和未接纳水量的闭合。
- G05输出格式已同步扩展，避免新增字段后数据行换行导致`Date`解析错误。

当前`DripSpreadMode=2`仍缺少的HYDRUS机制：

- 没有严格的`h=0`压力头主动集重解。
- 没有在同一步内把不能接纳的超额通量逐节点重新分配并反复求解。
- 对低渗透性壤土仍会产生严重不合理储水放大。

### Python验证工具链

相关文件：

- `DA_Framework/da_framework/hydrus_official_export.py`
- `DA_Framework/da_framework/hydrus_2d_comparison.py`
- `DA_Framework/da_framework/hydrus_aligned_validation.py`
- `DA_Framework/da_framework/drip_precision_validation.py`

当前能力：

- 读取官方HYDRUS工程，导出`theta`二维场、网格、土壤参数、轴对称体积权重和HYDRUS自身湿润体指标。
- 自动生成Drip1-like/Drip2-like MAIZSIM短时算例：同网格、同`KAT=1`轴对称几何、同土壤参数、同初始压力头`h=-100 cm`、同`2 L/h`持续`2 h`。
- 输出HYDRUS、MAIZSIM和`MAIZSIM-HYDRUS`三联图。
- 图中红色倒三角和虚线表示滴头中心，红色地表线段表示本次施加的地表源区。
- 图中黑色等值线表示当前`Delta theta`阈值下的湿润锋。
- points CSV新增`hydrus_wet`、`maizsim_wet`、`hydrus_source_wet`和`maizsim_source_wet`布尔列。
- 自动输出阈值敏感性CSV和PNG，检查宽度、深度、IoU和储水比例是否依赖单一阈值。
- 作物精度验证新增`precision_root_density_0601.png`，与既有`precision_delta_theta_root_overlay_0601.png`配套。

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

用`Delta theta >= 0.005`计算的HYDRUS 2 h湿润体指标：

| 工程 | HYDRUS湿润宽度 | HYDRUS湿润深度 | HYDRUS储水增量 |
| --- | ---: | ---: | ---: |
| `Drip1` | `28.055 cm` | `18.476 cm` | `3.983 L` |
| `Drip2` | `21.904 cm` | `23.026 cm` | `3.997 L` |

说明：这里的“宽度”是`KAT=1`径向`x`跨度，不是左右对称直径。

## 最新二维对照结果

### 稳定主线：`DripSpreadMode=1`

验证命令示例：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_aligned_validation `
  --project-file tmp\codex_hydrus_official\drip\Drip1.h3d3 `
  --workspace tmp\codex_goal3_main_runs_Drip1 `
  --output-dir tmp\codex_goal3_main_outputs_Drip1 `
  --prefix Drip1Goal3Main `
  --drip-spread-mode 1 `
  --timeout-seconds 300
```

输出图：

- `tmp/codex_goal3_main_outputs_Drip1/Drip1Goal3Main_aligned_fields.png`
- `tmp/codex_goal3_main_outputs_Drip2/Drip2Goal3Main_aligned_fields.png`

结果：

| 工程 | MAIZSIM模式 | HYDRUS储水 | MAIZSIM储水 | 储水残差 | 全局IoU | 连通IoU |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `DripSpreadMode=1, DripMode=3` | `3.983 L` | `3.278 L` | `-0.705 L` | `0.877` | `0.880` |
| `Drip2` | `DripSpreadMode=1, DripMode=0` | `3.997 L` | `3.865 L` | `-0.132 L` | `0.863` | `0.863` |

湿润体尺寸：

| 工程 | HYDRUS全局宽度 | MAIZSIM全局宽度 | HYDRUS连通宽度 | MAIZSIM连通宽度 | HYDRUS深度 | MAIZSIM深度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `28.055 cm` | `50.000 cm` | `28.055 cm` | `33.243 cm` | `18.476 cm` | `19.253 cm` |
| `Drip2` | `21.904 cm` | `23.345 cm` | `21.904 cm` | `23.345 cm` | `23.026 cm` | `18.979 cm` |

解释：

- Drip1的全局宽度`50 cm`来自阈值下远端浅层临界点，连通湿润体宽度`33.243 cm`更能代表滴头主体湿润体。
- Drip1主体形态较接近HYDRUS，但储水少约`0.705 L`，因此不能只凭IoU判断通过。
- Drip2储水误差较小，但垂向推进偏浅约`4.05 cm`。
- 两个主线图的PNG基础QA均通过：图像非空、非纯色，并检测到红色滴头/源区标注。

### 实验压力边界线：`DripSpreadMode=2`

验证命令示例：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_aligned_validation `
  --project-file tmp\codex_hydrus_official\drip\Drip2.h3d3 `
  --workspace tmp\codex_goal3_mode2_runs_Drip2_v9 `
  --output-dir tmp\codex_goal3_mode2_outputs_v9 `
  --prefix Drip2Mode2 `
  --drip-spread-mode 2 `
  --timeout-seconds 240
```

结果：

| 工程 | HYDRUS储水 | MAIZSIM储水 | 储水残差 | 全局IoU | HYDRUS宽度 | MAIZSIM宽度 | HYDRUS深度 | MAIZSIM深度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `3.983 L` | `23.259 L` | `+19.276 L` | `0.437` | `28.055 cm` | `50.000 cm` | `18.476 cm` | `20.763 cm` |
| `Drip2` | `3.997 L` | `3.856 L` | `-0.141 L` | `0.925` | `21.904 cm` | `21.904 cm` | `23.026 cm` | `21.122 cm` |

G05边界诊断：

| 工程 | `DripInput` | `DripActualInfil` | `DripHydraulicExcess` | 接纳闭合残差 |
| --- | ---: | ---: | ---: | ---: |
| `Drip1` | `3.159 mm` | `2.397 mm` | `0.761 mm` | `0.001 mm` |
| `Drip2` | `3.168 mm` | `3.162 mm` | `0.006 mm` | `~0 mm` |

解释：

- `mode2`在砂壤土Drip2上已经比旧实现明显合理，宽度对齐、储水接近、IoU高。
- `mode2`在壤土Drip1上严重不合理，储水达到施水量的`5.81`倍，说明低`Ks`条件下仍缺真正的压力头主动集和超额通量重分配。
- 因此`mode2`只能作为实验路径保留，不能作为当前目标3的完整完成依据。

## 根系二维图

官方HYDRUS Drip1/Drip2是无作物短时算例，不能直接验证根系吸水。为回答“滴灌湿润体是否覆盖作物根区”，当前使用MAIZSIM作物算例输出两类二维图：

- `tmp/codex_precision_drip_validation/precision_delta_theta_root_overlay_0601.png`
- `tmp/codex_precision_drip_validation/precision_root_density_0601.png`

基础QA：

| 图 | PNG尺寸 | 说明 |
| --- | --- | --- |
| `precision_delta_theta_root_overlay_0601.png` | `1685 x 4100` | `Delta theta`底图叠加根系等值线和滴头/源区标注 |
| `precision_root_density_0601.png` | `1685 x 4067` | 根系密度二维图，标出滴头和地表源区 |

根区指标：

| 土壤 | `delta_theta_max` | 正增湿面积 | 正增湿根区面积比例 | 根系加权`Delta theta` |
| --- | ---: | ---: | ---: | ---: |
| `clay_loam` | `0.1910` | `935.529 cm2` | `1.000` | `0.01381` |
| `loam` | `0.1428` | `2182.739 cm2` | `1.000` | `0.01857` |
| `sandy_loam` | `0.1339` | `1492.625 cm2` | `1.000` | `0.00973` |

这里的根系图只说明MAIZSIM作物算例中滴灌增湿体与根系分布的空间关系；它不是HYDRUS官方Drip1/Drip2验证图。

## 45例工程回归矩阵

`drip_precision_validation.py`仍会跑3种土壤、3种网格、5类场景，共45个工程回归记录。

最新检查摘要：

| 检查项 | 最新值 | 状态 |
| --- | ---: | --- |
| `case_count` | `45` | `pass` |
| `water_balance_residual_abs_max_mm` | `1.24e-14` | `pass` |
| `wet_width_limit_violations` | `0` | `pass` |
| `short_width_error_abs_max_cm` | `0.085` | `pass` |
| `hydrus_curve_width_error_abs_max_cm` | `1.47` | `fail` |
| `fortran_target_unexpressed_abs_max_cm` | `11.129` | `review` |
| `spatial_root_weighted_delta_records` | `3` | `pass` |

这个结果的正确表述是：45个回归记录已生成并通过水量闭合、湿润宽度上限和作物根区响应等检查，但HYDRUS曲线宽度精度仍有未通过项。不能再写成“45个算例全部通过”。

## 验证命令

构建：

```powershell
& 'F:\Program Files\Microsoft Visual Studio\18\Community\MSBuild\Current\Bin\amd64\MSBuild.exe' maizsim07.sln /t:2dmaizsim /p:Configuration=Release /p:Platform=x64 /m
```

Python单元测试：

```powershell
pixi run --manifest-path pixi.toml python -m unittest DA_Framework.tests.test_hydrus_2d_comparison DA_Framework.tests.test_hydrus_aligned_validation DA_Framework.tests.test_drip_validation
```

精度和根系图验证：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.drip_precision_validation
```

已完成结果：

- Fortran/C++构建成功，0个错误，73个既有警告。
- 相关Python单元测试29个通过。
- Drip1/Drip2主线二维对照已完成。
- Drip1/Drip2的`mode2`实验对照已完成。
- 根系叠加图和根系密度二维图已生成。

## 仍需后续处理

若目标保持为“精细模拟滴灌湿润体形态并与HYDRUS二维图对比”，下一步重点是：

- 为`DripSpreadMode=2`实现真正的压力头受限主动集：节点达到`h=0`后切换为压力边界，计算实际入渗，并把超额水在同一步内重分配到相邻地表节点后重解。
- 增加稳定的自适应子步长，尤其针对低`Ks`壤土，避免储水放大或时间步崩溃。
- 继续用Drip1和Drip2分别约束低`Ks`壤土和高`Ks`砂壤土，不能只用砂壤土Drip2证明压力边界正确。
- 将`DripMode=3`保持为稳定工程回归基线，但不要把它描述为HYDRUS物理边界复现。
- 对更多土壤质地按`theta_r`、`theta_s`、`alpha`、`n`、`Ks`和初始含水状态分组验证，而不是只按“壤土/砂壤土”等定性名称判断。
- 若转向地下滴灌，需要新增内部源项或内部边界，不能复用当前地表`DripSpreadMode`。

## 参考资料

- HYDRUS特殊边界条件说明：<https://www.pc-progress.com/en/OnlineHelp/HYDRUS3/SpecialBoundaryConditions1.html>
- HYDRUS 2D/3D Technical Manual, Surface Drip Irrigation with Dynamic Evaluation of the Wetted Area：<https://www2.pc-progress.com/downloads/Pgm_Hydrus3D5/HYDRUS_Technical_Manual_2D3D_V5.pdf>
- Lazarovitch, N.等. 2023. Modeling of irrigation and related processes with HYDRUS：<https://www.pc-progress.com/Documents/Jirka/Lazarovitch_et_al_2023.pdf>
- Kandelous, M. M.等. 2011. Comparison of numerical, analytical, and empirical models to estimate wetting patterns for surface and subsurface drip irrigation：<https://link.springer.com/article/10.1007/s00271-009-0205-9>
- Kandelous, M. M.和Simunek, J. 2010. Numerical simulations of water movement in a subsurface drip irrigation system under field and laboratory conditions using HYDRUS-2D：<https://www.pc-progress.com/Documents/Jirka/Kandelous_Simunek_AWM_2010.pdf>
