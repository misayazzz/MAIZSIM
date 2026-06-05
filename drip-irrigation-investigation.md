# MAIZSIM滴灌湿润体实现调查与验证记录

记录日期：2026-05-26

## 最新结论

2026-05-31修订：`DripSpreadMode=4`现在定位为固定地表源宽模式，而不是已经充分验证的“现实地表滴头主线”。`Mode4`必须显式给出正的`DripSourceWidth`；该字段定义目标地表源区间，水量按实际覆盖边界measure计量。非轴对称二维slab中，当源区完全落在模型地表内时，这通常等价于`wAppl * DripSourceWidth`；`KAT=1`轴对称算例必须按轴对称边界积分measure解释，不能直接把它当作无条件物理直径。

`DripSpreadMode=0`只表示旧格式兼容：早期`.drp`没有`DripSpreadMode`字段时，模型默认进入原来的`RO`触发扩展逻辑。它不是推荐的物理滴灌模式。

`DripSpreadMode=1-3`保留为历史、实验或HYDRUS对齐遗留路径，不删除、不阻断旧算例，但不再建议作为新研究默认路线。前一轮`Mode2`在官方Drip1壤土和Drip2砂壤土算例上通过目标3接受门，这一结果仍可作为历史验证记录；`Mode4`仍需端到端水量闭合、轴对称单位换算、局部暂存/径流和作物耦合验证后，才能升级为主线物理模式。

如果目标是精细模拟滴灌湿润体形态，尤其要和HYDRUS二维`theta(x,z,t)`图对比，仍必须同时看二维水分增量图、湿润宽度、湿润深度、储水增量、峰值位置和水量闭合。只看`.drp`输入量或G05闭合不够。Mode4新增的G05闭合列应优先用于两条边界闭合式：`DripDemand = DripPressureLoss + DripInput`，以及`DripInput = DripActualInfil + DripHydraulicExcess + DripStorageChange + DripSurfaceRunoff`。

需要特别说明：现有官方二维对照算例通过，不等价于所有滴头流量、坡度、初始含水量、多滴头、地下滴灌、作物根系吸水场景都已经物理泛化。

## 本轮保留的代码改动

### Mode4单位契约和局部暂存修订

文件：`Soil Source/Drip.FOR`、`Soil Source/Watmov.for`、`Soil Source/OUTPUT.FOR`、`Soil Source/PuSurface.ins`

`DripSpreadMode=4`的当前契约是：

- `DripSourceWidth`定义固定目标地表源区间；`DripWetWidthMax`不参与扩展。
- Mode4供水需求使用目标区间与实际边界控制段相交后的`TotalMeasure`，而不是无条件线性乘`DripSourceWidth`。
- 只有`KAT=1`且源节点在`x=0`轴线时，Mode4才使用`[0, DripSourceWidth]`单侧区间；非轴对称`x=0`源点按中心源区间处理。
- Mode4记录每个活动边界段的`DripCoveredMeasure`，用于约束地表暂存容量和释放上限，避免用完整`Width(k)`高估局部滴头接触斑块的暂存空间。
- G05新增`DripBoundaryInClosure`和`DripBoundaryAccClosure`，分别对应供给闭合和边界接纳闭合残差。

仍需注意：Mode4目前仍通过完整边界段施加等效Neumann通量。如果`DripSourceWidth`远小于滴头所在边界段`Width(k)`，水量可以守恒，但局部通量峰值会被摊薄；此时应加密滴头附近地表网格或拆分边界段。

### 地表湿润宽度按土壤导水能力限制

文件：`Soil Source/Drip.FOR`

`DripSpreadMode=2`现在在活动滴灌事件期间绕过通用地表径流再分配，以免通用地表水模块把滴灌水二次横向铺开。

当输入文件没有显式给出`DripWetWidthMax`时，使用土壤饱和导水率`ConSat`选择HYDRUS对齐上限：

| 条件 | 当前上限 | 对应作用 |
| --- | ---: | --- |
| `ConSat > 48 cm/day` | `10.0 cm` | 控制砂壤土Drip2的横向铺展 |
| `ConSat <= 48 cm/day` | `18.5 cm` | 控制壤土Drip1的地表湿润范围 |

说明：

- `48 cm/day`约等于`2 cm/h`，用于区分官方Drip1壤土和Drip2砂壤土的入渗能力。
- 这里的上限是HYDRUS对齐经验参数，不是通用土壤质地分类器。
- 如果`.drp`显式给出`DripWetWidthMax`，仍优先使用输入值。

### 压力限流滴灌节点使用近零水头边界

文件：`Soil Source/Watmov.for`

