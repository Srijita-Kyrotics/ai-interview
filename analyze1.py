import json, re

with open("aptitude.json", "r", encoding="utf-8") as f:
    data = json.load(f)

questions = data["questions"]
by_id = {q["id"]: q for q in questions}

notable = ["quantitative-086", "quantitative-091", "quantitative-149",
           "quantitative-017", "quantitative-077", "quantitative-009",
           "logical-006", "logical-007", "logical-009", "logical-010",
           "logical-017", "logical-018", "logical-019", "logical-020", "logical-021",
           "logical-042", "logical-043", "logical-044", "logical-045", "logical-046",
           "logical-049", "logical-050", "logical-051", "logical-052", "logical-053",
           "logical-066", "logical-188",
           "verbal-027", "verbal-046", "verbal-048", "verbal-049",
           "verbal-050", "verbal-051", "verbal-052", "verbal-053", "verbal-054",
           "verbal-055", "verbal-056", "verbal-057", "verbal-058",
           "verbal-017", "verbal-018", "verbal-019",
           "quantitative-0030", "quantitative-0114", "quantitative-0226",
           "quantitative-0303", "quantitative-0306", "quantitative-0314",
           "quantitative-0403", "quantitative-0410", "quantitative-0484",
           "quantitative-0269", "logical-0026",
           "quantitative-0146", "quantitative-0147"]

for qid in notable:
    q = by_id.get(qid)
    if q:
        print("=== [{}] (sec: {}) ===".format(qid, q["section"]))
        print(q["question"])
        print("Options: " + str(q["options"]))
        print("Correct: " + q["correct"])
        print()
