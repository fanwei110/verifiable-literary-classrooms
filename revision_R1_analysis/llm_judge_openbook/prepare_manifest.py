"""冻结 R1.7 的 60×3 提示清单与跨六部语料 dense-RAG 证据。"""

from __future__ import annotations

import csv
import importlib.metadata
import json
import os
import platform
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from experiment_core import (  # noqa: E402
    CONDITIONS,
    build_prompt,
    canonical_json,
    prompt_shell,
    sha256_file,
    sha256_text,
    utc_now,
)


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
FORM_PATH = ROOT / "人研究材料包" / "severity_rating_form.csv"
PRIVATE_KEY_PATH = ROOT / "人研究材料包" / "severity_key_HIDDEN.csv"
PUBLIC_KEY_PATH = ROOT / "journal_extension" / "llm_judge_foil" / "foil_key.csv"
TASK_DIR = ROOT / "tasks"
CORPUS_INDEX_PATH = ROOT / "corpus" / "processed" / "corpus_index.json"
OUT_PATH = BASE / "inputs" / "prompts_manifest.jsonl"
META_PATH = BASE / "inputs" / "manifest_metadata.json"

FORM_COLUMNS = {
    "quote": "模型给出的引文",
    "author": "模型标注的作者",
    "work": "模型标注的作品",
    "locator": "模型标注的出处",
    "speaker": "模型标注的说话人",
}


