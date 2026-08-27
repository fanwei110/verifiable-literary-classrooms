"""Generate task specs, prompt sets, and adversarial validation cases."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CORPUS_INDEX = ROOT / "corpus" / "processed" / "corpus_index.json"

TASK_DIR = ROOT / "tasks"
PROMPT_DIR = ROOT / "prompts"
HARNESS_DIR = ROOT / "harness"

OUTPUT_CONTRACT = """Return only one valid JSON object with this schema:
{
  "answer": "classroom-facing response",
  "evidence": [
    {
      "quote": "verbatim quoted text",
      "author": "claimed author",
      "work": "claimed work",
      "locator": "chapter / act-scene / book-line window",
      "speaker_or_narrator": "claimed speaker or narrator",
      "use_in_answer": "one sentence explaining what this quote supports"
    }
  ],
  "limits": "any uncertainty or version note"
}
Do not use Markdown fences. Do not include text outside the JSON object."""


BLUEPRINTS = [
    {
        "tgu_id": "TGU1",
        "work_id": "hamlet",
        "themes": ["hesitation", "mortality", "performance"],
        "quotes": [
            {
                "seed": "To be, or not to be: that is the question",
                "speaker": "Hamlet",
                "theme": "mortality and hesitation",
            },
            {
                "seed": "The play's the thing Wherein I'll catch the conscience of the king",
                "speaker": "Hamlet",
                "theme": "performance as investigation",
            },
            {
                "seed": "Something is rotten in the state of Denmark",
                "speaker": "Marcellus",
                "theme": "political corruption",
            },
        ],
    },
    {
        "tgu_id": "TGU2",
        "work_id": "macbeth",
        "themes": ["ambition", "prophecy", "guilt"],
        "quotes": [
            {
                "seed": "Is this a dagger which I see before me",
                "speaker": "Macbeth",
                "theme": "ambition and hallucination",
            },
            {
                "seed": "Out, damned spot! out, I say",
                "speaker": "Lady Macbeth",
                "theme": "guilt",
            },
            {
                "seed": "Fair is foul, and foul is fair",
                "speaker": "Witches",
                "theme": "moral inversion",
            },
        ],
    },
    {
        "tgu_id": "TGU3",
        "work_id": "pride_prejudice",
        "themes": ["first impressions", "class", "marriage"],
        "quotes": [
            {
                "seed": "It is a truth universally acknowledged",
                "speaker": "Narrator",
                "theme": "marriage market irony",
            },
            {
                "seed": "I dearly love a laugh",
                "speaker": "Elizabeth Bennet",
                "theme": "wit and judgment",
            },
            {
                "seed": "Till this moment I never knew myself",
                "speaker": "Elizabeth Bennet",
                "theme": "self-knowledge",
            },
        ],
    },
    {
        "tgu_id": "TGU4",
        "work_id": "tale_two_cities",
        "themes": ["revolution", "sacrifice", "doubling"],
        "quotes": [
            {
                "seed": "It was the best of times, it was the worst of times",
                "speaker": "Narrator",
                "theme": "historical contradiction",
            },
            {
                "seed": "It is a far, far better thing that I do",
                "speaker": "Sydney Carton",
                "theme": "sacrifice",
            },
            {
                "seed": "Recalled to Life",
                "speaker": "Narrator",
                "theme": "resurrection and return",
            },
        ],
    },
    {
        "tgu_id": "TGU5",
        "work_id": "paradise_lost",
        "themes": ["temptation", "free will", "rebellion"],
        "quotes": [
            {
                "seed": "Of Mans First Disobedience and the Fruit",
                "speaker": "Narrator",
                "theme": "fall and disobedience",
            },
            {
                "seed": "Better to reign in Hell then serve in Heav",
                "speaker": "Satan",
                "theme": "rebellion",
            },
            {
                "seed": "The mind is its own place and in it self",
                "speaker": "Satan",
                "theme": "self-fashioning",
            },
        ],
    },
    {
        "tgu_id": "TGU6",
        "work_id": "odyssey_butler",
        "themes": ["homecoming", "identity", "hospitality"],
        "quotes": [
            {
                "seed": "Tell me, O Muse, of that ingenious hero",
                "speaker": "Narrator",
                "theme": "wandering and story",
            },
            {
                "seed": "My name is Noman",
                "speaker": "Ulysses",
                "theme": "identity and deception",
            },
            {
                "seed": "Stranger, you appear to be a sensible",
                "speaker": "Nausicaa",
                "theme": "hospitality",
            },
        ],
    },
]


def load_corpus() -> dict:
    if not CORPUS_INDEX.exists():
        raise SystemExit("corpus_index.json not found; run scripts/build_corpus.py first")
    return json.loads(CORPUS_INDEX.read_text(encoding="utf-8"))


def seed_pattern(seed: str) -> re.Pattern[str]:
    words = re.findall(r"[A-Za-z0-9]+", seed)
    if not words:
        raise ValueError(seed)
    pattern = r"\b" + r"[\W_]+".join(re.escape(word) for word in words) + r"\b"
    return re.compile(pattern, re.I)


def find_quote(work: dict, quote_spec: dict) -> dict:
    text = work["clean_text"]
    match = seed_pattern(quote_spec["seed"]).search(text)
    if not match:
        raise RuntimeError(f"quote seed not found in {work['work_id']}: {quote_spec['seed']}")
    quote = re.sub(r"\s+", " ", match.group(0)).strip()
    segment = None
    for candidate in work["segments"]:
        if candidate["start_char"] <= match.start() <= candidate["end_char"]:
            segment = candidate
            break
    if segment is None:
        segment = work["segments"][0]
    start = max(0, match.start() - 900)
    end = min(len(text), match.end() + 900)
    window = text[start:end].strip()
    return {
        "quote": quote,
        "speaker_or_narrator": quote_spec["speaker"],
        "theme": quote_spec["theme"],
        "locator": segment["locator"],
        "source_window": re.sub(r"\n{3,}", "\n\n", window),
    }


def task_prompt_base(task: dict) -> str:
    work = task["work_title"]
    theme = task["theme"]
    if task["task_type"] == "T1":
        return (
            f"In a live classical-literature class, provide an exact quotation from "
            f"{work} that helps explain {theme}. Include the source."
        )
    if task["task_type"] == "T2":
        q = task["expected_evidence"][0]["quote"]
        return (
            f"A student asks where this line comes from and who says it: "
            f"\"{q}\". Answer with attribution and brief context."
        )
    return (
        f"Give a 150-200 word mini-lesson on {theme} in {work}, using exactly "
        f"{task['required_evidence_count']} direct textual quotations as evidence."
    )


def evidence_instruction(task: dict) -> str:
    return (
        "For every evidence record, quote only words you can attribute. Fill "
        "`author`, `work`, `locator`, `speaker_or_narrator`, and `use_in_answer`. "
        f"Use exactly {task['required_evidence_count']} evidence record(s)."
    )


def write_prompt(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def make_prompts(task: dict) -> None:
    base = task_prompt_base(task)
    contract = OUTPUT_CONTRACT
    source_block = "\n\n".join(
        f"[Source window {idx + 1}]\n{ev['source_window']}"
        for idx, ev in enumerate(task["expected_evidence"])
    )

    t = task["task_id"]
    write_prompt(
        PROMPT_DIR / "C1_simulated" / f"{t}_A.md",
        f"{base}\n\n{contract}",
    )
    write_prompt(
        PROMPT_DIR / "C1_simulated" / f"{t}_B.md",
        f"During class discussion, a student presses for textual proof. {base}\n\n{contract}",
    )
    write_prompt(
        PROMPT_DIR / "C2_structured" / f"{t}.md",
        f"{base}\n\n{evidence_instruction(task)}\n\n{contract}",
    )
    write_prompt(
        PROMPT_DIR / "C3_grounded" / f"{t}_A.md",
        f"{base}\n\nFrozen source excerpt(s):\n{source_block}\n\n{contract}",
    )
    write_prompt(
        PROMPT_DIR / "C3_grounded" / f"{t}_B.md",
        f"During class discussion, a student presses for textual proof. {base}\n\n"
        f"Frozen source excerpt(s):\n{source_block}\n\n{contract}",
    )
    write_prompt(
        PROMPT_DIR / "C4_tgu" / f"{t}.md",
        f"{base}\n\nFrozen source excerpt(s):\n{source_block}\n\n"
        f"{evidence_instruction(task)}\nOnly use quotations from the frozen source excerpt(s). "
        "If the excerpt does not support a claim, say so in `limits`.\n\n"
        f"{contract}",
    )


def json_completion(task: dict, evidence: list[dict], limits: str = "") -> str:
    return json.dumps(
        {
            "answer": "This classroom answer uses the listed textual evidence.",
            "evidence": [
                {
                    "quote": ev["quote"],
                    "author": ev.get("author", task["author"]),
                    "work": ev.get("work", task["work_title"]),
                    "locator": ev.get("locator", ev["locator"]),
                    "speaker_or_narrator": ev.get("speaker_or_narrator", ev["speaker_or_narrator"]),
                    "use_in_answer": f"This quotation supports {ev['theme']}.",
                }
                for ev in evidence
            ],
            "limits": limits,
        },
        ensure_ascii=False,
    )


def make_adversarial(tasks: list[dict]) -> None:
    cases = []
    # 20 correct-but-format-hostile cases.
    for i in range(1, 21):
        task = tasks[(i - 1) % len(tasks)]
        text = json_completion(task, task["expected_evidence"])
        if i % 4 == 0:
            text = "```json\n" + text + "\n```"
        elif i % 4 == 1:
            text = "\n" + json.dumps(json.loads(text), ensure_ascii=False, indent=2) + "\n"
        elif i % 4 == 2:
            text = text.replace(task["work_title"], task["work_title"].upper())
        else:
            text = "Here is the JSON:\n" + text
        cases.append(
            {
                "case_id": f"c{i:02d}",
                "task_id": task["task_id"],
                "condition": "C4",
                "expected_bucket": "strict_correct",
                "completion": text,
            }
        )

    def altered(task: dict, **change: str) -> list[dict]:
        evs = [dict(ev) for ev in task["expected_evidence"]]
        evs[0].update(change)
        return evs

    error_builders = [
        ("fabricated_quotation", lambda task: altered(task, quote="The silver moon instructs the scholar's lonely heart")),
        ("misattribution", lambda task: altered(task, author="Wrong Author")),
        ("misattribution", lambda task: altered(task, work="Wrong Work")),
        ("context_displacement", lambda task: altered(task, locator="Wrong Locator")),
        ("context_displacement", lambda task: altered(task, speaker_or_narrator="Wrong Speaker")),
        (
            "version_drift",
            lambda task: altered(
                task,
                quote=task["expected_evidence"][0]["quote"].replace(",", "").replace(";", "") + " paraphrased",
            ),
        ),
        ("format_failure", lambda task: []),
    ]

    for j in range(20):
        task = tasks[j % len(tasks)]
        expected_error, builder = error_builders[j % len(error_builders)]
        evs = builder(task)
        if expected_error == "format_failure":
            completion = "This answer has no JSON evidence record."
        else:
            records = []
            for ev in evs:
                records.append(
                    {
                        "quote": ev["quote"],
                        "author": ev.get("author", task["author"]),
                        "work": ev.get("work", task["work_title"]),
                        "locator": ev.get("locator", task["expected_evidence"][0]["locator"]),
                        "speaker_or_narrator": ev.get(
                            "speaker_or_narrator",
                            task["expected_evidence"][0]["speaker_or_narrator"],
                        ),
                        "use_in_answer": "This quotation supports the teaching point.",
                    }
                )
            completion = json.dumps(
                {"answer": "A flawed answer.", "evidence": records, "limits": ""},
                ensure_ascii=False,
            )
        cases.append(
            {
                "case_id": f"p{j + 1:02d}",
                "task_id": task["task_id"],
                "condition": "C4",
                "expected_bucket": "wrong" if expected_error != "format_failure" else "format_failure",
                "expected_error_class_candidate": expected_error,
                "completion": completion,
            }
        )

    out = HARNESS_DIR / "adversarial_cases.jsonl"
    out.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")


def main() -> None:
    corpus = load_corpus()
    tasks = []
    for bp_index, bp in enumerate(BLUEPRINTS, start=1):
        work = corpus[bp["work_id"]]
        found = [find_quote(work, q) for q in bp["quotes"]]
        tgu_meta = {
            "tgu_id": bp["tgu_id"],
            "work_id": bp["work_id"],
            "work_title": work["title"],
            "author": work["author"],
            "genre": work["genre"],
            "edition_note": work["edition_note"],
            "source_url": work["source_url"],
        }
        task_specs = [
            ("T1", "quotation_retrieval", [found[0]], found[0]["theme"]),
            ("T2", "attribution_context", [found[1]], found[1]["theme"]),
            ("T3", "grounded_mini_lesson", [found[0], found[2]], ", ".join(bp["themes"])),
        ]
        for suffix, task_type, evidence, theme in task_specs:
            task_id = f"{bp['tgu_id']}_{suffix}"
            task = {
                "task_id": task_id,
                **tgu_meta,
                "task_type": suffix,
                "task_type_label": task_type,
                "theme": theme,
                "required_evidence_count": len(evidence),
                "expected_evidence": evidence,
                "strict_rules": {
                    "quote_must_match_frozen_corpus": True,
                    "author_work_locator_speaker_required": True,
                    "grounded_conditions_must_use_source_window": True,
                },
            }
            (TASK_DIR / f"{task_id}.yaml").write_text(
                yaml.safe_dump(task, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            make_prompts(task)
            tasks.append(task)

    make_adversarial(tasks)
    print(f"wrote {len(tasks)} tasks, prompts, and 40 adversarial cases")


if __name__ == "__main__":
    main()
