# Smoke test 报告（dev 任务 TGU2/TGU4 · M2+M4 · k≤2）

## k=0 基线（本次新跑）
- C1: 25/36 = 69% strict
- C3: 27/36 = 75% strict

## 修复率（k0 失败组 n=20，臂内各修一次）

| 臂 | 修复成功/失败组 | 修复率 | 平均额外调用 | 平均额外token(完成) |
|---|---|---|---|---|
| resample(best-of-1extra) | 2/20 | 10% | 1.0 | — |
| resample(best-of-2extra) | 4/20 | 20% | 2.0 | — |
| F1 | 2/20 | 10% | 1.9 | 1858 |
| F2 | 2/20 | 10% | 2.0 | 1777 |
| F3 | 7/20 | 35% | 1.8 | 1642 |

## 命门 A：修复率 × 初始错误类别（F3 臂）

| 初始错误类别 | 条件 | 修复成功/n | 修复率 |
|---|---|---|---|
| context_displacement | C1 | 4/10 | 40% |
| context_displacement | C3 | 3/9 | 33% |
| fabricated_quotation | C1 | 0/1 | 0% |

## 门槛判定
- H1 增益门槛（修复率 vs 盲重采样）：F3 35% vs resample 20% → PASS
- H2c 定向价值（F3 vs F1 二值）：35% vs 10% → 分层可见
- 命门 A（类别拉开）：context_displacement 37% vs fabrication 0%（差 +37pp）→ RQ2 有戏
