from pathlib import Path

path = Path('shared/coding_questions.json')
text = path.read_text(encoding='utf-8')
lines = text.splitlines(True)
for i, line in enumerate(lines):
    if r'if (\"([{\"]\".indexOf(ch) >= 0) stack.push(ch);' in line:
        lines[i] = line.replace(
            r'if (\"([{\"]\".indexOf(ch) >= 0) stack.push(ch);',
            r'if (\"([{"]\".indexOf(ch) >= 0) stack.push(ch);'
        )
text = ''.join(lines)
path.write_text(text, encoding='utf-8')
print('patched')
