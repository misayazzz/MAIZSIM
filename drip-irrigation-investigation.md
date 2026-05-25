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
- 对砂壤土，仍可使用普通`DripSpreadMode=1`标定宽度模式；Drip2短时对照中横向宽度和储水增量较接近HYDRUS，但垂向推进仍偏浅。
- 二维对比图已经标出滴头中心和地表滴灌源区，并在HYDRUS/MAIZSIM增湿图上叠加同一`Delta theta`阈值对应的湿润锋轮廓。输出中同时给出全局湿润区指标和“与滴头连通的湿润体”指标，避免少数远端临界湿点把宽度误读成全域铺开。
- 自动输出阈值敏感性CSV和PNG，用`Delta theta = 0.002/0.005/0.010/0.020/0.050`检查宽度、深度和IoU是否依赖单一阈值。

当前可以谨慎说：MAIZSIM已经具备与官方HYDRUS SurfaceDrip二维场做同条件短时对照的工具链，并且Drip1/Drip2第一版对照结果在湿润面积、深度、交并比和轴对称储水增量上已进入可分析范围。

当前仍不能说：已经完整复现HYDRUS有限元SurfaceDrip边界迭代，或者已经达到“精细滴灌湿润体模型”的终点。`DripMode=3`是面向二维形态对比的工程标定，不是严格HYDRUS压力头受限边界条件；新增轴对称储水指标还显示Drip1存在明显储水不足。

如果最终目标就是“和HYDRUS二维湿润体图精细对比”，后续代码必须继续往物理边界迭代方向改，而不能只靠固定宽度、固定深度或单次形态标定。

## 代码层面的最新实现

### Fortran核心

核心文件：

- `Soil Source/Drip.FOR`
- `Soil Source/PuSurface.ins`
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
- `DripWetWidthMax`：地表最大湿润半径或宽度口径，取决于几何。`KAT=1`且滴头在轴线时按径向半径`[0,R]`解释。
- `DripMode=1/2`：压力补偿模式，要求`DripHIn>0`。
- `DripMode=3`：直接形态分配模式，不走压力补偿公式，允许`DripHIn=0`，`DripPcMax`作为直接源项深度。

`DripSpreadMode=1`的主要计算过程：

1. 用`DripEffHours`累计有效供水时间，压力不足只会降低后续扩展速率，不会让目标湿润宽度随瞬时压力因子下降而缩回。
2. 调用`DripTargetWidth(MaxWetWidth, DripEffHours)`得到目标地表湿润范围。
3. `KAT=1`轴对称滴头在轴线时，目标区间为`[0,TargetWetWidth]`，不是`x ± TargetWetWidth/2`。
4. 对每个地表边界段重构几何控制区间，计算与目标区间的交集。
5. `DripCoverMeasure()`把几何覆盖长度换成边界积分权重。`KAT=1`用环带比例`(r2^2-r1^2)/(R2^2-R1^2)`，`KAT=2`用普通长度比例。
6. 普通模式下，按覆盖权重更新滴灌诊断通量；直接模式下，把当前步水量按指定源区体积转成节点含水量增量，并同步`hNew`、`ThNew`和WaterMover旧状态数组。

这次最重要的代码修正是`DripMode=3`：

- 输入校验从`0..2`扩展为`0..3`。
- `DripMode=3`不再要求`DripHIn>0`。
- 压力补偿公式只用于`DripMode=1/2`，避免`DripHIn=0`导致`PressureFactor=0`、实际无水进入。
- `DripMode=3`活动时设置`DripBypassRunoff=1`和`DripBypassWaterMover=1`，避免直接形态分配又被地表径流扩展或WaterMover重复改写。

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
  --workspace tmp\codex_hydrus_aligned_runs_Drip1 `
  --output-dir tmp\codex_hydrus_aligned_outputs `
  --prefix Drip1 `
  --timeout-seconds 240

pixi run --manifest-path pixi.toml python -m DA_Framework.da_framework.hydrus_aligned_validation `
  --project-file tmp\codex_hydrus_official\drip\Drip2.h3d3 `
  --workspace tmp\codex_hydrus_aligned_runs_Drip2 `
  --output-dir tmp\codex_hydrus_aligned_outputs `
  --prefix Drip2 `
  --timeout-seconds 240
