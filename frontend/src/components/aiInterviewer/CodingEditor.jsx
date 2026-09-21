import React, { useEffect, useState } from 'react';
import { Maximize2, Minimize2, RotateCcw } from 'lucide-react';
import CodeEditor from '../CodeEditor';

const CodingEditor = ({
  value,
  language = 'python',
  starterCode,
  onChange,
  onRun,
  onReset,
  readOnly = false,
}) => {
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

  return (
    <div className={`aii-monaco-shell ${isFullscreen ? 'aii-monaco-shell--fullscreen' : ''}`} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
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
      <div className="aii-monaco-editor" style={{ flex: 1, minHeight: '220px', height: '100%', overflow: 'hidden' }}>
        <CodeEditor
          value={value !== undefined && value !== null ? value : (starterCode || '')}
          language={language}
          onChange={onChange}
          readOnly={readOnly}
          hideHeader={true}
        />
      </div>
    </div>
  );
};

export default CodingEditor;
