"""Replace placeholder examples with worked examples derived from real test cases.

Coding questions shipped with ``examples: ["Example: see problem statement"]``.
This script derives concrete input -> output examples from each question's real
test cases so candidates can understand the expected behaviour at a glance.

Run from the repository root:
    python backend/scripts/enrich_coding_examples.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
QUESTIONS_FILE = ROOT / "shared" / "coding_questions.json"

MAX_EXAMPLES = 3


def fmt_input(value: str) -> str:
    return value.replace("\n", " ").strip()


def main() -> None:
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    updated = 0
    for question in questions:
        cases = question.get("testCases") or []
        examples = []
        for case in cases:
            if len(examples) >= MAX_EXAMPLES:
                break
            expected = str(case.get("expected", ""))
            if not expected:
                continue
            examples.append(
                f"Input: {fmt_input(str(case.get('input', '')))}  =>  Output: {expected}"
            )
        if not examples:
            continue
        current = question.get("examples")
        if current == ["Example: see problem statement"] or not current:
            question["examples"] = examples
            updated += 1

    QUESTIONS_FILE.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Enriched examples for {updated} questions.")


if __name__ == "__main__":
    main()
