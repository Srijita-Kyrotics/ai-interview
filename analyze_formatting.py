import json, re

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

# Search for any text that includes visual formatting instructions
# This includes words like: italic, italics, italicized, bold, bolded, underline, underlined, underlining, highlight, highlighted, strikethrough, subscript, superscript
fmt_words = ['italic', 'bold', 'underline', 'highlight', 'strikethrough', 'subscript', 'superscript', 'emphasize', 'emphasized']
patterns_found = {}

for q in questions:
    text = q.get('question', '')
    for fw in fmt_words:
        if fw in text.lower():
            if fw not in patterns_found:
                patterns_found[fw] = []
            if len(patterns_found[fw]) < 3:
                patterns_found[fw].append((q['id'], text[:200]))

print('Questions mentioning formatting:')
for fw, examples in sorted(patterns_found.items()):
    print(f'\n--- {fw} ({sum(1 for q in questions if fw in q.get(\"question\",\"\").lower())}) ---')
    for qid, text in examples:
        print(f'  [{qid}] {text}')
