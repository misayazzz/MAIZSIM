# MAIZSIM滴灌湿润体实现调查与验证记录

记录日期：2026-05-24

最新更新：2026-05-26

## 当前结论

如果目标只是让滴灌水量进入MAIZSIM，并在季节尺度上检查水量闭合、作物根区水分响应和压力修正，普通地表滴灌源项已经够用。

如果目标是精细模拟滴灌湿润体形态，尤其要和HYDRUS二维`theta(x,z,t)`图对比，旧实现不够。这个目标下，评价标准不再是“水量进了土体”或“根区平均含水量有响应”，而是二维湿润体的宽度、深度、连通区域、峰值位置、残差分布和阈值敏感性都要能和HYDRUS图像对得上。

本轮已经按这个目标做了第一版可复核实现和同条件短时验证：

- 官方HYDRUS `Drip1.h3d3`和`Drip2.h3d3`已可直接解析，导出二维`theta`场、网格、土壤参数、轴对称体积权重和HYDRUS自身湿润体指标。
- MAIZSIM新增官方HYDRUS对齐验证脚本，能自动生成Drip1-like/Drip2-like短时算例：同网格、同`KAT=1`轴对称几何、同土壤参数、同初始压力头`h=-100 cm`、同`2 L/h`持续`2 h`。
- Fortran侧已区分地表几何湿润半径和边界积分权重。`KAT=1`下不再把`Width(k)`简单当横向长度，而是用环带面积比例分配覆盖权重。
- 对低饱和导水率壤土，新增`DripMode=3`直接形态分配模式，用于HYDRUS二维形态对比。它用`.drp`中的`DripPcMax`作为直接源项深度，并在该事件步绕过地表径流扩展和WaterMover二次搬运。
- `DripMode=3`已增加容量受限重分配和径向/深度权重：浅层源区节点达到`theta_s`上限后，剩余水会继续分配给同一源区内仍有容量的节点；同时不再把源区内所有节点均匀加水，而是让滴头附近和浅层节点获得更高权重，以减少横向均匀铺开的假象。
- `DripSpreadMode=1`的目标湿润宽度改为按当前时间步结束时的有效供水时间计算，避免最后一个滴灌步使用步初宽度导致湿润体形态滞后。
- 对砂壤土，仍可使用普通`DripSpreadMode=1`标定宽度模式；Drip2短时对照中横向宽度和储水增量较接近HYDRUS，但垂向推进仍偏浅。
- 二维对比图已经标出滴头中心和地表滴灌源区，并在HYDRUS/MAIZSIM增湿图上叠加同一`Delta theta`阈值对应的湿润锋轮廓。输出中同时给出全局湿润区指标和“与滴头连通的湿润体”指标，避免少数远端临界湿点把宽度误读成全域铺开。
- 自动输出阈值敏感性CSV和PNG，用`Delta theta = 0.002/0.005/0.010/0.020/0.050`检查宽度、深度和IoU是否依赖单一阈值。
- G05输出新增`DripSourceInput`和`DripSourceLoss`，用于核对`DripSpreadMode=1`源项分配层面的水量闭合。最新Drip1/Drip2重跑显示，当前源项分配层面`DripDemand = DripSourceInput + DripSourceLoss`，且`SourceLoss=0`；因此Drip1约`0.70 L`储水不足不是源区容量直接拒水造成的，而是当前工程标定和HYDRUS二维水动力过程仍有差异。
- 新增`DripSpreadMode=2`作为压力头受限边界原型：滴灌水以地表通量进入`WaterMover`，并只对滴灌激活边界启用`hNew >= 0`时的`CodeW=4, h=0`湿端压力限制。低流量烟测可跑通，但官方`2 L/h` Drip2仍会超时，说明该模式只是第一步，还缺HYDRUS式同一步超额通量重分配和稳定子步控制。

当前可以谨慎说：MAIZSIM已经具备与官方HYDRUS SurfaceDrip二维场做同条件短时对照的工具链，并且Drip1/Drip2第一版对照结果在湿润面积、深度、交并比和轴对称储水增量上已进入可分析范围。

