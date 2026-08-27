# Appendix A · GEE 重构与复现校验（R1.3）

- 分析样本：1319 观测，12 个 task cluster（confirmatory，排除 dev TGU2/TGU4）
- 模型：GEE binomial/logit，exchangeable working correlation，cluster = task_id；参考组 = M1，C1（ungrounded, unstructured）
- 任务聚类 case bootstrap：1931/2000 次成功重拟合（整簇重抽）

## 与正文已报数字的复现校验

| 量 | 重构值 | 正文值 | 容差 | 判定 |
|---|---|---|---|---|
| grounding OR | 7.241 | 7.24 | ±0.05 | ✅ |
| grounding CI low | 2.294 | 2.29 | ±0.05 | ✅ |
| grounding CI high | 22.86 | 22.86 | ±0.5 | ✅ |
| structure OR | 1.283 | 1.28 | ±0.05 | ✅ |
| structure p | 0.2331 | 0.23 | ±0.02 | ✅ |
| interaction OR | 0.8583 | 0.86 | ±0.05 | ✅ |
| interaction p | 0.5246 | 0.53 | ±0.03 | ✅ |
| M4 OR | 1.71 | 1.71 | ±0.05 | ✅ |
| M4 p | 0.04154 | 0.04 | ±0.02 | ✅ |

**总体判定：全部复现一致 ✅**

## 完整系数表

| term                                                    |    beta |     SE |     OR |   OR_CI_low |   OR_CI_high |         p |   boot_OR_CI_low |   boot_OR_CI_high |
|:--------------------------------------------------------|--------:|-------:|-------:|------------:|-------------:|----------:|-----------------:|------------------:|
| Intercept (reference: M1, ungrounded/unstructured cell) | -1.886  | 0.673  | 0.1517 |     0.04056 |       0.5672 | 0.005068  |          0.02026 |            0.7491 |
| Grounding (C3/C4 vs C1/C2)                              |  1.98   | 0.5865 | 7.241  |     2.294   |      22.86   | 0.0007373 |          2.963   |           38.61   |
| Structure (C2/C4 vs C1/C3)                              |  0.2493 | 0.209  | 1.283  |     0.8518  |       1.933  | 0.2331    |          0.8013  |            2.097  |
| Grounding x Structure                                   | -0.1528 | 0.2402 | 0.8583 |     0.536   |       1.374  | 0.5246    |          0.4881  |            1.532  |
| Model M2 (DeepSeek-chat) vs M1                          |  0.4112 | 0.2923 | 1.509  |     0.8507  |       2.675  | 0.1595    |          0.8674  |            3.1    |
| Model M3 (Qwen3-235B) vs M1                             |  0.2347 | 0.2283 | 1.264  |     0.8084  |       1.978  | 0.304     |          0.7765  |            2.396  |
| Model M4 (DeepSeek-reasoner) vs M1                      |  0.5365 | 0.2632 | 1.71   |     1.021   |       2.864  | 0.04154   |          1.029   |            3.388  |