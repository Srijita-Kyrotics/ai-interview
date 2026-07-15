import json

with open(r'D:\RECRUITMENT_PLATFORM\frontend\public\questions\aptitude.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Category A - bold type
print("=== Category A: 'printed in bold type' ===")
for q in data['questions']:
    if q['id'] == 'verbal-0782':
        print(f"ID: {q['id']}")
        print(f"Question: {q['question']}")
        print(f"Options: {q['options']}")
        print(f"Correct: {q.get('correct')}")
        print()
        break

# Category B - italicised and underlined
print("=== Category B: 'italicised and underlined' ===")
for q in data['questions']:
    if q['id'] == 'verbal-0840':
        print(f"ID: {q['id']}")
        print(f"Question: {q['question']}")
        print(f"Options: {q['options']}")
        print(f"Correct: {q.get('correct')}")
        print()
        break

# Category C - underlined word  
print("=== Category C: 'has an underlined word' ===")
for q in data['questions']:
    if q['id'] == 'logical-0049':
        print(f"ID: {q['id']}")
        print(f"Question: {q['question']}")
        print(f"Options: {q['options']}")
        print(f"Correct: {q.get('correct')}")
        print()
        break