当前仍不能说：已经完整复现HYDRUS有限元SurfaceDrip边界迭代，或者已经达到“精细滴灌湿润体模型”的终点。`DripMode=3`是面向二维形态对比的工程标定，不是严格HYDRUS压力头受限边界条件；容量受限重分配和径向/深度加权已改善Drip1形态与储水，但Drip1仍存在约`0.70 L`储水不足。

如果最终目标就是“和HYDRUS二维湿润体图精细对比”，后续代码必须继续往物理边界迭代方向改，而不能只靠固定宽度、固定深度或单次形态标定。

## 代码层面的最新实现

### Fortran核心

核心文件：

- `Soil Source/Drip.FOR`
- `Soil Source/PuSurface.ins`
- `Soil Source/OUTPUT.FOR`
- `Soil Source/Watmov.for`
- `Soil Source/surfaceWaterBalanceAdjustment.for`

`.drp`事件行仍兼容6、11、12和13字段：

```text
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax
Start_Date Start_hour Stop_Date Stop_hour wAppl Num_nodes DripMode DripHIn DripExp DripPcMin DripPcMax DripWetWidthMax DripSpreadMode
```

关键字段：

- `wAppl`：输入单位`cm/h`，Fortran内部换算为`cm/day`。
- `DripSpreadMode=0`：旧的入渗受限触发扩展模式。
- `DripSpreadMode=1`：HYDRUS SurfaceDrip宽度标定模式。
- `DripSpreadMode=2`：压力头受限地表边界原型。该模式把滴灌写入`DripRate -> VarBW -> Q -> CodeW=-4`路径，由`WaterMover`求解；若滴灌激活节点在入渗通量下达到`hNew >= 0`，则切换为`CodeW=4, h=0`压力头边界。
- `DripWetWidthMax`：地表最大湿润半径或宽度口径，取决于几何。`KAT=1`且滴头在轴线时按径向半径`[0,R]`解释。
- `DripMode=1/2`：压力补偿模式，要求`DripHIn>0`。
- `DripMode=3`：直接形态分配模式，不走压力补偿公式，允许`DripHIn=0`，`DripPcMax`作为直接源项深度。

`DripSpreadMode=1`的主要计算过程：

1. 用`DripEffHours`累计有效供水时间，压力不足只会降低后续扩展速率，不会让目标湿润宽度随瞬时压力因子下降而缩回。
2. 当前时间步内，用步末有效供水时间`DripEffHours + StepHours * PressureFactor`计算目标地表湿润范围；这样当前步施加的水量和当前步目标宽度使用同一时间口径。
3. 调用`DripTargetWidth(MaxWetWidth, EffectiveHours)`得到目标地表湿润范围。
4. `KAT=1`轴对称滴头在轴线时，目标区间为`[0,TargetWetWidth]`，不是`x ± TargetWetWidth/2`。
5. 对每个地表边界段重构几何控制区间，计算与目标区间的交集。
6. `DripCoverMeasure()`把几何覆盖长度换成边界积分权重。`KAT=1`用环带比例`(r2^2-r1^2)/(R2^2-R1^2)`，`KAT=2`用普通长度比例。
7. 普通模式下，按覆盖权重更新滴灌诊断通量；直接模式下，把当前步水量按指定源区体积转成节点含水量增量，并同步`hNew`、`ThNew`和WaterMover旧状态数组。
8. 新增`DripSourceInput`和`DripSourceLoss`，统计源项分配层面的入土水量和未分配水量。这个诊断适用于`DripSpreadMode=1`源区分配过程，不应误读为HYDRUS压力边界主动集迭代结果。

这次最重要的代码修正是`DripMode=3`：

