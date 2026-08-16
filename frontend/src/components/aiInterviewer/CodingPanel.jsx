import React from 'react';
import { AlertTriangle, CheckCircle2, Loader2, Play, Send } from 'lucide-react';
import { CodeEditor } from '../CodeEditor';

// Live coding tab: problem statement, language selector, editor, run/judge output.
const CodingPanel = ({
  problem,
  language,
  onLanguageChange,
  code,
  onCodeChange,
  stdin,
  onStdinChange,
  runStatus,
  runOutput,
  isRunning,
  isTesting,
  isThinking,
  testResults,
  onRun,
  onTest,
  onSend,
  languageOptions,
}) => {
  return (
    <div className="aii-code-area">
      {problem && (
        <div className="aii-problem">
          <div className="aii-problem__header">
            <span className={`aii-problem__diff aii-problem__diff--${problem.difficulty || 'medium'}`}>
              {problem.difficulty || 'medium'}
            </span>
            <h3>{problem.title || 'Coding Challenge'}</h3>
            {problem.topic && <span className="aii-problem__topic">{problem.topic}</span>}
          </div>
          <p className="aii-problem__desc">{problem.description}</p>
          {(problem.examples || []).length > 0 && (
            <div className="aii-problem__examples">
              {(problem.examples || []).map((ex, i) => (
                <div className="aii-problem__example" key={i}>
                  {ex.input && <pre>Input:    {ex.input}</pre>}
                  {ex.output && <pre>Output:   {ex.output}</pre>}
                  {ex.explanation && <pre>Explain:  {ex.explanation}</pre>}
                </div>
              ))}
            </div>
          )}
          {(problem.constraints || []).length > 0 && (
            <div className="aii-problem__constraints">
              {(problem.constraints || []).map((c, i) => (
                <span key={i}>{c}</span>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="aii-code-toolbar">
        <div className="aii-lang-selector">
          {languageOptions.map(opt => (
            <button
              key={opt.key}
              className={`aii-lang-btn ${language === opt.key ? 'aii-lang-btn--active' : ''}`}
              onClick={() => onLanguageChange(opt.key)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <span className="aii-code-hint">
          Code written here is shared with Obi for evaluation
        </span>
        <button
          className="aii-run-btn"
          onClick={onRun}
          disabled={isRunning || !code.trim()}
          title="Run code and see output"
        >
          {isRunning ? <><Loader2 size="14" className="aii-spin" /> Running…</> : <><Play size="14" /> Run Code</>}
        </button>
        {(problem?.visible_test_cases || []).length > 0 && (
          <button
            className="aii-test-btn"
            onClick={onTest}
            disabled={isRunning || isTesting || !code.trim()}
            title="Run your code against the visible test cases"
          >
            {isTesting ? <><Loader2 size="14" className="aii-spin" /> Testing…</> : <><CheckCircle2 size="14" /> Run Tests</>}
          </button>
        )}
        <button
          className="aii-submit-code-btn"
          onClick={onSend}
          disabled={isThinking || !code.trim()}
          title="Send this solution to Obi for evaluation"
        >
          <Send size="14" /> Submit to Obi
        </button>
      </div>
      <div className="aii-code-editor-wrap">
        <CodeEditor
          value={code}
          onChange={onCodeChange}
          language={language}
          questionTitle="Live Code"
        />
      </div>
      <div className="aii-run-panel">
        <div className="aii-run-panel__row">
          <input
            className="aii-stdin-input"
            placeholder="Optional stdin — e.g. 1 2 3"
            value={stdin}
            onChange={(e) => onStdinChange(e.target.value)}
            disabled={isRunning}
          />
          {runStatus && (
            <span
              className={`aii-run-status aii-run-status--${runStatus.toLowerCase().includes('successfully') ? 'good' : 'bad'}`}
            >
              {runStatus.toLowerCase().includes('successfully')
                ? <><CheckCircle2 size="13" /> {runStatus}</>
                : <><AlertTriangle size="13" /> {runStatus}</>}
            </span>
          )}
        </div>
        {runOutput && (
          <pre className="aii-run-output">{runOutput}</pre>
        )}
      </div>
      {testResults && (
        <div className="aii-test-results">
          {testResults.error ? (
            <div className="aii-test-results__error">
              <AlertTriangle size="14" /> {testResults.error}
            </div>
          ) : (
            <>
              <div className={`aii-test-summary ${testResults.passed === testResults.total ? 'aii-test-summary--good' : 'aii-test-summary--bad'}`}>
                <CheckCircle2 size="14" />
                {testResults.passed}/{testResults.total} tests passed
                {testResults.compile_error ? ' — compilation failed' : ` — ${testResults.score}%`}
              </div>
              <div className="aii-test-cases">
                {(testResults.results || []).map((r, i) => (
                  <div key={i} className={`aii-test-case aii-test-case--${r.status === 'passed' ? 'pass' : 'fail'}`}>
                    <span className="aii-test-case__tag">{r.status === 'passed' ? 'PASS' : (r.status || 'FAIL').toUpperCase()}</span>
                    <div className="aii-test-case__body">
                      <code>in:  {r.input || '(empty)'}</code>
                      <code>exp: {r.expected || '(empty)'}</code>
                      <code>got: {r.output || '(no output)'}</code>
                      {r.time_ms != null && <code className="aii-test-case__time">{r.time_ms}ms</code>}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default CodingPanel;
