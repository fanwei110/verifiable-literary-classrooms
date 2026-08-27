"""扫描返修产物中的密钥副本；不读取或比对 OpenRouter 原始密钥。"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
DEFAULT_ROOTS = [
    BASE,
    ROOT / "revision_R1",
    ROOT / "第一次提交版本" / "LaTeX_source (1)",
]
TOKEN_PATTERN = re.compile(rb"(?i)(?:sk-|or-v1-)[A-Za-z0-9_-]{16,}")


def matches_blob(blob: bytes, deepseek_key: bytes) -> bool:
    """同时检查本次实际密钥和通用 token 外形。"""
    return (bool(deepseek_key) and deepseek_key in blob) or bool(
        TOKEN_PATTERN.search(blob)
    )


def scan_file(path: Path, deepseek_key: bytes) -> list[str]:
    """扫描普通文件及 zip 内部文本；只返回文件名，不输出命中内容。"""
    hits: list[str] = []
    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if member.file_size > 25 * 1024 * 1024:
                        continue
                    blob = archive.read(member)
                    if matches_blob(blob, deepseek_key):
                        hits.append(f"{path}!{member.filename}")
        elif path.stat().st_size <= 25 * 1024 * 1024:
            if matches_blob(path.read_bytes(), deepseek_key):
                hits.append(str(path))
    except (OSError, zipfile.BadZipFile, RuntimeError):
        hits.append(f"UNREADABLE:{path}")
    return hits


def main() -> None:
    """命令行入口；DeepSeek 密钥仅在内存中用于精确匹配。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--deepseek-key-file", type=Path, required=True)
    parser.add_argument("--root", type=Path, action="append")
    args = parser.parse_args()
    deepseek_key = (
        args.deepseek_key_file.read_text(encoding="utf-8-sig").strip().encode()
    )
    roots = args.root or DEFAULT_ROOTS
    hits: list[str] = []
    seen: set[Path] = set()
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path in seen or "__pycache__" in path.parts:
                continue
            seen.add(path)
            hits.extend(scan_file(path, deepseek_key))
    if hits:
        print(f"密钥扫描失败：{len(hits)} 个文件或压缩包成员命中")
        for hit in hits:
            print(hit)
        raise SystemExit(1)
    print(f"密钥扫描通过：扫描 {len(seen)} 个文件，零命中")


if __name__ == "__main__":
    main()
