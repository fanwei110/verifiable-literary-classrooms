# 反-Goodhart 护栏面板（审计-only）

来源 ['e1c_m2']；含修复轮记录 331

## 逐轮引文平均长度 / 证据条数（塌缩检测）
| 轮 k | n | 平均引文字符数 | 平均证据条数 |
|---|---|---|---|
| 0 | 331 | 111 | 1.54 |
| 1 | 331 | 97 | 1.54 |
| 2 | 285 | 86 | 1.48 |
| 3 | 252 | 84 | 1.52 |

引文长度 k0→k3: -24% → **⚠️ 引文显著变短，修复以缩短换分**

## strict 但非 defensible（背离）：0（修复后严格通过却非可辩护——异常应为 0，>0 需查）

## 修复后引文集中度 top-5（是否塌缩到易验证名句）
| 引文前缀 | 出现次数 |
|---|---|
| It was the best of times, it was the worst of time... | 19 |
| Is this a dagger which I see before me, / The hand... | 13 |
| It is a truth universally acknowledged, that a sin... | 9 |
| It is a far, far better thing that I do, than I ha... | 8 |
| Of Mans First Disobedience, and the Fruit / Of tha... | 8 |

（去重引文 62 条；若 top-1 占比过高＝塌缩迹象）
