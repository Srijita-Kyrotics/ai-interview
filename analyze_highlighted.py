import json

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

highlighted = [q for q in questions if 'highlighted' in q.get('question','').lower()]
print(f'Total highlighted: {len(highlighted)}')

direct = 0
partial = 0
none = 0
examples_direct = []
for q in highlighted:
    text = q['question']
    lines = text.strip().split('\n')
    sentence = lines[-1].strip() if len(lines) > 1 else ''
    options = q.get('options', [])
    if not sentence or not options:
        none += 1
        continue
    orig = options[0]
    if orig in sentence:
        direct += 1
        if len(examples_direct) < 3:
            examples_direct.append((q['id'], sentence, orig))
    elif any(word in sentence for word in orig.split()):
        partial += 1
    else:
        none += 1

print(f'Direct match (option[0] in sentence): {direct}')
print(f'Partial match: {partial}')
print(f'No match: {none}')
print()
for qid, sentence, orig in examples_direct:
    print(f'[{qid}] HI=\"<mark>{orig}</mark>\" in \"{sentence}\"')
