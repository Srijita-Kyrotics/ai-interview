"""Write the hand-authored real test cases into shared/coding_questions.json.

Replaces the placeholder ``testCases``/``examples`` for questions 38-196 with the
verified cases in backend/scripts/coding_test_cases_data.py and regenerates the
worked examples from them (flattened to a single line for display).

Run from the repository root:
    python backend/scripts/populate_coding_test_cases.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coding_test_cases_data import TEST_CASES

ROOT = Path(__file__).resolve().parent.parent.parent
QUESTIONS_FILE = ROOT / "shared" / "coding_questions.json"

MAX_EXAMPLES = 3


def fmt(value: str) -> str:
    return value.replace("\n", " ").strip()


def main() -> None:
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    updated = 0
    for question in questions:
        qid = question["id"]
        if qid not in TEST_CASES:
            continue
        cases = [
            {"input": inp, "expected": exp}
            for inp, exp in TEST_CASES[qid]
        ]
        question["testCases"] = cases
        examples = []
        for case in cases:
            if len(examples) >= MAX_EXAMPLES:
                break
            expected = str(case["expected"])
            if not expected:
                continue
            examples.append(
                f"Input: {fmt(str(case['input']))}  =>  Output: {fmt(expected)}"
            )
        question["examples"] = examples
        updated += 1

    for question in questions:
        if question["id"] == 196:
            question["statement"] = (
                "Count the number of distinct pairs (num1, num2) where both num1 and "
                "num2 are present in the array and the total number of set bits in "
                "(num1 OR num2) plus the number of set bits in (num1 AND num2) is at "
                "least k."
            )

    QUESTIONS_FILE.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Populated real test cases and examples for {updated} questions.")


if __name__ == "__main__":
    main()
