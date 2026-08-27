# E0 汇总（零调用）

## 句位观察分析
- 句位分布：前 1/3 = 3，中 1/3 = 19，后 1/3 = 0（n=22）。
- **结论：窗口按 ±900 对称构造，句位近乎退化于中部——观察性句位分析无信息量；若要句位效应必须受控操纵（按预注册默认砍，除非后续有强理由）。**

## 失败池盘点
- 失败总数 1348；dev(TGU2/TGU4) 失败 237。
- C1: fabrication 池=171，context_displacement 池=133。
- C2: fabrication 池=110，context_displacement 池=176。
- C3: fabrication 池=39，context_displacement 池=236。
- C4: fabrication 池=12，context_displacement 池=265。

## best-of-k
- 见 best_of_k.md；闭环修复必须战胜其中 hypergeometric 口径的对应曲线才有'定向反馈净价值'。
