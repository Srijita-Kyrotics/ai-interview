import json, re
from collections import Counter

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

# Look for any text enclosed in special characters
all_text = '\n'.join(q.get('question','') for q in questions)
for opt in [opt for q in questions for opt in q.get('options',[])]:
    all_text += '\n' + opt

# Check for common formatting patterns from exam datasets
# Pattern: words in ALL CAPS (might indicate emphasis)
caps_words = re.findall(r'\b[A-Z]{2,}\b', all_text)
caps_counter = Counter(caps_words)
# Filter to relevant emphasis words
emphasis_words = {'NOTE', 'IMPORTANT', 'CORRECT', 'INCORRECT', 'OPTION', 'OPTIONS', 'CHOOSE', 'SELECT'}
print('Common emphasis CAPS words:')
for w in sorted(emphasis_words & set(caps_counter.keys())):
    print(f'  {w}: {caps_counter[w]}')

# Check for [] brackets that might enclose formatting
bracket_texts = re.findall(r'\[([^\]]+)\]', all_text)
bracket_counter = Counter(bracket_texts)
if bracket_counter:
    print(f'\nText in [] brackets (top 20):')
    for t, c in bracket_counter.most_common(20):
        print(f'  [{t}]: {c}')

# Check for {} braces
brace_texts = re.findall(r'\{([^}]+)\}', all_text)
brace_counter = Counter(brace_texts)
if brace_counter:
    print(f'\nText in {{}} braces (top 10):')
    for t, c in brace_counter.most_common(10):
        print(f'  {{{t}}}: {c}')

# Check for || pipes
pipe_texts = re.findall(r'\|([^|]+)\|', all_text)
if pipe_texts:
    print(f'\nText in || pipes (top 10):')
    for t in pipe_texts[:10]:
        print(f'  |{t}|')

# Check for < > angle brackets (non-HTML)
angle_texts = re.findall(r'<([^<>]+)>', all_text)
non_html = [t for t in angle_texts if t.lower() not in ('b', 'i', 'u', 'br', '/b', '/i', '/u', '/br', 'p', '/p')]
if non_html:
    print(f'\nNon-HTML text in <> brackets (top 10):')
    for t in non_html[:10]:
        print(f'  <{t}>')