```

输出图：

- `tmp/codex_hydrus_aligned_outputs/Drip1_aligned_fields.png`
- `tmp/codex_hydrus_aligned_outputs/Drip2_aligned_fields.png`

输出表：

- `tmp/codex_hydrus_aligned_outputs/Drip1_aligned_validation_summary.csv`
- `tmp/codex_hydrus_aligned_outputs/Drip2_aligned_validation_summary.csv`
- `tmp/codex_hydrus_aligned_outputs/Drip1_aligned_threshold_sensitivity.csv`
- `tmp/codex_hydrus_aligned_outputs/Drip2_aligned_threshold_sensitivity.csv`

阈值敏感性图：

- `tmp/codex_hydrus_aligned_outputs/Drip1_aligned_threshold_sensitivity.png`
- `tmp/codex_hydrus_aligned_outputs/Drip2_aligned_threshold_sensitivity.png`

最新结果：

| 工程 | 模式 | MAIZSIM源区半径 | 直接源项深度 | `theta_mae` | `theta_rmse` | `theta_corr` | `delta_rmse` | 全局IoU | 连通IoU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `DripMode=3` | `28.055 cm` | `13.857 cm` | `0.006994` | `0.023760` | `0.894306` | `0.013792` | `0.879927` | `0.882696` |
| `Drip2` | `DripMode=0` | `16.300 cm` | `0.000 cm` | `0.004901` | `0.018267` | `0.966315` | `0.016925` | `0.860862` | `0.860862` |

湿润体尺寸：

| 工程 | HYDRUS全局宽度 | MAIZSIM全局宽度 | HYDRUS连通宽度 | MAIZSIM连通宽度 | HYDRUS深度 | MAIZSIM深度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `28.055 cm` | `50.000 cm` | `28.055 cm` | `33.243 cm` | `18.476 cm` | `18.979 cm` |
| `Drip2` | `21.904 cm` | `22.339 cm` | `21.904 cm` | `22.339 cm` | `23.026 cm` | `18.979 cm` |

轴对称储水增量：

| 工程 | 施水量 | HYDRUS储水增量 | MAIZSIM储水增量 | MAIZSIM-HYDRUS | HYDRUS/施水量 | MAIZSIM/施水量 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `4.000 L` | `3.983 L` | `2.850 L` | `-1.133 L` | `0.996` | `0.713` |
| `Drip2` | `4.000 L` | `3.997 L` | `3.812 L` | `-0.186 L` | `0.999` | `0.953` |

对Drip1的解释：

- 全局宽度`50 cm`不是主湿润体真的铺满全域，而是`Delta theta >= 0.005`阈值下有少数远端浅层临界点。连通湿润体宽度为`33.243 cm`，更能代表滴头形成的主体湿润范围。
- Drip1的`source_wet_iou=0.882696`，深度误差约`0.50 cm`，说明主体湿润体在当前阈值下接近HYDRUS形态范围。
- 但Drip1的MAIZSIM轴对称储水增量只有`2.850 L`，HYDRUS为`3.983 L`。这说明只看二维形态会过度乐观，当前直接形态分配仍不能满足精细模型对水量闭合的要求。
- Drip1的单点峰值距离仍为`17.575 cm`。这主要因为HYDRUS壤土表层峰值区域较平坦，最大节点落在`x≈17.6 cm`，而MAIZSIM直接分配峰值在滴头轴线附近。这个指标应结合图和连通IoU一起看，不能单独判定失败或通过。

对Drip2的解释：

- 砂壤土结果更稳定：全局和连通宽度一致，MAIZSIM宽度`22.339 cm`接近HYDRUS`21.904 cm`。
- MAIZSIM湿润深度`18.979 cm`小于HYDRUS`23.026 cm`，说明垂向推进仍偏浅，是后续改进重点。
- MAIZSIM轴对称储水增量`3.812 L`，接近HYDRUS的`3.997 L`，水量误差明显小于Drip1。
- 峰值距离`0.788 cm`，说明滴头位置和峰值位置基本对齐。

阈值敏感性检查显示，Drip1在较高阈值下不会出现全域宽度；Drip2的宽度较稳定，但垂向深度偏浅在各阈值下都存在。阈值敏感性PNG还包含`Stored / applied`面板，用轴对称体积权重显示储水比例；该储水比例不随湿润阈值变化。

| 工程 | 阈值 | 连通IoU | MAIZSIM连通宽度 | HYDRUS连通宽度 | MAIZSIM连通深度 | HYDRUS连通深度 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Drip1` | `0.002` | `0.783873` | `50.000 cm` | `29.219 cm` | `19.764 cm` | `18.923 cm` |
| `Drip1` | `0.005` | `0.882696` | `33.243 cm` | `28.055 cm` | `18.979 cm` | `18.476 cm` |
| `Drip1` | `0.010` | `0.904411` | `24.716 cm` | `28.055 cm` | `18.476 cm` | `17.903 cm` |
| `Drip1` | `0.020` | `0.905771` | `23.800 cm` | `27.549 cm` | `17.530 cm` | `17.270 cm` |
| `Drip1` | `0.050` | `0.844975` | `21.350 cm` | `26.366 cm` | `16.122 cm` | `16.596 cm` |
| `Drip2` | `0.002` | `0.859320` | `23.345 cm` | `21.904 cm` | `18.979 cm` | `23.536 cm` |
| `Drip2` | `0.005` | `0.860862` | `22.339 cm` | `21.904 cm` | `18.979 cm` | `23.026 cm` |
| `Drip2` | `0.010` | `0.846867` | `22.339 cm` | `21.350 cm` | `18.596 cm` | `22.554 cm` |
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