- 输入校验从`0..2`扩展为`0..3`。
- `DripMode=3`不再要求`DripHIn>0`。
- 压力补偿公式只用于`DripMode=1/2`，避免`DripHIn=0`导致`PressureFactor=0`、实际无水进入。
- `DripMode=3`活动时显式设置`DripBypassRunoff=1`和`DripBypassWaterMover=1`，避免直接形态分配又被地表径流扩展或WaterMover重复改写。
- `DripMode=3`的直接分配现在按源区节点剩余孔隙容量迭代重分配，不再在某些浅层节点达到饱和上限时直接丢掉超额水。
- `DripMode=3`的源区体积不再是简单几何体积，而是径向权重和深度权重加权后的有效源区体积。越靠近滴头、越靠近地表的节点权重越高；远端和较深节点仍可入水，但不会和滴头附近节点等量分配。
- `DripMode=3`的源项水量诊断会写入G05：`DripSourceInput`表示成功分配给源区节点的水量，`DripSourceLoss`表示源区容量不足后仍未分配的水量。当前Drip1/Drip2短时算例中`DripSourceLoss=0`。

压力边界原型的最新状态：

- `DripSpreadMode=2`不设置`DripBypassWaterMover`，也不直接改`hNew/ThNew`。
- 新增`DripPressureLimit_Rate`，只标记`DripSpreadMode=2`写入的滴灌边界。这样湿端压力限制不会影响普通降雨、普通地表灌溉或自动灌溉。
- `WaterMover`在滴灌激活的`CodeW=-4`节点上，如果求解过程中`hNew >= 0`，会切换为`CodeW=4, h=0`；对已经切到`CodeW=4`且仍贴近`h=0`的节点加入小滞回，避免马上回跳到通量边界。
- `QAct`实际边界通量统计已覆盖`CodeW=4`，否则压力边界节点会缺少实际入渗诊断。
- 当前仍没有同一步内的HYDRUS主动集重分配：若单个滴头节点不能接纳指定通量，超额水不会在同一个求解步内自动分给相邻地表节点并重解。这就是官方`2 L/h`算例仍不稳定的主要原因。

### Python工具链

核心文件：

- `DA_Framework/da_framework/hydrus_official_export.py`
- `DA_Framework/da_framework/hydrus_2d_comparison.py`
- `DA_Framework/da_framework/hydrus_aligned_validation.py`
- `DA_Framework/tests/test_hydrus_aligned_validation.py`
- `DA_Framework/tests/test_hydrus_2d_comparison.py`

当前能力：

- 从官方HYDRUS OLE工程文件或解包目录读取`MESHTRIA.000`、`th.out`、`SELECTOR.IN`、`BOUNDARY.IN`和`ATMOSPH.IN`。
- 导出HYDRUS节点场、网格、初始/输出/增量三联图和HYDRUS自身湿润体指标。
- 从官方`BOUNDARY.IN`写出MAIZSIM `KAT=1`网格和边界宽度。
- 自动写入Drip1-like/Drip2-like短时MAIZSIM算例。
- 自动运行baseline和drip两个MAIZSIM目录，再和HYDRUS输出做二维场对比。
- 输出`theta_mae`、`theta_rmse`、`theta_corr`、`delta_theta_mae`、`delta_theta_rmse`、湿润面积、湿润宽度、湿润深度、交并比、峰值位置距离。
- 额外输出`source_wet_*`指标，只统计与滴头源区连通的湿润体。
- 若HYDRUS导出包含`axisym_volume_cm3`，额外输出轴对称储水增量：`hydrus_delta_storage_l`、`maizsim_delta_storage_l`、储水残差和相对施水量比例。
- 解析MAIZSIM G05中的滴灌诊断，并把`g05_drip_demand_mm_sum`、`g05_drip_source_input_mm_sum`、`g05_drip_source_loss_mm_sum`和`g05_source_closure_residual_mm`写入HYDRUS对齐汇总表。
- 额外输出阈值敏感性表和图，检查湿润体结论是否只由某一个`Delta theta`阈值造成。
- 二维对比图中黑色等值线表示当前阈值下的湿润锋，红色标注表示滴头中心和地表源区。

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

用`Delta theta >= 0.005`计算的官方HYDRUS 2 h湿润体指标：

