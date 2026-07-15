import json, sys

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

highlighted = [q for q in questions if 'highlighted' in q.get('question','').lower()]

# For each question, try to find which part of the sentence is highlighted
# by finding the longest word sequence from the sentence that appears in options[0]
results = []
for q in highlighted:
    text = q['question']
    lines = text.strip().split('\n')
    sentence = lines[-1].strip() if len(lines) > 1 else ''
    options = q.get('options', [])
    if not sentence or not options:
        continue
    
    orig = options[0]
    words = sentence.split()
    
    # Find the best match: the substring of the sentence that has the most word overlap with orig
    best_start, best_end, best_score = 0, 0, 0
    for i in range(len(words)):
        for j in range(i + 1, len(words) + 1):
            phrase = ' '.join(words[i:j])
            # Score: number of words from orig that appear in this phrase
            score = sum(1 for w in phrase.split() if w.lower() in orig.lower())
            if score > best_score:
                best_score = score
                best_start, best_end = i, j
    
    highlighted_part = ' '.join(words[best_start:best_end])
    
    # Build highlighted sentence
    before = ' '.join(words[:best_start])
    after = ' '.join(words[best_end:])
    
    results.append((q['id'], sentence, highlighted_part, before, after, best_score, orig))

# Write results to a file
with open('highlighted_analysis.txt', 'w', encoding='utf-8') as f:
    f.write(f'Total highlighted questions: {len(results)}\n\n')
    for qid, sentence, hp, before, after, score, orig in results:
        f.write(f'[{qid}] score={score}\n')
        f.write(f'  Sentence: {sentence}\n')
        f.write(f'  Option[0]: {orig}\n')
        f.write(f'  Highlighted: {hp}\n')
        f.write(f'  Before: {before}\n')
        f.write(f'  After: {after}\n\n')

# Print summary stats
from collections import Counter
word_counts = Counter(len(r[2].split()) for r in results)
print('Words in highlighted part:')
for k in sorted(word_counts):
    print(f'  {k} words: {word_counts[k]}')
print(f'\nTotal: {len(results)}')
