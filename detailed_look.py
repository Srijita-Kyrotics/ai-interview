import json

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

highlighted = [q for q in questions if 'highlighted' in q.get('question','').lower()]

# Look at 10 consecutive highlighted questions to understand the pattern
for q in highlighted[10:20]:
    text = q['question']
    lines = text.strip().split('\n')
    sentence = lines[-1].strip() if len(lines) > 1 else ''
    options = q.get('options', [])
    correct = q.get('correct', '')
    
    print(f'[{q["id"]}]')
    print(f'  Sentence: {sentence}')
    for i, opt in enumerate(options):
        marker = ' *** CORRECT ***' if opt == correct else ''
        print(f'    [{i}] {opt}{marker}')
    print()
