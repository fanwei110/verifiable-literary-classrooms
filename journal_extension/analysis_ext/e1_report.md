# E1a 主线分析（['e1c_m2', 'e1c_m3', 'e1c_m4', 'e1c_m1']）

F3 记录 1979；去重 group 1979

## k=0 基线 strict%（confirmatory 12 任务；dev 另列）

| 模型 | 条件 | conf n | conf strict% | dev strict% |
|---|---|---|---|---|
| M1 | C3 | 60 | 52% | 70% |
| M1 | C4 | 60 | 67% | 80% |
| M2 | C1 | 120 | 19% | 75% |
| M2 | C2 | 119 | 23% | 63% |
| M2 | C3 | 120 | 74% | 67% |
| M2 | C4 | 120 | 72% | 65% |
| M3 | C1 | 120 | 23% | 58% |
| M3 | C2 | 120 | 29% | 63% |
| M3 | C3 | 120 | 60% | 75% |
| M3 | C4 | 120 | 62% | 63% |
| M4 | C1 | 60 | 27% | 67% |
| M4 | C2 | 60 | 30% | 73% |
| M4 | C3 | 60 | 72% | 77% |
| M4 | C4 | 60 | 70% | 77% |

## 可修性矩阵（headline）：F3 修复率 × 初始错误类别 × 条件
（仅 confirmatory 12 任务；k0 失败组为分母）

| 初始错误类别 | 条件 | 修复/n | 修复率 | 95%CI(任务聚类) |
|---|---|---|---|---|
| context_displacement | C1 | 9/49 | 18% | [2, 64] |
| context_displacement | C2 | 8/53 | 15% | [1, 54] |
| context_displacement | C3 | 6/79 | 8% | [3, 29] |
| context_displacement | C4 | 6/91 | 7% | [1, 27] |
| fabricated_quotation | C1 | 33/138 | 24% | [10, 42] |
| fabricated_quotation | C2 | 20/115 | 17% | [6, 32] |
| fabricated_quotation | C3 | 17/33 | 52% | [29, 91] |
| fabricated_quotation | C4 | 1/16 | 6% | [0, 75] |
| format_failure | C1 | 1/6 | 17% | [0, 100] |
| format_failure | C2 | 4/9 | 44% | [0, 85] |
| format_failure | C3 | 6/8 | 75% | [20, 100] |
| format_failure | C4 | 2/3 | 67% | [0, 100] |
| misattribution | C1 | 3/18 | 17% | [11, 100] |
| misattribution | C2 | 5/25 | 20% | [10, 27] |
| misattribution | C3 | 3/4 | 75% | [25, 100] |
| misattribution | C4 | 1/5 | 20% | [0, 100] |
| version_drift | C1 | 6/22 | 27% | [0, 29] |
| version_drift | C2 | 6/17 | 35% | [31, 100] |
| version_drift | C3 | 0/1 | 0% | [0, 0] |
| version_drift | C4 | 1/2 | 50% | [50, 50] |

## H2a 错误类别修复率排序（池化 grounded 条件 C2/C3/C4）

- format_failure: 12/20 = 60%
- version_drift: 7/20 = 35%
- misattribution: 9/34 = 26%
- fabricated_quotation: 38/164 = 23%
- context_displacement: 20/223 = 9%

## H2b 捏造类修复率：C1(无窗) vs C3(有窗)

- C1 fabrication: 33/138 = 24%
- C3 fabrication: 17/33 = 52%

## 存活曲线：F3 每轮累计修复率

| 到第 k 轮 | 累计修复% |
|---|---|
| 1 | 10% |
| 2 | 16% |
| 3 | 20% |

## H1a 主要对比（primary）：C3 confirmatory F3 修复率（k0 失败组内）
- 修复率 = 26%  95%CI[12, 62]（125 组，任务聚类自助）
- 门槛：≥10pp 提升即 C3 最终率相对 k0 抬升 → 见 k0 基线对照

