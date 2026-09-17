import React from 'react';
import { AlertTriangle, CheckCircle2, Clock3, Code2, Loader2, Play, Send, Timer } from 'lucide-react';
import CodingEditor from './CodingEditor';
import './CodingPanel.css';

const statusLabel = {
  passed: 'Passed',
  failed: 'Wrong Answer',
  timeout: 'Time Limit Exceeded',
  runtime_error: 'Runtime Error',
  error: 'Error',
};

const resultTone = (status) => status === 'passed' ? 'pass' : 'fail';

const CodingPanel = ({
  problem,
  language,
  onLanguageChange,
  code,
  onCodeChange,
  runStatus,
  runOutput,
  isRunning,
  isTesting,
  isSubmitting,
  isThinking,
  testResults,
  submissionResult,
  onRun,
  onTest,
  onSubmit,
  onNextProblem,
  onReset,
  isDirectMode,
  languageOptions,
}) => {
  const publicCases = problem?.visible_test_cases || problem?.testCases || [];
  const starterCode = problem?.starter_code?.[language] || problem?.starterCode?.[language] || '';
  const activeResult = submissionResult || testResults;
  const resultTitle = submissionResult ? 'Submission Result' : 'Public Test Results';

  return (
    <section className="aii-coding-platform" aria-label="Coding interview workspace">
      <aside className="aii-coding-problem-panel">
        <div className="aii-coding-panel-eyebrow"><Code2 size="14" /> Coding challenge</div>
        <div className="aii-coding-problem-heading">
          <h2>{problem?.title || 'Coding Challenge'}</h2>
          <div className="aii-coding-problem-meta">
            <span className={`aii-problem__diff aii-problem__diff--${problem?.difficulty || 'medium'}`}>
              {problem?.difficulty || 'medium'}
            </span>
            <span>{problem?.category || problem?.topic || 'Algorithms'}</span>
          </div>
        </div>
        <div className="aii-coding-problem-scroll">
          <section className="aii-coding-copy-section">
            <h3>Problem</h3>
            <p>{problem?.description || problem?.statement || 'Read the prompt and implement the required solution.'}</p>
          </section>
          {(problem?.examples || []).length > 0 && (
            <section className="aii-coding-copy-section">
              <h3>Examples</h3>
              <div className="aii-coding-examples">
                {problem.examples.map((example, index) => (
                  <div className="aii-coding-example" key={index}>
                    {typeof example === 'string' ? <pre>{example}</pre> : (
                      <>
                        {example.input !== undefined && <pre><strong>Input</strong>{'\n'}{example.input}</pre>}
                        {example.output !== undefined && <pre><strong>Output</strong>{'\n'}{example.output}</pre>}
                        {example.explanation && <p>{example.explanation}</p>}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
          {(problem?.constraints || []).length > 0 && (
            <section className="aii-coding-copy-section">
              <h3>Constraints</h3>
              <ul className="aii-coding-constraints">
                {problem.constraints.map((constraint, index) => <li key={index}>{constraint}</li>)}
              </ul>
            </section>
          )}
          {(problem?.function_signature || problem?.functionName) && (
            <section className="aii-coding-copy-section">
              <h3>Expected signature</h3>
              <code className="aii-signature">{problem.function_signature || problem.functionName}</code>
            </section>
          )}
          <div className="aii-coding-limits">
            {problem?.timeLimit && <span><Timer size="13" /> {problem.timeLimit}ms</span>}
            {problem?.memoryLimit && <span><Clock3 size="13" /> {problem.memoryLimit}MB</span>}
          </div>
        </div>
      </aside>

      <div className="aii-coding-workspace-main">
        <div className="aii-coding-toolbar">
          <div className="aii-coding-language-tabs" role="tablist" aria-label="Programming language">
            {languageOptions.map((option) => (
              <button
                type="button"
                role="tab"
                aria-selected={language === option.key}
                key={option.key}
                className={`aii-coding-language-tab ${language === option.key ? 'is-active' : ''}`}
                onClick={() => onLanguageChange(option.key)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="aii-coding-actions">
            {onNextProblem && <button type="button" className="aii-coding-secondary-btn" onClick={onNextProblem}>Next Problem</button>}
            <button type="button" className="aii-coding-secondary-btn" onClick={onReset}>Reset</button>
            <button type="button" className="aii-coding-run-btn" onClick={onRun} disabled={isRunning || !code.trim()}>
              {isRunning ? <Loader2 size="14" className="aii-spin" /> : <Play size="14" />} Run Code
            </button>
            {!isDirectMode && (
              <button type="button" className="aii-coding-submit-btn" onClick={onSubmit} disabled={isSubmitting || isThinking || !code.trim()}>
                {isSubmitting ? <Loader2 size="14" className="aii-spin" /> : <Send size="14" />} Submit
              </button>
            )}
          </div>
        </div>
        <div className="aii-coding-editor-main">
          <CodingEditor
            value={code}
            language={language}
            starterCode={starterCode}
            onChange={onCodeChange}
            onRun={onRun}
            onReset={onReset}
          />
        </div>
        <div className="aii-coding-results-panel">
          <div className="aii-coding-results-header">
            <div><span className="aii-coding-results-kicker">Output</span><strong>{resultTitle}</strong></div>
            {runStatus && <span className={`aii-coding-run-status ${runStatus.toLowerCase().includes('success') ? 'is-good' : 'is-bad'}`}>{runStatus}</span>}
          </div>
          {runOutput && <pre className="aii-coding-raw-output">{runOutput}</pre>}
          {!activeResult && !runOutput && <p className="aii-coding-empty-result">Run the visible test cases to inspect output. Submit sends the complete solution to Jack for evaluation.</p>}
          {activeResult?.error && <div className="aii-coding-error"><AlertTriangle size="15" /> {activeResult.error}</div>}
          {activeResult && !activeResult.error && (
            <>
              <div className={`aii-coding-summary ${activeResult.passed === activeResult.total ? 'is-pass' : 'is-fail'}`}>
                <CheckCircle2 size="15" />
                <strong>{submissionResult?.status ? String(submissionResult.status).replaceAll('_', ' ').toUpperCase() : `${activeResult.passed}/${activeResult.total} PASSED`}</strong>
                <span>{activeResult.passed}/{activeResult.total} test cases</span>
                {activeResult.time_ms != null && <span>{activeResult.time_ms}ms</span>}
              </div>
              <div className="aii-coding-case-list">
                {(activeResult.results || []).map((result, index) => (
                  <div className={`aii-coding-case aii-coding-case--${resultTone(result.status)}`} key={index}>
                    <div className="aii-coding-case-heading"><strong>{result.status === 'passed' ? '✓' : '✕'} Case {index + 1}</strong><span>{statusLabel[result.status] || result.status}</span></div>
                    <code>Input: {result.input || '(empty)'}</code>
                    <code>Expected: {result.expected || '(empty)'}</code>
                    <code>Output: {result.output || '(no output)'}</code>
                    {result.error && <code className="aii-coding-case-error">{result.error}</code>}
                    {result.time_ms != null && <small>{result.time_ms}ms</small>}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
};

export default CodingPanel;
