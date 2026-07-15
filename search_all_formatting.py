import json, re, sys

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

# Search ALL text fields for formatting mentions
fields = ['question', 'options', 'correct', 'topic']
all_matches = {}

for q in questions:
    for field in fields:
        val = q.get(field)
        if isinstance(val, str):
            texts = [val]
        elif isinstance(val, list):
            texts = val
        else:
            continue
        
        for text in texts:
            # Look for the exact words
            lower = text.lower()
            for word in ['italic', 'italics', 'italicized', 'italicised', 'italicize', 'italicise']:
                if word in lower:
                    all_matches.setdefault(word, []).append((q['id'], field, text[:150]))
            for word in ['bold', 'bolded', 'boldface']:
                if word in lower and word not in ['bold']:
                    all_matches.setdefault(word, []).append((q['id'], field, text[:150]))
            # For 'bold', check it's not just a vocabulary word
            if 'bold' in lower:
                # Check if it's about formatting
                if any(ctx in lower for ctx in ['in bold', 'bold word', 'bold text', 'bold letter', 'bolded']):
                    all_matches.setdefault('bold_formatting', []).append((q['id'], field, text[:150]))
            for word in ['underline', 'underlined', 'underlining', 'underlines']:
                if word in lower:
                    all_matches.setdefault(word, []).append((q['id'], field, text[:150]))
            for word in ['strikethrough', 'strike-through', 'strike through']:
                if word in lower:
                    all_matches.setdefault('strikethrough', []).append((q['id'], field, text[:150]))
            for word in ['superscript', 'subscript']:
                if word in lower:
                    all_matches.setdefault(word, []).append((q['id'], field, text[:150]))

# Also check for HTML-like tags
html_style = re.compile(r'<(b|i|u|em|strong|mark|ins|del|s|strike)>', re.I)
html_matches = []
for q in questions:
    text = q.get('question', '')
    for m in html_style.finditer(text):
        html_matches.append((q['id'], m.group(), text[:150]))

print('Formatting references found:')
for key, matches in sorted(all_matches.items()):
    print(f'\n--- {key} ({len(matches)}) ---')
    for qid, field, text in matches[:3]:
        print(f'  [{qid}] ({field}) {text}')

if html_matches:
    print(f'\n--- HTML-style formatting tags ---')
    for qid, tag, text in html_matches[:5]:
        print(f'  [{qid}] {tag} in {text[:120]}')
else:
    print('\nNo HTML formatting tags found.')

# Check for markdown-style formatting that might be rendering instructions
# Like `code`, ~~strikethrough~~, etc.
print('\n--- Also check for specific formats ---')

# Check questions that have "word" followed by formatting description
# Like "the word 'X' is" 
word_refs = re.finditer(r"the\s+word\s+['\u2018\u2019]([^'\u2019]+)['\u2019]", 
                        '\n'.join(q.get('question','') for q in questions), re.I)
word_count = 0
for m in word_refs:
    word_count += 1
    if word_count <= 5:
        print(f'  Word reference: \"{m.group(1)}\"')
print(f'  Total word references: {word_count}')

# Check if there are any sections/topics that might indicate formatting
print('\n--- Unique topics in verbal section ---')
verbal_topics = set()
for q in questions:
    if q.get('section') == 'verbal' and q.get('topic'):
        verbal_topics.add(q['topic'])
for t in sorted(verbal_topics):
    print(f'  {t}')
