import json

def find_highlighted(sentence, options, correct):
    """Find the highlighted part of the sentence using word overlap with options."""
    words = sentence.split()
    if not words:
        return sentence, '', ''
    
    best_start = len(words)
    best_end = 0
    
    # Use correct answer and all options to find overlapping words
    candidates = [correct] + options
    for cand in candidates:
        cand_words = cand.lower().split()
        for cw in cand_words:
            for i, w in enumerate(words):
                if w.lower() == cw:
                    best_start = min(best_start, i)
                    best_end = max(best_end, i + 1)
    
    # If no match found, try partial word matching
    if best_start >= best_end:
        for cand in candidates:
            cand_words = cand.lower().split()
            for cw in cand_words:
                for i, w in enumerate(words):
                    if len(cw) >= 3 and (cw.startswith(w.lower()) or w.lower().startswith(cw)):
                        best_start = min(best_start, i)
                        best_end = max(best_end, i + 1)
    
    # If still no match, default to last 3-4 words
    if best_start >= best_end:
        best_start = max(0, len(words) - 4)
        best_end = len(words)
    
    before = ' '.join(words[:best_start])
    hl = ' '.join(words[best_start:best_end])
    after = ' '.join(words[best_end:])
    
    return before, hl, after

with open('frontend/public/questions/aptitude.json', encoding='utf-8') as f:
    data = json.load(f)
questions = data.get('questions', data)

highlighted = [q for q in questions if 'highlighted' in q.get('question','').lower()]

# Test on first 20
good = 0
bad = 0
for q in highlighted[:20]:
    text = q['question']
    lines = text.strip().split('\n')
    sentence = lines[-1].strip() if len(lines) > 1 else ''
    options = q.get('options', [])
    correct = q.get('correct', '')
    
    before, hl, after = find_highlighted(sentence, options, correct)
    
    print(f'[{q["id"]}]')
    print(f'  Sentence: {sentence}')
    print(f'  Correct: {correct}')
    print(f'  Before: "{before}" | HL: "{hl}" | After: "{after}"')
    print()
