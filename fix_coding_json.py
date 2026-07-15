from pathlib import Path

path = Path('shared/coding_questions.json')
text = path.read_text(encoding='utf-8')
text = text.replace(
    'if (\\"([{\"]\\".indexOf(ch) >= 0) stack.push(ch);',
    'if (\\"([{"]\\".indexOf(ch) >= 0) stack.push(ch);'
)
text = text.replace('}\\\n      "c": "#include', '}",\n      "c": "#include')
path.write_text(text, encoding='utf-8')
print('patched')