| 工程 | HYDRUS湿润宽度 | HYDRUS湿润深度 | `Delta theta`最大值 |
| --- | ---: | ---: | ---: |
| `Drip1` | `28.055 cm` | `18.476 cm` | `0.187579` |
| `Drip2` | `21.904 cm` | `23.026 cm` | `0.287925` |

说明：

- 这里的“宽度”是`KAT=1`径向`x`跨度，不是左右对称直径。
- 早期文档里提到的`16.3 cm`和`39.7 cm`来自公开图的地表湿润半径/宽度人工数字化曲线；本节指标来自官方工程`th.out`二维节点场。两者口径不同，不能混用。

## 同条件二维对照结果

验证命令：

```powershell
pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_aligned_validation `
  --project-file tmp\codex_hydrus_official\drip\Drip1.h3d3 `
  --workspace tmp\codex_hydrus_source_diag_runs_Drip1 `
  --output-dir tmp\codex_hydrus_source_diag_outputs `
  --prefix Drip1SourceDiag `
  --timeout-seconds 240

pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_aligned_validation `
  --project-file tmp\codex_hydrus_official\drip\Drip2.h3d3 `
  --workspace tmp\codex_hydrus_source_diag_runs_Drip2 `
  --output-dir tmp\codex_hydrus_source_diag_outputs `
  --prefix Drip2SourceDiag `
  --timeout-seconds 240
```

输出图：

- `tmp/codex_hydrus_source_diag_outputs/Drip1SourceDiag_aligned_fields.png`
- `tmp/codex_hydrus_source_diag_outputs/Drip2SourceDiag_aligned_fields.png`

输出表：

- `tmp/codex_hydrus_source_diag_outputs/Drip1SourceDiag_aligned_validation_summary.csv`
- `tmp/codex_hydrus_source_diag_outputs/Drip2SourceDiag_aligned_validation_summary.csv`
- `tmp/codex_hydrus_source_diag_outputs/Drip1SourceDiag_aligned_threshold_sensitivity.csv`
- `tmp/codex_hydrus_source_diag_outputs/Drip2SourceDiag_aligned_threshold_sensitivity.csv`

阈值敏感性图：

- `tmp/codex_hydrus_source_diag_outputs/Drip1SourceDiag_aligned_threshold_sensitivity.png`
- `tmp/codex_hydrus_source_diag_outputs/Drip2SourceDiag_aligned_threshold_sensitivity.png`

最新结果：

| 工程 | 模式 | MAIZSIM源区半径 | 直接源项深度 | `theta_mae` | `theta_rmse` | `theta_corr` | `delta_rmse` | 全局IoU | 连通IoU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `DripMode=3` | `28.055 cm` | `13.857 cm` | `0.006007` | `0.020564` | `0.927765` | `0.011895` | `0.877477` | `0.880131` |
| `Drip2` | `DripMode=0` | `16.300 cm` | `0.000 cm` | `0.004940` | `0.018222` | `0.966528` | `0.016910` | `0.862990` | `0.862990` |

湿润体尺寸：

| 工程 | HYDRUS全局宽度 | MAIZSIM全局宽度 | HYDRUS连通宽度 | MAIZSIM连通宽度 | HYDRUS深度 | MAIZSIM深度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `28.055 cm` | `50.000 cm` | `28.055 cm` | `33.243 cm` | `18.476 cm` | `19.253 cm` |
| `Drip2` | `21.904 cm` | `23.345 cm` | `21.904 cm` | `23.345 cm` | `23.026 cm` | `18.979 cm` |

轴对称储水增量：

| 工程 | 施水量 | HYDRUS储水增量 | MAIZSIM储水增量 | MAIZSIM-HYDRUS | HYDRUS/施水量 | MAIZSIM/施水量 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `4.000 L` | `3.983 L` | `3.278 L` | `-0.705 L` | `0.996` | `0.820` |
| `Drip2` | `4.000 L` | `3.997 L` | `3.865 L` | `-0.132 L` | `0.999` | `0.966` |

G05源项诊断：

