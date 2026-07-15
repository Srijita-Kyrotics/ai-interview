import json, unicodedata, sys

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

all_text = ''
for q in questions:
    all_text += q.get('question', '') + '\n'
    for opt in q.get('options', []):
        all_text += opt + '\n'

non_ascii = {}
for ch in all_text:
    if ord(ch) > 127:
        if ch not in non_ascii:
            non_ascii[ch] = 0
        non_ascii[ch] += 1

# Write to file
with open('unicode_analysis.txt', 'w', encoding='utf-8') as f:
    f.write(f'Unique non-ASCII characters: {len(non_ascii)}\n\n')
    from collections import defaultdict
    by_cat = defaultdict(list)
    for ch, count in sorted(non_ascii.items(), key=lambda x: -x[1]):
        cat = unicodedata.category(ch)
        name = unicodedata.name(ch, 'UNKNOWN')
        by_cat[cat].append((ch, count, name))
    
    for cat, items in sorted(by_cat.items()):
        f.write(f'Category {cat}:\n')
        for ch, count, name in items[:20]:
            display = ch if ch.isprintable() else f'U+{ord(ch):04X}'
            f.write(f'  {display} (U+{ord(ch):04X}): {count}x - {name}\n')
        if len(items) > 20:
            f.write(f'  ... and {len(items)-20} more\n')
        f.write('\n')

print('Written to unicode_analysis.txt')
