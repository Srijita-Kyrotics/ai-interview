import json

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

# Check spotting errors questions
spotting = [q for q in questions if q.get('topic') == 'Spotting Errors' and q.get('section') == 'verbal']
print(f'Spotting Errors questions: {len(spotting)}')
for q in spotting[:5]:
    print(f'\n[{q["id"]}]')
    print(f'  Question: {q["question"]}')
    print(f'  Options: {q["options"]}')
    print(f'  Correct: {q.get("correct")}')

print('\n\n--- Sentence Correction (highlighted) ---')
sc = [q for q in questions if q.get('topic') == 'Sentence Correction' and q.get('section') == 'verbal']
print(f'Sentence Correction questions: {len(sc)}')
for q in sc[:3]:
    print(f'\n[{q["id"]}]')
    print(f'  Question: {q["question"][:200]}')
    print(f'  Options: {q["options"]}')
    print(f'  Correct: {q.get("correct")}')

print('\n\n--- Sentence Improvement ---')
si = [q for q in questions if q.get('topic') == 'Sentence Improvement' and q.get('section') == 'verbal']
print(f'Sentence Improvement questions: {len(si)}')
for q in si[:3]:
    print(f'\n[{q["id"]}]')
    print(f'  Question: {q["question"][:200]}')
    print(f'  Options: {q["options"]}')
    print(f'  Correct: {q.get("correct")}')
