import React, { useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Download, Code2, MessageSquare } from 'lucide-react'
import { api } from '../api'
import { calculateInterviewScores } from '../proctoring/proctoringState'

function ReportPage({ state, proctoring }) {
  const [report, setReport] = useState(null)
  const [isGenerating, setIsGenerating] = useState(true)

  useEffect(() => {
    if (!state.sessionId) return
    const fetchReport = async () => {
      setIsGenerating(true)
      try {
        await api.post('/ai/feedback', { session_id: state.sessionId })
      } catch (err) {
        console.error("AI feedback generation failed", err)
      }
      try {
        const data = await api.get(`/report?session_id=${state.sessionId}`)
        setReport(data)
      } catch (err) {
        console.error("Failed to load report", err)
      }
      setIsGenerating(false)
    }
    fetchReport()
  }, [state.sessionId])

  const interviewScores = useMemo(() => {
    return calculateInterviewScores(proctoring?.interviewMetrics || {})
  }, [proctoring?.interviewMetrics])

  const liveInterviews = useMemo(() => {
    return report?.state?.liveInterview || {}
  }, [report?.state?.liveInterview])

  const downloadPdf = async () => {
    if (!report) return
    const { jsPDF } = await import('jspdf')
    const doc = new jsPDF()
    doc.setFontSize(20)
    doc.text('Assessment Report', 20, 20)
    doc.setFontSize(12)
    doc.text(`Candidate: ${report.candidateName || 'Unknown'}`, 20, 30)
    doc.text(`Company: ${report.selectedCompany || 'Unknown'}`, 20, 40)
    doc.text(`Overall Score: ${report.overallScore || 0}%`, 20, 50)

    doc.text(`Communication Score: ${interviewScores.communicationScore}%`, 20, 70)
    doc.text(`Confidence Score: ${interviewScores.confidenceScore}%`, 20, 80)
    doc.text(`Participation Score: ${interviewScores.participationScore}%`, 20, 90)

    // Add transcript if available
    let y = 110
    for (const [round, data] of Object.entries(liveInterviews)) {
      if (data.transcript?.length) {
        doc.setFontSize(14)
        doc.text(`${round.toUpperCase()} Interview Transcript`, 20, y)
        y += 10
        doc.setFontSize(10)
        for (const entry of data.transcript) {
          const role = entry.role === 'interviewer' ? 'Obi' : 'You'
          const lines = doc.splitTextToSize(`${role}: ${entry.text}`, 170)
          for (const line of lines) {
            if (y > 270) { doc.addPage(); y = 20 }
            doc.text(line, 20, y)
            y += 6
          }
          y += 4
        }
        if (data.codeReview) {
          doc.setFontSize(12)
          doc.text('Code Review:', 20, y)
          y += 8
          doc.setFontSize(10)
          const reviewLines = doc.splitTextToSize(data.codeReview, 170)
          for (const line of reviewLines) {
            if (y > 270) { doc.addPage(); y = 20 }
            doc.text(line, 20, y)
            y += 6
          }
        }
        y += 10
      }
    }

    doc.save('Assessment_Report.pdf')
  }

  const downloadTranscript = () => {
    let text = `Assessment Report\n${'='.repeat(40)}\n`
    text += `Candidate: ${report?.candidateName || 'Unknown'}\n`
    text += `Company: ${report?.selectedCompany || 'Unknown'}\n`
    text += `Overall Score: ${report?.overallScore || 0}%\n\n`

    for (const [round, data] of Object.entries(liveInterviews)) {
      text += `\n${round.toUpperCase()} Interview\n${'-'.repeat(30)}\n`
      if (data.transcript?.length) {
        for (const entry of data.transcript) {
          const role = entry.role === 'interviewer' ? 'Obi' : 'You'
          text += `\n[${role}]\n${entry.text}\n`
        }
      }
      if (data.codeReview) {
        text += `\n[Code Review]\n${data.codeReview}\n`
      }
      if (data.code) {
        text += `\n[Submitted Code - ${data.language}]\n${data.code}\n`
      }
    }

    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'Interview_Transcript.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!state.sessionId) return <Navigate to="/resume" replace />
  if (!state.company) return <Navigate to="/company" replace />

  return (
    <section className="panel main-panel report-panel">
      <div className="section-head">
        <div>
          <p className="eyebrow">Final report</p>
          <h2>Candidate readiness summary</h2>
          <p className="muted">A mock assessment dashboard showing round scores, strengths, remediation, and next steps.</p>
        </div>
        <div className="action-row compact">
          {Object.keys(liveInterviews).length > 0 && (
            <button className="btn ghost" type="button" onClick={downloadTranscript}>
              <Download size={14} /> Transcript
            </button>
          )}
          <button className="btn primary" type="button" onClick={downloadPdf}>
            <Download size={14} /> PDF
          </button>
        </div>
      </div>
      {report ? (
        <>
          <div className="report-grid">
            <div className="report-card summary-card">
              <span>Overall score</span>
              <h3>{report.overallScore}%</h3>
              <p>{report.feedback?.summary}</p>
            </div>
            <div className="report-card breakdown-card">
              <span>Interview Metrics</span>
              <ul>
                <li>
                  <div className="score-row"><strong>Communication</strong><span>{interviewScores.communicationScore}%</span></div>
                  <div className="score-bar"><div className="score-fill" style={{ width: `${interviewScores.communicationScore}%` }} /></div>
                </li>
                <li>
                  <div className="score-row"><strong>Confidence</strong><span>{interviewScores.confidenceScore}%</span></div>
                  <div className="score-bar"><div className="score-fill" style={{ width: `${interviewScores.confidenceScore}%` }} /></div>
                </li>
                <li>
                  <div className="score-row"><strong>Participation</strong><span>{interviewScores.participationScore}%</span></div>
                  <div className="score-bar"><div className="score-fill" style={{ width: `${interviewScores.participationScore}%` }} /></div>
                </li>
              </ul>
            </div>
            <div className="report-card breakdown-card">
              <span>Round breakdown</span>
              <ul>
                {Object.entries(report.breakdown || {}).map(([round, value]) => (
                  <li key={round}>
                    <div className="score-row"><strong>{round}</strong><span>{value}%</span></div>
                    <div className="score-bar"><div className="score-fill" style={{ width: `${value}%` }} /></div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="report-card notes-card">
              <span>Top insights</span>
              <h4>Strengths</h4>
              <ul>
                {(report.strengths || []).map((item, idx) => <li key={idx}>{item}</li>)}
              </ul>
              <h4>Areas to improve</h4>
              <ul>
                {(report.weaknesses || []).map((item, idx) => <li key={idx}>{item}</li>)}
              </ul>
            </div>
          </div>
          <div className="report-details">
            <div className="report-card full-card">
              <span>Recommendations</span>
              <ul>
                {(report.recommendations || []).map((item, idx) => <li key={idx}>{item}</li>)}
              </ul>
            </div>
          </div>

          {/* Live Interview Transcripts */}
          {Object.keys(liveInterviews).length > 0 && (
            <div className="report-details">
              <h3 className="transcript-section-title">
                <MessageSquare size={18} /> Interview Transcripts
              </h3>
              {Object.entries(liveInterviews).map(([round, data]) => (
                <div key={round} className="report-card transcript-card">
                  <div className="transcript-header">
                    <span className="transcript-round">{round}</span>
                    {data.language && <span className="transcript-lang"><Code2 size={12} /> {data.language}</span>}
                  </div>

                  {data.transcript?.length > 0 && (
                    <div className="transcript-chat">
                      {data.transcript.map((entry, i) => (
                        <div key={i} className={`transcript-entry ${entry.role}`}>
                          <strong>{entry.role === 'interviewer' ? '🤖 Obi' : '👤 You'}</strong>
                          <p>{entry.text}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {data.codeReview && (
                    <div className="transcript-review">
                      <h4>📝 Code Review</h4>
                      <pre>{data.codeReview}</pre>
                    </div>
                  )}

                  {data.code && (
                    <div className="transcript-code">
                      <h4>💻 Submitted Code</h4>
                      <pre>{data.code}</pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="empty-state">
          <b>{isGenerating ? "Generating AI Feedback..." : "Loading report..."}</b>
          <p>{isGenerating ? "Analyzing your interview answers..." : "Your performance summary will appear here shortly."}</p>
        </div>
      )}
    </section>
  )
}

export { ReportPage }
