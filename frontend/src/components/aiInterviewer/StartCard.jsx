import React from 'react';
import { ArrowRight, CheckCircle2, Clock, ListChecks, Loader2, Mic, Target, XCircle } from 'lucide-react';
import { ROLE_MAPPINGS } from '../../constants';

// Idle / start screen shown before the voice interview begins.
const StartCard = ({
  effectiveRole,
  onRoleChange,
  estimatedMinutes,
  highlights,
  resume,
  resumeFile,
  resumeText,
  resumeSummaryOpen,
  uploadingResume,
  resumeUploadError,
  resumableSession,
  resumeFileInputRef,
  onToggleResumeSummary,
  onResumeTextChange,
  onResumeFileChange,
  onClearResumeFile,
  onBegin,
}) => {
  const roles = Object.keys(ROLE_MAPPINGS);

  return (
    <div className="aii-start-card">
      <div className="aii-start-card__brand">
        <div className="aii-start-avatar">
          <span>J</span>
          <i />
        </div>
        <span className="aii-start-card__tag">Jack · Technical Interviewer</span>
      </div>
      <h2 className="aii-start-card__title">Technical Interview</h2>
      <p className="aii-start-card__sub">
        Jack will interview you like a senior technical reviewer — using your
        resume to ask focused questions, then probing deeper based on your
        answers and your code.
      </p>

      <div className="aii-start-card__badges" aria-label="Interview overview">
        {highlights.map((item) => (
          <span key={item.label} className="aii-pill">
            <span className="aii-pill__label">{item.label}</span>
            {item.value}
          </span>
        ))}
      </div>

      <div className="aii-start-card__details">
        <div className="aii-detail-item aii-detail-item--role">
          <span className="aii-detail-item__icon"><Target size="18" /></span>
          <div style={{ width: '100%', textAlign: 'left' }}>
            <strong>Target Role</strong>
            <select
              className="aii-role-select"
              value={effectiveRole}
              onChange={(e) => onRoleChange && onRoleChange(e.target.value)}
            >
              {roles.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="aii-detail-item">
          <span className="aii-detail-item__icon"><ListChecks size="18" /></span>
          <div>
            <strong>Questions</strong>
            <p>Adaptive</p>
          </div>
        </div>
        <div className="aii-detail-item">
          <span className="aii-detail-item__icon"><Clock size="18" /></span>
          <div>
            <strong>Duration</strong>
            <p>~{estimatedMinutes} minutes</p>
          </div>
        </div>
      </div>

      <div className="aii-start-card__tips">
        <div className="aii-start-card__tips-title">Before you begin</div>
        <ul>
          <li>Give concrete examples — Jack will follow up on the details that matter most.</li>
          <li>Speak clearly, keep your camera optional, and allow mic access when prompted.</li>
        </ul>
      </div>

      {resume && (
        <div className="aii-resume-preview">
          <div className="aii-resume-preview__header">
            <span>Resume snapshot</span>
            <button type="button" className="aii-link-button" onClick={onToggleResumeSummary}>
              {resumeSummaryOpen ? 'Hide' : 'Show'} summary
            </button>
          </div>
          {resumeSummaryOpen && (
            <div className="aii-resume-preview__content">
              {resume.parsed?.experience?.slice(0, 3).map((item, index) => (
                <div key={index} className="aii-resume-preview__item">
                  <strong>{item.position || item.title}</strong>
                  <span>{item.company || item.organization}</span>
                </div>
              ))}
              <p className="aii-resume-preview__note">Jack will use your resume to personalize questions.</p>
            </div>
          )}
        </div>
      )}

      <div className="aii-start-card__resume">
        <label>Upload your resume (PDF or TXT) so Jack can read it before starting</label>
        <div className={`aii-file-upload${resumeFile ? ' aii-file-upload--done' : ''}`}>
          <input
            ref={resumeFileInputRef}
            type="file"
            id="aii-resume-file"
            accept=".pdf,.txt"
            onChange={onResumeFileChange}
            disabled={uploadingResume}
          />
          <div className="aii-file-upload__hint">
            {uploadingResume ? (
              <><Loader2 className="aii-spin" size="18" /> Parsing resume…</>
            ) : resumeFile ? (
              <><CheckCircle2 size="18" /> {resumeFile.name} — Jack will use it for your interview.</>
            ) : (
              <>Drop your PDF here or <u>browse</u></>
            )}
          </div>
          {resumeFile && !uploadingResume && (
            <button type="button" className="aii-file-upload__remove" onClick={onClearResumeFile} aria-label="Remove resume file">
              <XCircle size="16" />
            </button>
          )}
        </div>
        {resumeUploadError && <p className="aii-form-error">{resumeUploadError}</p>}
      </div>

      <div className="aii-start-card__resume">
        <label htmlFor="aii-resume-text">Or paste your resume text (optional)</label>
        <textarea
          id="aii-resume-text"
          value={resumeText}
          onChange={onResumeTextChange}
          placeholder="Paste your resume text here so Jack can personalize questions to your background…"
          rows={5}
        />
      </div>

      {resumableSession && (
        <button
          className="aii-start-btn aii-start-btn--ghost"
          onClick={() => onBegin(true)}
        >
          <span>Resume Interview</span>
          <ArrowRight size="18" />
        </button>
      )}

      <button className="aii-start-btn" onClick={() => onBegin(false)}>
        <Mic size="18" />
        <span>{resumableSession ? 'Start New Interview' : 'Begin Interview'}</span>
        <ArrowRight size="18" />
      </button>
      <p className="aii-start-card__footnote">Make sure your microphone is allowed in the browser.</p>
    </div>
  );
};

export default StartCard;
