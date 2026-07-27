import React, { useEffect, useRef } from 'react'
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, dropCursor, rectangularSelection } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { defaultKeymap, indentWithTab, history, historyKeymap } from '@codemirror/commands'
import { bracketMatching, indentOnInput, syntaxHighlighting, defaultHighlightStyle, foldGutter, foldKeymap } from '@codemirror/language'
import { closeBrackets, closeBracketsKeymap, autocompletion, completionKeymap } from '@codemirror/autocomplete'
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search'
import { oneDark } from '@codemirror/theme-one-dark'
import { javascript } from '@codemirror/lang-javascript'
import { python } from '@codemirror/lang-python'
import { java } from '@codemirror/lang-java'
import { cpp } from '@codemirror/lang-cpp'

const langMap = {
  javascript: () => javascript(),
  python: () => python(),
  java: () => java(),
  c: () => cpp(),
  'c++': () => cpp(),
  csharp: () => cpp(), // C# uses C-like syntax
  'c#': () => cpp(),
}

function getLanguageExtension(lang) {
  const key = (lang || 'javascript').toLowerCase()
  const factory = langMap[key]
  return factory ? factory() : javascript()
}

function CodeEditor({ value, onChange, language, starter, questionTitle }) {
  const containerRef = useRef(null)
  const viewRef = useRef(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    if (!containerRef.current) return

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        const doc = update.state.doc.toString()
        onChangeRef.current?.(doc)
      }
    })

    const state = EditorState.create({
      doc: value || '',
      extensions: [
        lineNumbers(),
        highlightActiveLineGutter(),
        history(),
        foldGutter(),
        drawSelection(),
        dropCursor(),
        EditorState.allowMultipleSelections.of(true),
        indentOnInput(),
        bracketMatching(),
        closeBrackets(),
        autocompletion(),
        rectangularSelection(),
        highlightActiveLine(),
        highlightSelectionMatches(),
        keymap.of([
          ...closeBracketsKeymap,
          ...defaultKeymap,
          ...searchKeymap,
          ...historyKeymap,
          ...foldKeymap,
          ...completionKeymap,
          indentWithTab,
        ]),
        getLanguageExtension(language),
        oneDark,
        updateListener,
        EditorView.theme({
          '&': { height: '100%', fontSize: '14px' },
          '.cm-scroller': { overflow: 'auto', fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace" },
          '.cm-content': { padding: '12px 0' },
          '.cm-gutters': { borderRight: '1px solid #334155' },
        }),
      ],
    })

    const view = new EditorView({ state, parent: containerRef.current })
    viewRef.current = view

    return () => {
      view.destroy()
      viewRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Sync external value changes (e.g., starter code on language switch)
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const current = view.state.doc.toString()
    if (value !== current) {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value || '' },
      })
    }
  }, [value])

  const lineCount = (value || '').split('\n').length
  const charCount = (value || '').length

  return (
    <div className="leetcode-editor-shell">
      <div className="editor-toolbar">
        <div className="editor-title-stack">
          <span className="editor-kicker">Code</span>
          <strong>{questionTitle || 'Solution'}</strong>
        </div>
        <div className="editor-meta">
          <span>{language || 'JavaScript'}</span>
          <span>{lineCount} lines</span>
          <span>{charCount} chars</span>
        </div>
      </div>
      <div className="code-editor-wrapper codemirror-wrapper" ref={containerRef} />
    </div>
  )
}

export { CodeEditor }
