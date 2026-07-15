import React, { useMemo } from 'react'
import katex from 'katex'

const MACROS = {
  '\\root': '\\sqrt'
}

function preprocessLatex(code) {
  let result = code
  result = result.replace(/\\root\s+(\d+)\s*\\of\s*([{])/g, (_, n, open) => {
    return `\\sqrt[${n}]{`
  })
  result = result.replace(/\\root\s+(\d+)\s*\\of\s*/g, (_, n) => `\\sqrt[${n}]{`)
  result = result.replace(/\\root\s*\\of\s*/g, '\\sqrt{')
  result = result.replace(/\\eqalign/g, '\\begin{aligned}')
  result = result.replace(/\\cr/g, '\\\\')
  return result
}

function renderLatex(code, displayMode) {
  const processed = preprocessLatex(code)
  try {
    return katex.renderToString(processed, {
      throwOnError: false,
      displayMode,
      output: 'html',
      macros: MACROS,
      strict: false,
    })
  } catch {
    try {
      return katex.renderToString(code, {
        throwOnError: false,
        displayMode,
        output: 'html',
        strict: false,
      })
    } catch {
      return `<span class="math-raw">${escapeHtml(code)}</span>`
    }
  }
}

const COMBINED = new RegExp(
  '\\$\\$(.*?)\\$\\$|\\\\\\((.*?)\\\\\\)|\\\\\\[(.*?)\\\\\\]',
  'gs'
)

function splitText(text) {
  const parts = []
  let lastIndex = 0
  let match

  while ((match = COMBINED.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', value: text.slice(lastIndex, match.index) })
    }
    if (match[1] !== undefined) {
      parts.push({ type: 'block', value: match[1] })
    } else if (match[2] !== undefined) {
      parts.push({ type: 'inline', value: match[2] })
    } else if (match[3] !== undefined) {
      parts.push({ type: 'block', value: match[3] })
    }
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.slice(lastIndex) })
  }
  return parts
}

export default function MathRenderer({ text, as = 'span', className = '' }) {
  const content = useMemo(() => {
    if (!text) return null
    const parts = splitText(text)
    if (parts.length === 1 && parts[0].type === 'text') return null
    return parts.map((part, i) => {
      if (part.type === 'text') {
        return React.createElement('span', {
          key: i,
          className: 'math-text',
          dangerouslySetInnerHTML: { __html: escapeHtml(part.value) }
        })
      }
      const html = renderLatex(part.value, part.type === 'block')
      return React.createElement('span', {
        key: i,
        className: part.type === 'block' ? 'math-block' : 'math-inline',
        dangerouslySetInnerHTML: { __html: html }
      })
    })
  }, [text])

  if (!text) return null
  if (!content) {
    return React.createElement(as, {
      className: `math-renderer ${className}`.trim(),
      dangerouslySetInnerHTML: { __html: escapeHtml(text) }
    })
  }
  return React.createElement(as, { className: `math-renderer ${className}`.trim() }, content)
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}