| 工程 | `DripDemand`累计 | `DripSourceInput`累计 | `DripSourceLoss`累计 | 源项闭合残差 |
| --- | ---: | ---: | ---: | ---: |
| `Drip1` | `2.494 mm` | `2.494 mm` | `0.000 mm` | `0.000 mm` |
| `Drip2` | `3.188 mm` | `3.188 mm` | `0.000 mm` | `0.000 mm` |

说明：这里的G05单位是模型平面平均水深`mm`，用于检查MAIZSIM源项分配层面的闭合；不能直接和上表的轴对称储水升数混用。

对Drip1的解释：

- 全局宽度`50 cm`不是主湿润体真的铺满全域，而是`Delta theta >= 0.005`阈值下有少数远端浅层临界点。连通湿润体宽度为`33.243 cm`，更能代表滴头形成的主体湿润范围。
- Drip1的`source_wet_iou=0.880131`，深度误差约`0.78 cm`，说明主体湿润体在当前阈值下仍接近HYDRUS形态范围。
- 容量受限重分配和径向/深度加权后，Drip1的MAIZSIM轴对称储水增量由早期`2.850 L`提高到`3.278 L`，但HYDRUS为`3.983 L`。这说明只看二维形态仍会过度乐观，当前直接形态分配还没有完全满足精细模型对水量闭合的要求。
- 最新G05诊断显示Drip1源项分配层面没有`DripSourceLoss`，因此`0.70 L`储水不足不能再解释为“源区容量不够导致直接丢水”。更合理的解释是：当前`DripMode=3`把水按标定源区直接写入含水量，随后与HYDRUS压力受限边界、水力梯度和有限元瞬态迁移过程不同。
- Drip1的单点峰值距离仍为`17.575 cm`。这主要因为HYDRUS壤土表层峰值区域较平坦，最大节点落在`x≈17.6 cm`，而MAIZSIM直接分配峰值在滴头轴线附近。这个指标应结合图和连通IoU一起看，不能单独判定失败或通过。
- `DripMode=3`当前把`DripBypassWaterMover`作为事件步全局旁路开关。当前HYDRUS对齐算例是单一滴灌事件，因此这个旁路可控；若同一时间步混有其他非`DripMode=3`灌溉事件，仍需改成更局部的旁路或限制输入组合。

对Drip2的解释：

- 砂壤土结果更稳定：全局和连通宽度一致，MAIZSIM宽度`23.345 cm`略高于HYDRUS`21.904 cm`。
- MAIZSIM湿润深度`18.979 cm`小于HYDRUS`23.026 cm`，说明垂向推进仍偏浅，是后续改进重点。
- MAIZSIM轴对称储水增量`3.865 L`，接近HYDRUS的`3.997 L`，水量误差明显小于Drip1。
- 峰值距离`0.788 cm`，说明滴头位置和峰值位置基本对齐。

阈值敏感性检查显示，Drip1在较高阈值下不会出现全域宽度；Drip2的宽度较稳定，但垂向深度偏浅在各阈值下都存在。阈值敏感性PNG还包含`Stored / applied`面板，用轴对称体积权重显示储水比例；该储水比例不随湿润阈值变化。

| 工程 | 阈值 | 连通IoU | MAIZSIM连通宽度 | HYDRUS连通宽度 | MAIZSIM连通深度 | HYDRUS连通深度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `0.002` | `0.764802` | `50.000 cm` | `29.219 cm` | `19.764 cm` | `18.923 cm` |
| `Drip1` | `0.005` | `0.880131` | `33.243 cm` | `28.055 cm` | `19.253 cm` | `18.476 cm` |
| `Drip1` | `0.010` | `0.915969` | `27.549 cm` | `28.055 cm` | `18.476 cm` | `17.903 cm` |
| `Drip1` | `0.020` | `0.902415` | `25.411 cm` | `27.549 cm` | `17.530 cm` | `17.270 cm` |
| `Drip1` | `0.050` | `0.876213` | `21.350 cm` | `26.366 cm` | `16.325 cm` | `16.596 cm` |
| `Drip2` | `0.002` | `0.860130` | `23.345 cm` | `21.904 cm` | `19.439 cm` | `23.536 cm` |
| `Drip2` | `0.005` | `0.862990` | `23.345 cm` | `21.904 cm` | `18.979 cm` | `23.026 cm` |
| `Drip2` | `0.010` | `0.853882` | `22.339 cm` | `21.350 cm` | `18.596 cm` | `22.554 cm` |
| `Drip2` | `0.020` | `0.821350` | `21.904 cm` | `20.761 cm` | `18.476 cm` | `22.554 cm` |
| `Drip2` | `0.050` | `0.844046` | `21.350 cm` | `20.157 cm` | `17.530 cm` | `21.982 cm` |

