"""回归测试：台账 spent() 必须对残行/坏值稳健（曾因 float(None) 抛 TypeError 毒化全流程）。"""
import csv
import sys
from pathlib import Path

EXT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXT))
from api_client import Client  # noqa: E402


def test_spent_skips_torn_and_bad_rows(tmp_path=None):
    c = Client()
    base = c.spent()
    # 写一个含残行/坏值/合法值的临时 per-process 台账到 EXT，spent() 应跳坏行、加合法值
    probe = EXT / "cost_ledger_pTEST.csv"
    with probe.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(Client._HEADER)
        w.writerow([])                                   # 空残行
        w.writerow(["e1c_m3:F3:r1"])                     # 撕裂残行（唯一字段）
        w.writerow(["ts", "M2", "deepseek", "s", "1", "1", "abc", "t"])  # 坏 cost
        w.writerow(["ts", "M2", "deepseek", "s", "1", "1", "0.010000", "t"])  # 合法 $0.01
    try:
        after = c.spent()
        assert abs((after - base) - 0.01) < 1e-6, f"expected +0.01, got {after - base}"
    finally:
        probe.unlink(missing_ok=True)


if __name__ == "__main__":
    test_spent_skips_torn_and_bad_rows()
    print("OK: spent() robust to torn/bad rows")