因此当前保留的是稳定、可验证的工程标定版本；若目标是精细二维湿润体，真正的下一步不是继续调一个经验宽度，而是实现可收敛的压力头受限边界迭代和自适应子步长。

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

- 93个测试通过。

官方HYDRUS同条件验证：

- Drip1通过，生成二维图和CSV。
- Drip2通过，生成二维图和CSV。
- 两个MAIZSIM run均完成到`39200.000000`，未出现ORTHOMIN失败、Fortran严重错误或脚本traceback。

## 仍需后续处理

若目标保持为“精细模拟滴灌湿润体形态并与HYDRUS二维图对比”，下面内容不是可选优化，而是达到目标前必须补齐的范围。

短期：

- 为`DripMode=3`增加更明确的逐节点源项诊断输出，包括源区节点、分配权重、源项体积、单步施水量和直接更新的`theta`。
- 追踪Drip1直接形态分配后的完整水量去向：输入滴灌量、节点储水增量、边界出流、地表旁路和WaterMover旁路，解释约`1.13 L`储水差。
- 对Drip1补充更多阈值图，例如`0.005`、`0.010`、`0.020`，避免单一阈值导致宽度解释不稳。
- 补做源项深度灵敏度分析。当前Drip1用`0.75 * HYDRUS湿润深度`作为直接源项深度，结果明显优于直接等于最终湿润深度，但这是标定参数，不是普适规律。
- 为Drip2补垂向推进改进，因为当前MAIZSIM深度偏浅约`4.0 cm`。

中期：

- 实现更接近HYDRUS的压力头受限边界迭代，而不是只用目标宽度或直接分配。这个迭代需要根据地表节点压力头、可接纳通量和局部水量守恒动态扩展或收缩源区。
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
- Drip1主体湿润体连通IoU约`0.883`，Drip2 IoU约`0.861`。
- Drip1轴对称储水增量低于HYDRUS约`1.13 L`，Drip2低约`0.19 L`。
- 当前结果显示滴灌确实改变二维水分场，并且图中已标出滴灌位置和地表源区。

## 参考资料

- HYDRUS特殊边界条件说明：<https://www.pc-progress.com/en/OnlineHelp/HYDRUS3/SpecialBoundaryConditions1.html>
- Lazarovitch, N.等. 2023. Modeling of irrigation and related processes with HYDRUS. <https://www.pc-progress.com/Documents/Jirka/Lazarovitch_et_al_2023.pdf>
- Kandelous, M. M.等. 2011. Comparison of numerical, analytical, and empirical models to estimate wetting patterns for surface and subsurface drip irrigation. <https://link.springer.com/article/10.1007/s00271-009-0205-9>
- Kandelous, M. M.和Simunek, J. 2010. Numerical simulations of water movement in a subsurface drip irrigation system under field and laboratory conditions using HYDRUS-2D. <https://www.pc-progress.com/Documents/Jirka/Kandelous_Simunek_AWM_2010.pdf>
- HYDRUS 2D/3D Technical Manual, Surface Drip Irrigation with Dynamic Evaluation of the Wetted Area. <https://www2.pc-progress.com/downloads/Pgm_Hydrus3D5/HYDRUS_Technical_Manual_2D3D_V5.pdf>
