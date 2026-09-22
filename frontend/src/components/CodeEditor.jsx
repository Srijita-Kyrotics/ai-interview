import React, { useEffect, useRef } from 'react';
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, dropCursor, rectangularSelection } from '@codemirror/view';
import { EditorState, Compartment } from '@codemirror/state';
import { defaultKeymap, indentWithTab, history, historyKeymap } from '@codemirror/commands';
import { bracketMatching, indentOnInput, foldGutter, foldKeymap } from '@codemirror/language';
import { closeBrackets, closeBracketsKeymap, autocompletion, completionKeymap } from '@codemirror/autocomplete';
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
import { oneDark } from '@codemirror/theme-one-dark';
import { javascript } from '@codemirror/lang-javascript';
import { python } from '@codemirror/lang-python';
import { java } from '@codemirror/lang-java';
import { cpp } from '@codemirror/lang-cpp';

const langMap = {
  javascript: () => javascript(),
  typescript: () => javascript({ typescript: true }),
  python: () => python(),
  java: () => java(),
  c: () => cpp(),
  'c++': () => cpp(),
  cpp: () => cpp(),
  csharp: () => cpp(),
  'c#': () => cpp(),
  go: () => javascript(),
  rust: () => cpp(),
};

function getLanguageExtension(lang) {
  const key = (lang || 'javascript').toLowerCase();
  const factory = langMap[key];
  return factory ? factory() : javascript();
}

export default function CodeEditor({ value, onChange, language = 'python', starter, questionTitle, hideHeader = false, readOnly = false }) {
  const containerRef = useRef(null);
  const viewRef = useRef(null);
  const langCompartmentRef = useRef(new Compartment());
  const readOnlyCompartmentRef = useRef(new Compartment());
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!containerRef.current) return;

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        const doc = update.state.doc.toString();
        onChangeRef.current?.(doc);
      }
    });

    const state = EditorState.create({
      doc: value || starter || '',
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
        langCompartmentRef.current.of(getLanguageExtension(language)),
        readOnlyCompartmentRef.current.of(EditorState.readOnly.of(readOnly)),
        oneDark,
        updateListener,
        EditorView.theme({
          '&': { height: '100%', fontSize: '13.5px', background: '#0b0c19' },
          '.cm-scroller': { overflow: 'auto', fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace" },
          '.cm-content': { padding: '12px 0' },
          '.cm-gutters': { background: '#090a16', borderRight: '1px solid #1e2238', color: '#64748b' },
          '.cm-activeLineGutter': { background: '#181a2e', color: '#a5b4fc' },
          '.cm-activeLine': { background: 'rgba(99, 102, 241, 0.08)' },
        }),
      ],
    });

    const view = new EditorView({ state, parent: containerRef.current });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, []);

  // Sync external value changes
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (value !== current && (value !== undefined && value !== null)) {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value },
      });
    }
  }, [value]);

  // Update language dynamically
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({
      effects: langCompartmentRef.current.reconfigure(getLanguageExtension(language)),
    });
  }, [language]);

  // Update readOnly dynamically
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({
      effects: readOnlyCompartmentRef.current.reconfigure(EditorState.readOnly.of(readOnly)),
    });
  }, [readOnly]);

  const lineCount = (value || '').split('\n').length;
  const charCount = (value || '').length;

  return (
    <div className="leetcode-editor-shell" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {!hideHeader && (
        <div className="editor-toolbar">
          <div className="editor-title-stack">
            <span className="editor-kicker">Code</span>
            <strong>{questionTitle || 'Solution'}</strong>
          </div>
          <div className="editor-meta">
            <span>{language || 'Python'}</span>
            <span>{lineCount} lines</span>
            <span>{charCount} chars</span>
          </div>
        </div>
      )}
      <div
        className="code-editor-wrapper codemirror-wrapper"
        ref={containerRef}
        style={{ flex: 1, minHeight: 0, height: '100%', overflow: 'hidden' }}
      />
    </div>
  );
}

export { CodeEditor };
