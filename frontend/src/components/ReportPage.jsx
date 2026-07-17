import React, { useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { jsPDF } from 'jspdf'
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

  const downloadPdf = () => {
    if (!report) return
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

    doc.save('Assessment_Report.pdf')
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
          <button className="btn primary" type="button" onClick={downloadPdf}>Download PDF</button>
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