def normalize_space(text: str) -> str:
    """统一空白与大小写，用于审计检索命中而不改变模型输入。"""
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def segment(text: str, seg_chars: int = 700, overlap: int = 150) -> list[str]:
    """严格复用既有 dense-RAG 的段落聚合和字符重叠规则。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    segments: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) > seg_chars and current:
            segments.append(current)
            current = current[-overlap:] + "\n\n" + paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        segments.append(current)
    return segments


def read_csv(path: Path) -> list[dict[str, str]]:
    """读取带 BOM 的研究 CSV，并保留原始文本字段。"""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_inputs() -> (
    tuple[list[dict[str, str]], dict[str, dict[str, str]], dict[str, dict[str, str]]]
):
    """读取盲表与两份真值键，并验证二者没有版本漂移。"""
    forms = read_csv(FORM_PATH)
    private_rows = read_csv(PRIVATE_KEY_PATH)
    public_rows = read_csv(PUBLIC_KEY_PATH)
    private = {row["item_id"]: row for row in private_rows}
    public = {row["item_id"]: row for row in public_rows}
    form_ids = {row["item_id"] for row in forms}
    if len(forms) != 60 or len(form_ids) != 60:
        raise ValueError("盲评表必须恰含 60 个唯一题项")
    if form_ids != set(private) or form_ids != set(public):
        raise ValueError("盲评表、隐藏键与公开 foil_key 的 item_id 不一致")
    for item_id in form_ids:
        strict_private = private[item_id]["auto_strict"].strip().lower()
        strict_public = public[item_id]["auto_strict"].strip().lower()
        class_private = private[item_id]["auto_error_class"].strip()
        class_public = public[item_id]["auto_error_class"].strip()
        if strict_private != strict_public or class_private != class_public:
            raise ValueError(f"{item_id} 的两份真值键不一致")
    return forms, private, public


def build_global_index(
    corpus: dict[str, Any]
) -> tuple[list[dict[str, Any]], np.ndarray, str]:
    """对六部冻结语料统一编码，允许检出跨作品误归属。"""
    from sentence_transformers import SentenceTransformer

    records: list[dict[str, Any]] = []
    for work_id in sorted(corpus):
        work = corpus[work_id]
        for segment_index, text in enumerate(segment(work["clean_text"])):
            records.append(
                {
                    "work_id": work_id,
                    "work": work["title"],
                    "author": work["author"],
                    "segment_index": segment_index,
                    "text": text,
                    "text_sha256": sha256_text(text),
                }
            )
    encoder_name = "all-MiniLM-L6-v2"
    encoder = SentenceTransformer(encoder_name)
    embeddings = encoder.encode(
        [record["text"] for record in records],
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    return records, np.asarray(embeddings, dtype=np.float32), encoder_name


def claim_from_form(row: dict[str, str]) -> dict[str, str]:
    """把中文盲表字段映射到模型共用的稳定英文键。"""
    return {name: row[column].strip() for name, column in FORM_COLUMNS.items()}


def evidence_block(excerpts: list[dict[str, str]]) -> str:
    """以统一格式插入证据；条件名称不会出现在模型可见文本中。"""
    if not excerpts:
        return "[No reference excerpts supplied.]"
    blocks = []
    for index, excerpt in enumerate(excerpts, 1):
        metadata = f"author={excerpt['author']}; work={excerpt['work']}"
        if excerpt.get("locator"):
            metadata += f"; locator={excerpt['locator']}"
        if excerpt.get("speaker"):
            metadata += f"; speaker_or_narrator={excerpt['speaker']}"
        blocks.append(
            f"[Reference excerpt {index}]\nSource metadata: {metadata}\n{excerpt['text']}"
        )
    return "\n\n".join(blocks)


def query_text(claim: dict[str, str]) -> str:
    """查询同时包含引文和归属字段，避免按声称作品预先限库。"""
    return (
        f"Claimed quotation: {claim['quote']}\n"
        f"Author: {claim['author']}\nWork: {claim['work']}\n"
        f"Locator: {claim['locator']}\nSpeaker or narrator: {claim['speaker']}"
    )


def main() -> None:
    """生成并冻结 180 条模型无关提示。"""
    forms, private, public = load_inputs()
    corpus = json.loads(CORPUS_INDEX_PATH.read_text(encoding="utf-8"))
    if len(corpus) != 6:
        raise ValueError(f"冻结语料应为 6 部，实际为 {len(corpus)}")

    segment_records, segment_embeddings, encoder_name = build_global_index(corpus)
    from sentence_transformers import SentenceTransformer

    encoder = SentenceTransformer(encoder_name)
    claims = [claim_from_form(row) for row in forms]
    queries = [query_text(claim) for claim in claims]
    query_embeddings = encoder.encode(
        queries,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,
    ).astype(np.float32)

    tasks: dict[str, dict[str, Any]] = {}
    manifest: list[dict[str, Any]] = []
    shells: dict[str, set[str]] = defaultdict(set)
    for form, claim, query_embedding in zip(forms, claims, query_embeddings):
        item_id = form["item_id"]
        task_id = private[item_id]["task_id"]
        if task_id not in tasks:
            tasks[task_id] = yaml.safe_load(
                (TASK_DIR / f"{task_id}.yaml").read_text(encoding="utf-8")
            )
        task = tasks[task_id]

        similarities = segment_embeddings @ query_embedding
        ranking = np.argsort(-similarities)[:3]
        rag_excerpts: list[dict[str, str]] = []
        retrieval_rows: list[dict[str, Any]] = []
        claim_norm = normalize_space(claim["quote"])
        expected_quotes = [
            normalize_space(ev.get("quote", ""))
            for ev in task.get("expected_evidence", [])
        ]
        for rank, segment_position in enumerate(ranking, 1):
            segment_row = segment_records[int(segment_position)]
            segment_norm = normalize_space(segment_row["text"])
            claim_hit = bool(claim_norm and claim_norm in segment_norm)
            task_gold_hit = any(q and q in segment_norm for q in expected_quotes)
            rag_excerpts.append(
                {
                    "author": segment_row["author"],
                    "work": segment_row["work"],
                    "text": segment_row["text"],
                }
            )
            retrieval_rows.append(
                {
                    "rank": rank,
                    "work_id": segment_row["work_id"],
                    "segment_index": segment_row["segment_index"],
                    "score": round(float(similarities[int(segment_position)]), 8),
                    "text_sha256": segment_row["text_sha256"],
                    "claim_exact_hit": claim_hit,
                    "task_gold_hit": task_gold_hit,
                }
            )

        gold_excerpts = []
        for expected in task.get("expected_evidence", []):
            gold_excerpts.append(
                {
                    "author": task["author"],
                    "work": task["work_title"],
                    "locator": str(expected.get("locator", "")),
                    "speaker": str(expected.get("speaker_or_narrator", "")),
                    "text": str(expected.get("source_window", "")),
                }
            )

        condition_payloads: dict[str, tuple[list[dict[str, str]], dict[str, Any]]] = {
            "closed": ([], {}),
            "rag_top3": (
                rag_excerpts,
                {
                    "retrieval": retrieval_rows,
                    "claim_exact_hit_at_3": any(
                        r["claim_exact_hit"] for r in retrieval_rows
                    ),
                    "task_gold_hit_at_3": any(
                        r["task_gold_hit"] for r in retrieval_rows
                    ),
                    "diagnostic_hit_at_3": any(
                        r["claim_exact_hit"] or r["task_gold_hit"]
                        for r in retrieval_rows
                    ),
                },
            ),
            "gold_reference": (
                gold_excerpts,
                {
                    "gold_excerpt_sha256": [
                        sha256_text(excerpt["text"]) for excerpt in gold_excerpts
                    ]
                },
            ),
        }
        for condition in CONDITIONS:
            excerpts, audit = condition_payloads[condition]
            prompt = build_prompt(claim, evidence_block(excerpts))
            shells[item_id].add(sha256_text(prompt_shell(prompt)))
            dispatch_key = sha256_text(f"20260823|{item_id}|{condition}")
            manifest.append(
                {
                    "item_id": item_id,
                    "condition": condition,
                    "dispatch_key": dispatch_key,
                    "prompt": prompt,
                    "prompt_sha256": sha256_text(prompt),
                    "evidence_count": len(excerpts),
                    **audit,
                }
            )

    if any(len(item_shells) != 1 for item_shells in shells.values()):
        raise ValueError("同一题项的三条件除证据块之外还存在提示差异")
    if len(manifest) != 180:
        raise ValueError(f"提示应为 180 条，实际为 {len(manifest)}")
    pairs = {(row["item_id"], row["condition"]) for row in manifest}
    if len(pairs) != 180:
        raise ValueError("提示清单存在重复 item_id×condition")
    counts = Counter(row["condition"] for row in manifest)
    if counts != Counter({condition: 60 for condition in CONDITIONS}):
        raise ValueError(f"三条件数量异常：{counts}")

    manifest.sort(key=lambda row: row["dispatch_key"])
    for dispatch_order, row in enumerate(manifest, 1):
        row["dispatch_order"] = dispatch_order
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in manifest
        ),
        encoding="utf-8",
    )

    metadata = {
        "created_utc": utc_now(),
        "design": "60 items × 3 evidence conditions × 2 independent judges",
        "item_count": 60,
        "prompt_count": 180,
        "job_count": 360,
        "condition_counts": dict(counts),
        "truth_distribution": dict(
            Counter(
                public[item_id]["auto_error_class"] or "correct" for item_id in public
            )
        ),
        "retrieval": {
            "encoder": encoder_name,
            "scope": "all six frozen corpora",
            "segment_chars": 700,
            "overlap_chars": 150,
            "top_k": 3,
            "segment_count": len(segment_records),
        },
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pyyaml": yaml.__version__,
            "sentence_transformers": importlib.metadata.version(
                "sentence-transformers"
            ),
            "torch": importlib.metadata.version("torch"),
        },
        "input_sha256": {
            "severity_rating_form.csv": sha256_file(FORM_PATH),
            "severity_key_HIDDEN.csv": sha256_file(PRIVATE_KEY_PATH),
            "foil_key.csv": sha256_file(PUBLIC_KEY_PATH),
            "corpus_index.json": sha256_file(CORPUS_INDEX_PATH),
            **{
                f"tasks/{task_id}.yaml": sha256_file(TASK_DIR / f"{task_id}.yaml")
                for task_id in sorted(tasks)
            },
        },
        "manifest_sha256": sha256_file(OUT_PATH),
        "dispatch_seed_material": "20260823|item_id|condition",
        "prompt_schema_sha256": sha256_text(canonical_json({"conditions": CONDITIONS})),
    }
    META_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"冻结提示：{OUT_PATH}")
    print(f"题项=60，提示=180，正式任务=360，跨库片段={len(segment_records)}")
    print(f"manifest_sha256={metadata['manifest_sha256']}")


if __name__ == "__main__":
    main()
