import React, { useEffect, useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import { Maximize2, Minimize2, RotateCcw } from 'lucide-react';

const MONACO_LANGUAGES = {
  python: 'python',
  javascript: 'javascript',
  java: 'java',
  cpp: 'cpp',
  c: 'c',
  csharp: 'csharp',
  go: 'go',
  rust: 'rust',
  typescript: 'typescript',
};

const CodingEditor = ({
  value,
  language,
  starterCode,
  onChange,
  onRun,
  onReset,
  readOnly = false,
}) => {
  const editorRef = useRef(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        onRun?.();
      }
      if (event.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen, onRun]);

  const handleMount = (editor, monaco) => {
    editorRef.current = editor;
    editor.addAction({
      id: 'run-coding-solution',
      label: 'Run coding solution',
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter],
      run: () => onRun?.(),
    });
  };

  return (
    <div className={`aii-monaco-shell ${isFullscreen ? 'aii-monaco-shell--fullscreen' : ''}`}>
      <div className="aii-monaco-toolbar">
        <div className="aii-monaco-toolbar__title">
          <span className="aii-monaco-toolbar__kicker">Solution</span>
          <strong>{language || 'python'}</strong>
        </div>
        <div className="aii-monaco-toolbar__actions">
          <button type="button" className="aii-editor-tool" onClick={onReset} title="Reset starter code">
            <RotateCcw size="14" /> Reset
          </button>
          <button
            type="button"
            className="aii-editor-tool"
            onClick={() => setIsFullscreen((current) => !current)}
            title={isFullscreen ? 'Exit fullscreen editor' : 'Open fullscreen editor'}
          >
            {isFullscreen ? <Minimize2 size="14" /> : <Maximize2 size="14" />}
            {isFullscreen ? 'Exit' : 'Fullscreen'}
          </button>
        </div>
      </div>
      <div className="aii-monaco-editor">
        <Editor
          height="100%"
          language={MONACO_LANGUAGES[language] || 'plaintext'}
          value={value || starterCode || ''}
          theme="ai-interview-dark"
          onMount={handleMount}
          onChange={(nextValue) => onChange?.(nextValue || '')}
          options={{
            automaticLayout: true,
            minimap: { enabled: false },
            fontSize: 14,
            fontFamily: "'JetBrains Mono', 'Fira Code', Consolas, monospace",
            lineNumbers: 'on',
            roundedSelection: false,
            scrollBeyondLastLine: false,
            tabSize: 4,
            padding: { top: 14, bottom: 24 },
            wordWrap: 'on',
            readOnly,
            bracketPairColorization: { enabled: true },
            suggest: { showMethods: true, showFunctions: true },
          }}
          beforeMount={(monaco) => {
            monaco.editor.defineTheme('ai-interview-dark', {
              base: 'vs-dark',
              inherit: true,
              rules: [],
              colors: {
                'editor.background': '#0f1020',
                'editorGutter.background': '#0f1020',
                'editorLineNumber.foreground': '#59607c',
                'editorLineNumber.activeForeground': '#c4b5fd',
                'editor.lineHighlightBackground': '#1a1b31',
                'editor.selectionBackground': '#4338ca66',
              },
            });
          }}
        />
      </div>
    </div>
  );
};

export default CodingEditor;