## 这是否合理

从HYDRUS机制看，低渗透性土壤更容易在滴头附近形成不能接纳指定通量的边界状态，SurfaceDrip会把超额通量沿地表相邻边界扩展。因此“渗透性越差，越可能触发横向扩展”这个方向是合理的。

但HYDRUS不是简单按经验宽度铺水。它是压力头受限边界：某个节点不能接纳通量时，边界条件切换并重新分配超额通量。MAIZSIM当前`DripMode=3`没有完整求解这套边界迭代，而是用HYDRUS最终二维场标定一个直接源区，再把水量分配到浅层节点。因此它适合用于：

- 判断MAIZSIM是否能产生与HYDRUS同量级的二维湿润体。
- 做壤土/砂壤土短时形态对照。
- 暴露宽度、深度、峰值位置和阈值敏感性问题。

它不适合直接宣称：

- MAIZSIM已经复现HYDRUS SurfaceDrip算法。
- 所有土壤、所有流量和所有施水量都已验证。
- 田间实测湿润锋已经校准。
- Drip1已经在水量闭合意义上通过；当前MAIZSIM储水增量明显低于HYDRUS。

本轮还做过两个没有保留到主线的代码路线验证：

- 把`DripSpreadMode=1`改成纯地表边界通量，让WaterMover/压力求解自己消纳滴灌通量。Drip2短时算例在`240 s`超时，说明当前求解链不能直接承受这个SurfaceDrip式边界路线。
- 把滴灌作为WaterMover源项注入，而不是直接更新`theta`。Drip2同样超时，说明仅把水移到WaterMover源项并不能自动得到稳定的HYDRUS式湿润体。
- 另做过`DripMode=3`不旁路WaterMover的Drip1实验：储水量从`3.278 L`轻微改善到`3.348 L`，但二维形态明显变差，连通IoU从`0.880`降到`0.687`，湿润深度变为`25.586 cm`，超过HYDRUS的`18.476 cm`。因此没有采用这条路线。
- 新增`DripSpreadMode=2`后，Drip2在低流量`0.0002 L/h`下能完成，用于证明新边界路径和验证工具链可运行；但`0.002 L/h`和官方`2 L/h`仍会在滴灌开始后明显缩步并超时。这说明当前瓶颈不是输入格式，而是缺少HYDRUS式超额通量重分配和更稳定的子步/主动集策略。

因此当前保留的是稳定、可验证的工程标定版本；若目标是精细二维湿润体，真正的下一步不是继续调一个经验宽度，而是实现可收敛的压力头受限边界迭代和自适应子步长。

资料核对后的判断也支持这个划分。HYDRUS官方帮助和技术手册都把SurfaceDrip描述为压力头受限的动态湿润区算法：先给滴头节点施加通量，若该节点需要正压力头才能接纳指定通量，就切换为零压力头边界，计算实际入渗量，再把超额通量迭代分配到相邻节点。Kandelous和Simunek的滴灌湿润体对比研究也显示，湿润形态需要按土壤水力参数、初始含水状态、滴头流量、施水量和可能的地表积水共同判断；经验湿润体模型若不考虑这些因素，跨土壤和跨工况泛化能力有限。

所以，如果目标就是“精细模拟滴灌湿润体并与HYDRUS二维图对比”，验收口径应当升级为：

