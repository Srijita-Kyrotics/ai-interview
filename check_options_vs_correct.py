import json

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

highlighted = [q for q in questions if 'highlighted' in q.get('question','').lower()]

# Check: how often is option[0] the original text embedded in the sentence?
# Also check: is option[0] always the correct answer?
opt0_is_correct = 0
opt0_is_original = 0
for q in highlighted:
    text = q['question']
    lines = text.strip().split('\n')
    sentence = lines[-1].strip() if len(lines) > 1 else ''
    options = q.get('options', [])
    correct = q.get('correct', '')
    
    # Check if correct answer is options[0]
    if options and correct == options[0]:
        opt0_is_correct += 1
    
    # Check if options[0] is a substring of the sentence
    if options and options[0] in sentence:
        opt0_is_original += 1

print(f'Total highlighted questions: {len(highlighted)}')
print(f'Option[0] IS the correct answer: {opt0_is_correct}')
print(f'Option[0] appears verbatim in sentence: {opt0_is_original}')

# Show all options for a few questions
for q in highlighted[:3]:
    text = q['question']
    lines = text.strip().split('\n')
    sentence = lines[-1].strip() if len(lines) > 1 else ''
    print(f'\n[{q["id"]}]')
    print(f'Sentence: {sentence}')
    for i, opt in enumerate(q['options']):
        marker = ' (CORRECT)' if opt == q.get('correct') else ''
        in_sentence = ' (IN SENTENCE)' if opt in sentence else ''
        print(f'  Option[{i}]: \"{opt}\"{marker}{in_sentence}')
