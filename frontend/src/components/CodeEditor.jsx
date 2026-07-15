import React from 'react'

function CodeEditor({ value, onChange, language, starter, questionTitle }) {
  const lineCount = Math.max(1, value.split('\n').length)
  const charCount = value.length
  const onKeyDown = (event) => {
    if (event.key !== 'Tab') return
    event.preventDefault()
    const target = event.currentTarget
    const start = target.selectionStart
    const end = target.selectionEnd
    const nextValue = `${value.slice(0, start)}  ${value.slice(end)}`
    onChange(nextValue)
    window.requestAnimationFrame(() => {
      target.selectionStart = start + 2
      target.selectionEnd = start + 2
    })
  }

  return (
    <div className="leetcode-editor-shell">
      <div className="editor-toolbar">
        <div className="editor-title-stack">
          <span className="editor-kicker">Code</span>
          <strong>{questionTitle || 'Solution'}</strong>
        </div>
        <div className="editor-meta">
          <span>{language}</span>
          <span>{lineCount} lines</span>
          <span>{charCount} chars</span>
        </div>
      </div>
      <div className="code-editor-wrapper">
        <div className="editor-lines" aria-hidden="true">
          {Array.from({ length: lineCount }, (_, i) => (
            <div key={i} className="line-number">{i + 1}</div>
          ))}
        </div>
        <textarea
          className="code-editor"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={starter || 'Write your code here'}
          spellCheck="false"
        />
      </div>
    </div>
  )
}

export { CodeEditor }
