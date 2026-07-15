import json, re

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

# For "other" questions, check comprehension passages and other long texts
# for any text that might need formatting

# 1. Check Comprehension passages for italicized words, book titles, etc.
comprehension = [q for q in questions if q.get('topic') == 'Comprehension']
print(f'Comprehension questions: {len(comprehension)}')

# Look for patterns in all question texts that might indicate formatting
# - Words in ALL CAPS (might represent headings or emphasis)
# - Words in 'single quotes' or "double quotes" 
# - Patterns like (A), (B), etc.
# - Numbers or symbols that might need special formatting

# Check for ALL CAPS words (3+ letters) that might be emphasized
all_text = ''
for q in questions:
    all_text += q.get('question', '') + '\n'
    for opt in q.get('options', []):
        all_text += opt + '\n'

# Find all-caps words
caps_words = set(re.findall(r'\b[A-Z]{3,}\b', all_text))
# Filter to meaningful content words (not just after period)
# Look at context
print(f'\nUnique ALL CAPS words (3+ letters): {len(caps_words)}')

# Categorize
proper_nouns = {'RAJKOT', 'UJJAIN', 'MUMBAI', 'DELHI', 'INDIA', 'ENGLAND', 'SATURDAY', 'SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER', 'HINDI', 'SANSKRIT', 'ROMAN', 'GREEK'}
grammatical = {'THE', 'AND', 'FOR', 'WAS', 'BUT', 'NOT', 'ARE', 'HAS', 'HAD', 'ITS', 'CAN', 'ALL', 'ANY', 'WHO', 'HOW', 'WHY', 'SOME', 'EACH', 'MANY', 'MORE', 'MOST', 'VERY', 'SUCH', 'THAN', 'THAT', 'THIS', 'WITH', 'FROM', 'WHEN', 'WHAT', 'WHICH', 'WHERE', 'THERE', 'THEIR', 'HAVE', 'BEEN', 'BEING', 'SHOULD', 'WOULD', 'COULD', 'MIGHT', 'MUST', 'INTO', 'UPON', 'ABOUT', 'BETWEEN', 'THROUGH', 'WITHOUT', 'ALSO', 'ONLY', 'JUST', 'EVEN', 'STILL', 'ALREADY', 'ALWAYS', 'OFTEN', 'NEVER', 'ALMOST', 'QUITE', 'RATHER'}
# Ignore proper nouns and grammatical words
unusual = caps_words - proper_nouns - grammatical

# Check context for these unusual caps words
print(f'\nUnusual ALL CAPS (not proper nouns/grammar):')
for w in sorted(unusual)[:30]:
    # Find context
    for m in re.finditer(r'\b' + re.escape(w) + r'\b', all_text):
        start = max(0, m.start() - 40)
        end = min(len(all_text), m.end() + 40)
        context = all_text[start:end]
        print(f'  {w}: ...{context.strip()}...')
        break

# Check for questions with underscores (_) that might indicate formatting
print('\n\nWords with underscores (possible formatting):')
for q in questions:
    text = q.get('question', '')
    us = re.findall(r'\b\w+_\w+\b', text)
    if us:
        print(f'  [{q["id"]}] {us} in {text[:150]}')

# Check for questions using special formatting characters like | or / in ways that suggest layout
print('\n\nQuestions with possible layout/markdown:')
for q in questions:
    text = q.get('question', '')
    if '|' in text and not '||' in text:
        pass  # pipe might be in normal text