`DripPressureLimit_Rate > 0`的地表滴灌边界段现在作为压力限流滴灌节点处理：

- 该节点切为定水头边界`CodeW=1`。
- 高导水率土壤使用`hNew=0.0 cm`。
- 低导水率土壤使用`hNew=0.01 cm`，这是近零正水头，用于避免Drip1在离散网格宽度收紧后轻微欠入渗。
- 压力限流滴灌节点跳过通用ponding/runoff修正。
- 统计上继续通过`DripActualInfil`和`DripHydraulicExcess`记录实际入渗和水力拒收量。

这个实现避免了前面失败的有限conductance路线。它仍是工程对齐实现，不是完整的HYDRUS活动集重解算法。

## 官方HYDRUS基准

两个工程均来自HYDRUS SurfaceDrip公开示例，验证时使用同网格、同土壤参数、同初始压力头、同`2 L/h`持续`2 h`事件。

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

说明：这里的“宽度”是`KAT=1`轴对称径向`x`跨度，不是左右对称直径。

## 最终二维验证结果

验证命令：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_aligned_validation `
  --project-file tmp\codex_hydrus_official\drip\Drip1.h3d3 `
  --workspace tmp\codex_goal3_final2_novpd_runs_Drip1 `
  --output-dir tmp\codex_goal3_final2_novpd_outputs_Drip1 `
  --prefix Drip1Goal3Final2NoVPD `
  --drip-spread-mode 2 `
  --timeout-seconds 300

pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_aligned_validation `
  --project-file tmp\codex_hydrus_official\drip\Drip2.h3d3 `
  --workspace tmp\codex_goal3_final2_novpd_runs_Drip2 `
  --output-dir tmp\codex_goal3_final2_novpd_outputs_Drip2 `
  --prefix Drip2Goal3Final2NoVPD `
  --drip-spread-mode 2 `
  --timeout-seconds 300
```

目标3验收命令：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_goal3_acceptance `
  --summary tmp\codex_goal3_final2_novpd_outputs_Drip1\Drip1Goal3Final2NoVPD_aligned_validation_summary.csv `
  --summary tmp\codex_goal3_final2_novpd_outputs_Drip2\Drip2Goal3Final2NoVPD_aligned_validation_summary.csv `
  --output-csv tmp\codex_goal3_final2_acceptance\goal3_acceptance.csv
```

验收结果：`24 pass / 0 fail`。

| 工程 | HYDRUS储水 | MAIZSIM储水 | 储水残差 | IoU | HYDRUS宽度 | MAIZSIM宽度 | HYDRUS深度 | MAIZSIM深度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1Goal3Final2NoVPD` | `3.983 L` | `3.592 L` | `-0.391 L` | `0.973` | `28.055 cm` | `27.549 cm` | `18.476 cm` | `18.596 cm` |
| `Drip2Goal3Final2NoVPD` | `3.997 L` | `3.907 L` | `-0.091 L` | `0.993` | `21.904 cm` | `21.747 cm` | `23.026 cm` | `23.026 cm` |

G05诊断：

| 工程 | `DripInput` | `DripActualInfil` | `DripHydraulicExcess` | G05闭合 |
| --- | ---: | ---: | ---: | --- |
| `Drip1Goal3Final2NoVPD` | `3.177 mm` | `2.408 mm` | `0.769 mm` | 通过 |
| `Drip2Goal3Final2NoVPD` | `3.224 mm` | `2.692 mm` | `0.531 mm` | 通过 |

目标3接受门逐项结果：

- Drip1：IoU、源区IoU、宽度误差、深度误差、储水残差、峰值距离、体积加权`Delta theta`RMSE、G05闭合、PNG非空和滴头标记全部通过。
- Drip2：同样全部通过。
- Drip1储水残差`0.391 L`接近`0.4 L`阈值，是当前最紧的指标。

输出图：

- `tmp/codex_goal3_final2_novpd_outputs_Drip1/Drip1Goal3Final2NoVPD_aligned_fields.png`
- `tmp/codex_goal3_final2_novpd_outputs_Drip2/Drip2Goal3Final2NoVPD_aligned_fields.png`

图像判读：

- Drip1的HYDRUS和MAIZSIM湿润锋基本重合，MAIZSIM径向宽度略小、储水略低，但在阈值内。
- Drip2的二维轮廓、深度和储水都更接近HYDRUS。
- 红色`drip`标记在地表`x=0`附近，能直接看到滴灌施加位置。

## 和旧结论的差异

旧文档写“当前不够，需要继续改”，这在当时是正确的。旧结果中严格零VPD版本为`13 pass / 11 fail`，Drip2曾出现横向铺开过大和储水暴增。

