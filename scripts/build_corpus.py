"""Download, clean, segment, and freeze the source corpus.

The script intentionally writes deterministic outputs from public-domain
Project Gutenberg plain-text sources. It may be re-run; unchanged raw files
and processed files should retain identical hashes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "corpus" / "raw"
PROCESSED_DIR = ROOT / "corpus" / "processed"


@dataclass(frozen=True)
class Work:
    work_id: str
    title: str
    author: str
    gutenberg_id: int
    url: str
    genre: str
    locator_mode: str
    edition_note: str


WORKS = [
    Work(
        "hamlet",
        "Hamlet",
        "William Shakespeare",
        1524,
        "https://www.gutenberg.org/cache/epub/1524/pg1524.txt",
        "drama",
        "act_scene",
        "Project Gutenberg plain text",
    ),
    Work(
        "macbeth",
        "Macbeth",
        "William Shakespeare",
        1533,
        "https://www.gutenberg.org/cache/epub/1533/pg1533.txt",
        "drama",
        "act_scene",
        "Project Gutenberg plain text",
    ),
    Work(
        "pride_prejudice",
        "Pride and Prejudice",
        "Jane Austen",
        1342,
        "https://www.gutenberg.org/cache/epub/1342/pg1342.txt",
        "novel",
        "chapter",
        "Project Gutenberg plain text",
    ),
    Work(
        "tale_two_cities",
        "A Tale of Two Cities",
        "Charles Dickens",
        98,
        "https://www.gutenberg.org/cache/epub/98/pg98.txt",
        "novel",
        "book_chapter",
        "Project Gutenberg plain text",
    ),
    Work(
        "paradise_lost",
        "Paradise Lost",
        "John Milton",
        20,
        "https://www.gutenberg.org/cache/epub/20/pg20.txt",
        "poem",
        "book",
        "Project Gutenberg plain text",
    ),
    Work(
        "odyssey_butler",
        "The Odyssey",
        "Homer",
        1727,
        "https://www.gutenberg.org/cache/epub/1727/pg1727.txt",
        "epic_translation",
        "book",
        "Project Gutenberg Samuel Butler translation",
    ),
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def download(work: Work) -> bytes:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{work.work_id}.txt"
    if path.exists():
        return path.read_bytes()
    response = requests.get(work.url, timeout=60)
    response.raise_for_status()
    data = response.content
    path.write_bytes(data)
    return data


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def strip_gutenberg(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    start_match = re.search(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I | re.S)
    end_match = re.search(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*", text, re.I | re.S)
    if start_match:
        text = text[start_match.end() :]
    if end_match:
        text = text[: end_match.start()]
    return text.strip() + "\n"


def roman_to_int(value: str) -> int | None:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev = 0
    for ch in reversed(value.upper()):
        cur = values.get(ch)
        if cur is None:
            return None
        if cur < prev:
            total -= cur
        else:
            total += cur
            prev = cur
    return total


def segment_drama(text: str) -> list[dict]:
    lines = text.splitlines()
    segments: list[dict] = []
    cur_act = ""
    cur_scene = ""
    cur_start = 0
    cur_lines: list[str] = []
    char_pos = 0

    def flush(end_pos: int) -> None:
        nonlocal cur_lines, cur_start
        body = "\n".join(cur_lines).strip()
        if cur_act and cur_scene and body:
            segments.append(
                {
                    "locator": f"{cur_act}, {cur_scene}",
                    "start_char": cur_start,
                    "end_char": end_pos,
                    "text": body,
                }
            )
        cur_lines = []
        cur_start = end_pos

    for line in lines:
        raw_line = line
        stripped = line.strip()
        act = re.match(r"^ACT\s+([IVXLCDM]+)\.?", stripped, re.I)
        scene = re.match(r"^SCENE\s+([IVXLCDM]+)\.?", stripped, re.I)
        if act:
            flush(char_pos)
            cur_act = f"Act {act.group(1).upper()}"
            cur_scene = ""
            cur_start = char_pos
        elif scene:
            flush(char_pos)
            cur_scene = f"Scene {scene.group(1).upper()}"
            cur_start = char_pos
        cur_lines.append(raw_line)
        char_pos += len(raw_line) + 1
    flush(len(text))
    return segments or segment_chunks(text)


def segment_chapters(text: str) -> list[dict]:
    pattern = re.compile(r"(?m)^(CHAPTER\s+[IVXLCDM0-9]+\.?.*)$")
    matches = list(pattern.finditer(text))
    if not matches:
        return segment_chunks(text)
    segments = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        heading = match.group(1).strip().rstrip(".")
        segments.append(
            {
                "locator": heading.title(),
                "start_char": start,
                "end_char": end,
                "text": text[start:end].strip(),
            }
        )
    return segments


def segment_books(text: str) -> list[dict]:
    pattern = re.compile(r"(?m)^(BOOK\s+[IVXLCDM0-9]+\.?.*)$")
    matches = list(pattern.finditer(text))
    if not matches:
        return segment_chunks(text)
    segments = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        heading = match.group(1).strip().rstrip(".")
        segments.append(
            {
                "locator": heading.title(),
                "start_char": start,
                "end_char": end,
                "text": text[start:end].strip(),
            }
        )
    return segments


def segment_tale(text: str) -> list[dict]:
    pattern = re.compile(r"(?m)^((?:BOOK\s+THE\s+\w+|CHAPTER\s+[IVXLCDM0-9]+)\.?.*)$")
    matches = list(pattern.finditer(text))
    if not matches:
        return segment_chapters(text)
    segments = []
    current_book = ""
    for idx, match in enumerate(matches):
        heading = match.group(1).strip().rstrip(".")
        if heading.upper().startswith("BOOK THE"):
            current_book = heading.title()
            continue
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        locator = f"{current_book}, {heading.title()}" if current_book else heading.title()
        segments.append(
            {
                "locator": locator,
                "start_char": start,
                "end_char": end,
                "text": text[start:end].strip(),
            }
        )
    return segments or segment_chapters(text)


def segment_chunks(text: str, size: int = 5000) -> list[dict]:
    return [
        {
            "locator": f"Chunk {i // size + 1}",
            "start_char": i,
            "end_char": min(i + size, len(text)),
            "text": text[i : i + size].strip(),
        }
        for i in range(0, len(text), size)
        if text[i : i + size].strip()
    ]


def segment(work: Work, text: str) -> list[dict]:
    if work.locator_mode == "act_scene":
        return segment_drama(text)
    if work.locator_mode == "chapter":
        return segment_chapters(text)
    if work.locator_mode == "book_chapter":
        return segment_tale(text)
    if work.locator_mode == "book":
        return segment_books(text)
    return segment_chunks(text)


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    corpus_index = {}
    hash_lines = []

    for work in WORKS:
        raw_bytes = download(work)
        raw_hash = sha256_bytes(raw_bytes)
        raw_text = decode_text(raw_bytes)
        clean_text = strip_gutenberg(raw_text)
        segments = segment(work, clean_text)
        item = {
            "work_id": work.work_id,
            "title": work.title,
            "author": work.author,
            "gutenberg_id": work.gutenberg_id,
            "source_url": work.url,
            "download_date": date.today().isoformat(),
            "edition_note": work.edition_note,
            "genre": work.genre,
            "locator_mode": work.locator_mode,
            "raw_sha256": raw_hash,
            "clean_sha256": sha256_text(clean_text),
            "clean_text": clean_text,
            "segments": segments,
        }
        corpus_index[work.work_id] = item
        (PROCESSED_DIR / f"{work.work_id}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        hash_lines.append(f"{raw_hash}  raw/{work.work_id}.txt")
        hash_lines.append(f"{item['clean_sha256']}  processed/{work.work_id}.json.clean_text")
        manifest_rows.append(
            {
                "work_id": work.work_id,
                "title": work.title,
                "author": work.author,
                "gutenberg_id": work.gutenberg_id,
                "source_url": work.url,
                "download_date": item["download_date"],
                "edition_note": work.edition_note,
                "genre": work.genre,
                "locator_mode": work.locator_mode,
                "raw_sha256": raw_hash,
                "clean_sha256": item["clean_sha256"],
                "segments": len(segments),
            }
        )

    (PROCESSED_DIR / "corpus_index.json").write_text(
        json.dumps(corpus_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (ROOT / "corpus" / "corpus_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)
    (ROOT / "corpus" / "SHA256SUMS.txt").write_text("\n".join(hash_lines) + "\n", encoding="utf-8")
    print(f"wrote {len(WORKS)} works -> {PROCESSED_DIR / 'corpus_index.json'}")


if __name__ == "__main__":
    main()

