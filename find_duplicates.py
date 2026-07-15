import json, re
from collections import defaultdict

with open(r'D:\RECRUITMENT_PLATFORM\frontend\public\questions\aptitude.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

target_topics = [
    'Logical Deduction', 'Statement and Conclusion', 'Statement and Assumption', 
    'Statement and Argument', 'Course of Action', 'Cause and Effect', 
    'Theme Detection', 'Verification of Truth', 'Logical Games',
    'Logical Problems', 'Syllogism', 'Essential Part', 'Making Judgments',
    'Analyzing Arguments',
]

# For each topic, find the common option pattern and show representative questions
topic_examples = defaultdict(list)
seen_topic_patterns = {}

for q in data['questions']:
    if q.get('topic') in target_topics:
        t = q['topic']
        qid = q['id']
        question = q['question']
        options = q['options']
        correct = q.get('correct')
        
        # Extract the unique content after "Statement:" or "Statements:" or "Conclusions:"
        # and the conclusion text itself
        
        if t not in seen_topic_patterns:
            seen_topic_patterns[t] = {
                'first_qid': qid,
                'question_snippet': question[:300],
                'options': options,
                'correct': correct,
            }

# Now for each topic, show the pattern
print("=" * 80)
print("LOGICAL REASONING QUESTIONS WITH DUPLICATED CONTENT: TOPIC SUMMARIES")
print("=" * 80)

for t in target_topics:
    if t in seen_topic_patterns:
        info = seen_topic_patterns[t]
        print(f'\n## {t} (Example: {info["first_qid"]})')
        print(f'**Question (first 300 chars):**')
        print(f'{info["question_snippet"]}')
        print(f'\n**Options:** {info["options"]}')
        print(f'**Correct Answer:** {info["correct"]}')
        
        # Analyze duplication
        question_lower = info['question_snippet'].lower()
        dupes = []
        for opt in info['options']:
            core_phrases = opt.split()
            # Check key phrases
            for plen in range(min(len(core_phrases), 6), 2, -1):
                for start in range(0, len(core_phrases) - plen + 1):
                    phrase = ' '.join(core_phrases[start:start+plen]).lower().rstrip('.')
                    if len(phrase) > 10 and phrase in question_lower:
                        dupes.append(opt)
                        break
                if dupes and dupes[-1] == opt:
                    break
        
        if dupes:
            print(f'**Duplicated option text found in question:** {dupes}')
        
        # Count total questions for this topic
        count = sum(1 for q in data['questions'] if q.get('topic') == t)
        print(f'**Total questions in this category:** {count}')
        print()

# Now show 5 specific full examples that demonstrate the duplication pattern
print("\n" + "=" * 80)
print("FULL EXAMPLES WITH COMPLETE CONTENT (10-15 examples)")
print("=" * 80)

# Get one example from each major topic
topic_ids = {
    'Statement and Conclusion': 'logical-0250',
    'Statement and Assumption': 'logical-0151',
    'Statement and Argument': 'logical-0346',
    'Course of Action': 'logical-0200',
    'Cause and Effect': 'logical-0316',
    'Logical Deduction': 'logical-0401',
    'Syllogism': 'logical-0998',
    'Theme Detection': 'logical-0298',
    'Logical Problems': 'logical-0127',
    'Logical Games': 'logical-0138',
    'Analyzing Arguments': 'logical-0142',
    'Essential Part': None,
    'Making Judgments': 'logical-0113',
    'Verification of Truth': 'logical-1388',
}

# Find Essential Part questions
for q in data['questions']:
    if q.get('topic') == 'Essential Part':
        topic_ids['Essential Part'] = q['id']
        break

# Find Logical Games questions
for q in data['questions']:
    if q.get('topic') == 'Logical Games':
        if topic_ids['Logical Games'] is None:
            topic_ids['Logical Games'] = q['id']
        break

# Find Verification of Truth questions  
count_vt = 0
for q in data['questions']:
    if q.get('topic') == 'Verification of Truth':
        count_vt += 1
        if count_vt == 1:
            topic_ids['Verification of Truth'] = q['id']
        break

# Find Theme Detection
count_td = 0
for q in data['questions']:
    if q.get('topic') == 'Theme Detection':
        count_td += 1
        if count_td == 1:
            topic_ids['Theme Detection'] = q['id']
        break

# Extract and display each example
example_count = 0
for topic, qid in topic_ids.items():
    if qid is None:
        continue
    for q in data['questions']:
        if q['id'] == qid:
            example_count += 1
            print(f'\n### Example {example_count}: {q["id"]} [{q["topic"]}]')
            print(f'**ID:** {q["id"]}')
            print(f'**Topic:** {q["topic"]}')
            print(f'**Question:**')
            print(f'{q["question"]}')
            print(f'\n**Options:**')
            for i, opt in enumerate(q['options']):
                print(f'  {chr(65+i)}. {opt}')
            print(f'**Correct:** {q["correct"]}')
            
            # Show the duplicated text
            question_lower = q['question'].lower()
            dupes = []
            for opt in q['options']:
                phrase_to_check = opt.lower().rstrip('. ')
                if len(phrase_to_check) > 10 and phrase_to_check in question_lower:
                    dupes.append(opt)
            if dupes:
                print(f'**Duplicated option text found in question body:** {dupes}')
            print()
            break

print(f'\nTotal examples shown: {example_count}')