- 至少同时看二维`Delta theta`场、湿润锋轮廓、连通湿润体宽度/深度、残差图和储水闭合。
- 壤土和砂壤土不能只按土壤名称判断，应按`theta_r`、`theta_s`、`alpha`、`n`、`Ks`和初始压力头分组。
- 代码实现不能长期依赖固定宽度或固定源项深度；这两个量最多作为短期对照参数，不能作为精细物理模型的核心机制。
- 当前`DripMode=3`可以作为回归基线和问题定位工具，但目标3的下一步必须实现压力头受限边界迭代。

目标3的代码验收项应至少包括：

- 滴头节点达到压力头上限时，能自动从通量边界切换到压力头受限边界。
- 当前节点不能接纳的超额通量能按相邻地表边界重新分配，并允许湿润地表范围随边界状态动态扩展或收缩。
- 低渗透性土壤下有自适应子步长或等价稳定机制，不能靠超时或失败算例规避问题。
- 输出能闭合输入滴灌量、土体储水增量、边界出流、地表滞留/损失和数值残差。
- 二维验收同时给出`Delta theta`场、残差场、连通湿润体宽度/深度、IoU、峰值位置、储水比例和阈值敏感性。

## 绘图和根系分布

当前HYDRUS对齐图是三联图：

- 左：HYDRUS `Delta theta`。
- 中：MAIZSIM `Delta theta`。
- 右：`MAIZSIM - HYDRUS`。

图中红色标注含义：

- 红色倒三角和虚线表示滴头中心。
- 红色地表线段表示本次MAIZSIM施加的地表源区范围。
- `drip`标签标明滴灌发生位置。

图中黑色线表示当前`Delta theta`阈值下的湿润锋轮廓，用于直接比较HYDRUS和MAIZSIM湿润体形态。

已有MAIZSIM内部根系叠加图：

- `tmp/codex_precision_drip_validation/precision_delta_theta_root_overlay_0601.png`

该图显示`Delta theta = drip - baseline`和根系等值线的空间关系，能回答“滴灌增湿区是否进入根区”。它不是HYDRUS对比图，因为官方HYDRUS Drip1/Drip2本身是无作物短时算例，没有对应根系。

若要把根系也纳入HYDRUS式验证，应另做一个带根系或给定吸水项的同条件设计；不能把无作物HYDRUS Drip1/Drip2直接拿来评价根系吸水分布。

## 已完成验证命令

构建：

```powershell
& 'F:\Program Files\Microsoft Visual Studio\18\Community\MSBuild\Current\Bin\amd64\MSBuild.exe' maizsim07.sln /t:2dmaizsim /p:Configuration=Release /p:Platform=x64 /m
```

结果：

- 成功。
- 0个错误。
- 73个既有警告。

相关单元测试：

```powershell
pixi run --manifest-path pixi.toml python -m unittest discover -s DA_Framework\tests
```

结果：

- 95个测试通过。

官方HYDRUS同条件验证脚本：

- Drip1成功运行，生成二维图和CSV。
- Drip2成功运行，生成二维图和CSV。
- 两个MAIZSIM run均完成到`39200.000000`，未出现ORTHOMIN失败、Fortran严重错误或脚本traceback。
- 最新重跑同时生成G05源项闭合诊断：Drip1和Drip2的`g05_source_closure_residual_mm`均为`0.0`。

## 仍需后续处理

若目标保持为“精细模拟滴灌湿润体形态并与HYDRUS二维图对比”，下面内容不是可选优化，而是达到目标前必须补齐的范围。

短期：

