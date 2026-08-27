"""构建中文语料 processed（结构分段 + 冻结哈希）。
读 corpus_zh/raw/*.json（每部作品含 zhang 列表）→ 输出 corpus_zh/processed/corpus_index_zh.json。
locator 用篇名（论语按篇引用，如"學而第一"）。clean_text = 全章拼接。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"
OUT = Path(__file__).resolve().parent / "processed" / "corpus_index_zh.json"


def build() -> None:
    index = {}
    for f in sorted(RAW.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        wid = d["work_id"]
        segments = []
        parts = []
        for z in d["zhang"]:
            segments.append({
                "locator": d["book_title"],          # 篇名（论语按篇引用）
                "zhang_id": z["id"],
                "text": z["text"],
            })
            parts.append(z["text"])
        clean_text = "\n".join(parts)
        raw_bytes = f.read_bytes()
        entry = index.setdefault(wid, {
            "work_id": wid, "title": d["title"], "author": d["author"],
            "source": d.get("source"), "source_url": d.get("source_url"),
            "edition_note": d.get("edition_note"), "locator_mode": d.get("locator_mode"),
            "segments": [], "clean_text": "",
        })
        entry["segments"] += segments
        entry["clean_text"] = (entry["clean_text"] + "\n" + clean_text).strip() if entry["clean_text"] else clean_text
        entry.setdefault("books", []).append({
            "book_title": d["book_title"],
            "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "clean_sha256": hashlib.sha256(clean_text.encode("utf-8")).hexdigest(),
            "n_zhang": len(d["zhang"]),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    for wid, e in index.items():
        print(f"{wid}: {len(e['segments'])} segments, clean_text {len(e['clean_text'])} chars, "
              f"books={[b['book_title'] for b in e['books']]}")
    print("->", OUT)


if __name__ == "__main__":
    build()
