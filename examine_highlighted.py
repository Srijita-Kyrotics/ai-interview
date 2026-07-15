import json

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

highlighted_qs = [q for q in questions if 'highlighted' in q.get('question','').lower()]

# Show 10 examples in detail
for q in highlighted_qs[:15]:
    print('ID:', q['id'])
    text = q['question']
    lines = text.strip().split('\n')
    instruction = lines[0].strip() if lines else ''
    sentence = lines[-1].strip() if len(lines) > 1 else ''
    print('  Instruction:', instruction[:80])
    print('  Sentence:', sentence[:120])
    print('  Options:', q['options'])
    print('  Correct:', q.get('correct'))
    print()
