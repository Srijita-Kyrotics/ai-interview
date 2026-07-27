import json

with open("shared/coding_questions_new.json", encoding="utf-8") as f:
    raw = json.load(f)

STARTER_TEMPLATES = {
    "python": lambda title, func_name: f"# {title}\n# Time Complexity:\n# Space Complexity:\n\ndef {func_name}():\n    pass\n",
    "javascript": lambda title, func_name: f"// {title}\n// Time Complexity:\n// Space Complexity:\n\nfunction {func_name}() {{\n  // Your code here\n}}\n",
    "java": lambda title, func_name: f"// {title}\n// Time Complexity:\n// Space Complexity:\n\npublic class Solution {{\n  public static void {func_name}() {{\n    // Your code here\n  }}\n}}\n",
    "c": lambda title, func_name: f"// {title}\n// Time Complexity:\n// Space Complexity:\n\n#include <stdio.h>\n\nvoid {func_name}() {{\n    // Your code here\n}}\n",
    "csharp": lambda title, func_name: f"// {title}\n// Time Complexity:\n// Space Complexity:\n\nusing System;\n\npublic class Solution {{\n  public static void {func_name}() {{\n    // Your code here\n  }}\n}}\n"
}

def slugify(title):
    parts = title.lower().replace("-", "_").replace(" ", "_").split("_")
    parts = [p for p in parts if p.isalnum()]
    return "_".join(parts[:4])

def transform_example(ex):
    inp = ex.get("input", "").strip()
    out = ex.get("output", "").strip()
    return f"Input: {inp} | Output: {out}"

def transform_test_cases(examples, problem_id):
    tests = []
    for i, ex in enumerate(examples):
        tests.append({
            "input": ex.get("input", ""),
            "expected": ex.get("output", ""),
        })
    return tests

results = []
for i, item in enumerate(raw, 1):
    title = item.get("title", f"Problem {i}")
    problem_id = item.get("problemId", f"PROB_{i:03d}")
    slug = slugify(title)
    statement_parts = []
    if item.get("problem_statement"):
        statement_parts.append(item["problem_statement"])
    if item.get("input_format"):
        statement_parts.append(f"Input: {item['input_format']}")
    if item.get("output_format"):
        statement_parts.append(f"Output: {item['output_format']}")
    if item.get("constraints"):
        statement_parts.append(f"Constraints: {item['constraints']}")
    statement = "\n\n".join(statement_parts) if statement_parts else title

    examples_raw = item.get("examples", [])
    examples_str = [transform_example(ex) for ex in examples_raw]
    test_cases = transform_test_cases(examples_raw, problem_id) if examples_raw else [
        {"input": "", "expected": ""}
    ]

    starter = {}
    for lang, tmpl in STARTER_TEMPLATES.items():
        starter[lang] = tmpl(title, slug)

    results.append({
        "id": i,
        "title": title,
        "statement": statement,
        "difficulty": item.get("difficulty", "Medium"),
        "topic": item.get("topic", ""),
        "tags": item.get("tags", {}),
        "source": item.get("source", ""),
        "timeComplexity": item.get("time_complexity", ""),
        "spaceComplexity": item.get("space_complexity", ""),
        "followUp": item.get("follow_up", ""),
        "starter": starter,
        "examples": examples_str,
        "testCases": test_cases,
    })

with open("shared/coding_questions.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"Transformed {len(results)} problems → shared/coding_questions.json")
