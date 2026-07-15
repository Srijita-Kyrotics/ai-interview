from pathlib import Path

p = Path('shared/coding_questions.json')
text = p.read_text(encoding='utf-8')
text = text.replace('\\\"([{\"]\\\"', '\\\"([{"]\\\"')
p.write_text(text, encoding='utf-8')
print('patched')