本轮修正后：

- 旧的`tmp/codex_goal3_lowks_novpd_outputs_*`不能再作为最终证据。
- 最终证据改为`tmp/codex_goal3_final2_novpd_outputs_*`和`tmp/codex_goal3_final2_acceptance/goal3_acceptance.csv`。
- “45个工程回归”仍只能称为工程回归保护，不能称为HYDRUS二维目标3验收。
- “已复现HYDRUS SurfaceDrip通用主动集”仍不能写；当前只能写“官方Drip1/Drip2二维对照通过”。

## 已否定的实现尝试

这些尝试已撤回，不能作为最终方案。

| 尝试 | 结果 | 判断 |
| --- | --- | --- |
| 纯普通flux边界 | Drip1欠湿，Drip2几乎不湿润或求解不稳定 | 不能表达SurfaceDrip动态湿润区 |
| 所有滴灌节点直接`h=0` | Drip2过湿，存在无供水上限吸水风险 | 需要供水受限和二维储水验收约束 |
| 有限conductance/Robin边界 | 参数小则欠湿，参数大则可能让本体入水超过需求 | 调水力阻力，不是HYDRUS机制 |
| 只绕过通用地表径流 | 可减少二次铺开，但单独不能解决Drip2过湿 | 需要配合湿润宽度和压力限流边界 |
| 低Ksat使用较大负水头 | Drip1水量偏低，Drip2也可能欠湿 | 会压低入渗量，不能单独解决宽度问题 |

## 子代理审阅要点

两个独立子代理给出的共同判断：

- 根本风险不是`.drp`滴灌量单位，而是固定水头边界若无供水限制，可能让土体按导水能力额外吸水。
- `DripWetWidthMax=0`落到默认宽度时，砂壤土Drip2有横向铺开风险。
- `KAT=1`下宽度/半径语义必须说明清楚；当前验证中的湿润宽度按径向`x`跨度解释。
- 不建议继续走有限conductance调参路线。
- 最严谨的长期方案仍是HYDRUS式活动集：中心段先试算，拒收水量逐步给邻段，活动集变化后重解。

本轮最终实现没有采用失败的conductance路线，而是用土壤导水率限制候选湿润宽度，并用二维储水差和G05闭合同时约束供水过量风险。

## 根系二维图

官方HYDRUS Drip1/Drip2是无作物短时算例，不能直接验证根系吸水。作物场景必须另外输出根系分布图。

当前已有图：

- `tmp/codex_precision_drip_validation/precision_delta_theta_root_overlay_0601.png`
- `tmp/codex_precision_drip_validation/precision_root_density_0601.png`

这些图只回答“MAIZSIM作物算例中滴灌增湿区是否覆盖根区”，不能替代HYDRUS官方Drip1/Drip2湿润体物理验证。

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
- 目标3接受门已运行，当前`24 pass / 0 fail`。

## 文献判断

HYDRUS官方说明把SurfaceDrip列为特殊边界条件，并明确其动态湿润面积算法：先在滴头节点施加Neumann通量；若容纳该通量所需压力头大于零，就把该节点切为零压力Dirichlet边界，计算实际入渗`Qa`；超额`Q-Qa`继续施加到邻近节点，迭代直到整个灌水通量被处理完。

Kandelous和Simunek的HYDRUS-2D滴灌研究说明，评价滴灌模型不能只看总水量，还要看滴头周围水分分布和湿润尺寸。后续比较数值、解析和经验模型的研究也把湿润区尺寸误差作为核心指标，并指出HYDRUS-2D虽然输入复杂，但能更精细估计滴灌水分运动。

因此，从文献和HYDRUS算法定义看，目标3的合理验收必须包含二维图像和湿润体几何。当前实现已通过官方Drip1/Drip2二维验收，但若要对任意土壤和滴灌制度泛化，仍应继续实现真正的供水受限动态活动边界。

参考资料：

- HYDRUS Special Boundary Conditions, Surface Drip Irrigation：<https://www.pc-progress.com/en/OnlineHelp/HYDRUS3/SpecialBoundaryConditions1.html>
- Kandelous, M. M. and Simunek, J. 2010. Numerical simulations of water movement in a subsurface drip irrigation system under field and laboratory conditions using HYDRUS-2D：<https://www.pc-progress.com/Documents/Jirka/Kandelous_Simunek_AWM_2010.pdf>
- Kandelous, M. M. and Simunek, J. 2010. Comparison of numerical, analytical, and empirical models to estimate wetting patterns for surface and subsurface drip irrigation：<https://link.springer.com/article/10.1007/s00271-009-0205-9>