- 在已有G05源项闭合诊断基础上，继续增加逐节点源项诊断，包括源区节点、分配权重、源项体积、单步施水量和直接更新的`theta`。
- 继续追踪Drip1直接形态分配后的完整水量去向：输入滴灌量、节点储水增量、边界出流、地表旁路和WaterMover旁路。当前已排除“源区容量直接丢水”这一解释，但还没有完成节点储水与边界通量的逐项闭合。
- 对Drip1补充更多阈值图，例如`0.005`、`0.010`、`0.020`，避免单一阈值导致宽度解释不稳。
- 补做源项深度灵敏度分析。当前Drip1用`0.75 * HYDRUS湿润深度`作为直接源项深度，结果明显优于直接等于最终湿润深度，但这是标定参数，不是普适规律。
- 为Drip2补垂向推进改进，因为当前MAIZSIM深度偏浅约`4.0 cm`。
- 将`DripBypassWaterMover`从全局事件步开关收窄为局部机制，或在输入校验中禁止`DripMode=3`与其他需要WaterMover的同步事件混用。

中期：

- 实现更接近HYDRUS的压力头受限边界迭代，而不是只用目标宽度或直接分配。这个迭代需要根据地表节点压力头、可接纳通量和局部水量守恒动态扩展或收缩源区。
- 在`DripSpreadMode=2`基础上补同一步主动集：求解中心滴头节点实际入渗量，计算超额通量，分配到相邻地表节点，更新边界条件并重解，直到超额水被接纳、进入地表滞留/径流，或达到明确的稳定退出条件。
- 增加自适应子步长，避免低渗透性土壤下通量过大导致数值不稳。
- 用更多HYDRUS工程或论文数据覆盖砂土、壤砂土、粉壤土、黏壤土、黏土等质地。不要只按土壤名称标定，应按`theta_r`、`theta_s`、`alpha`、`n`、`Ks`和初始含水状态分组。
- 若目标转为地下滴灌，应新增地下源项或内部边界，不能复用地表`DripSpreadMode=1`。

## 不能声称和可以声称

不能声称：

- 已完整复现HYDRUS有限元二维流场。
- 已验证所有土壤质地、所有滴头流量和所有施水量。
- 已完成田间实测湿润锋校准。
- `DripWetWidthMax`是滴头物理半径。
- `DripPcMax`在`DripMode=3`中仍表示压力补偿上限。当前它表示直接源项深度。

可以谨慎声称：

- 已完成官方HYDRUS Drip1/Drip2二维场导出。
- 已完成Drip1-like/Drip2-like同条件MAIZSIM短时算例生成和自动对比。
- `KAT=1`轴对称下已把几何半径和边界积分权重分开处理。
- Drip1主体湿润体连通IoU约`0.880`，Drip2 IoU约`0.863`。
- Drip1轴对称储水增量低于HYDRUS约`0.70 L`，Drip2低约`0.13 L`。
- G05源项分配诊断显示当前Drip1/Drip2短时算例在MAIZSIM源项层面闭合，且没有`DripSourceLoss`。
- 当前结果显示滴灌确实改变二维水分场，并且图中已标出滴灌位置和地表源区。
- 已新增`DripSpreadMode=2`压力边界原型，但只能声称“边界通量路径已接通并通过低流量烟测”，不能声称官方HYDRUS流量下已经稳定或形态通过。

## 参考资料

- HYDRUS特殊边界条件说明：<https://www.pc-progress.com/en/OnlineHelp/HYDRUS3/SpecialBoundaryConditions1.html>
- Lazarovitch, N.等. 2023. Modeling of irrigation and related processes with HYDRUS. <https://www.pc-progress.com/Documents/Jirka/Lazarovitch_et_al_2023.pdf>
- Kandelous, M. M.等. 2011. Comparison of numerical, analytical, and empirical models to estimate wetting patterns for surface and subsurface drip irrigation. <https://link.springer.com/article/10.1007/s00271-009-0205-9>
- Kandelous, M. M.和Simunek, J. 2010. Numerical simulations of water movement in a subsurface drip irrigation system under field and laboratory conditions using HYDRUS-2D. <https://www.pc-progress.com/Documents/Jirka/Kandelous_Simunek_AWM_2010.pdf>
- HYDRUS 2D/3D Technical Manual, Surface Drip Irrigation with Dynamic Evaluation of the Wetted Area. <https://www2.pc-progress.com/downloads/Pgm_Hydrus3D5/HYDRUS_Technical_Manual_2D3D_V5.pdf>
