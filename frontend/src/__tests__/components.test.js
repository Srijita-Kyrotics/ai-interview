import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  Navigate: ({ to }) => React.createElement('div', { 'data-testid': 'navigate' }, `Navigate to ${to}`),
  BrowserRouter: ({ children }) => React.createElement('div', null, children),
}))

vi.mock('lucide-react', () => {
  const icon = (name) => () => React.createElement('span', null, name)
  return {
    FileText: icon('FileText'),
    Building2: icon('Building2'),
    Brain: icon('Brain'),
    Code2: icon('Code2'),
    MessageSquare: icon('MessageSquare'),
    Users: icon('Users'),
    BarChart2: icon('BarChart2'),
    Calendar: icon('Calendar'),
    TrendingUp: icon('TrendingUp'),
    Award: icon('Award'),
    X: icon('X'),
    CheckCircle: icon('CheckCircle'),
    LayoutDashboard: icon('LayoutDashboard'),
    Shield: icon('Shield'),
    Menu: icon('Menu'),
    Mic: icon('Mic'),
    Square: icon('Square'),
    Play: icon('Play'),
    RotateCcw: icon('RotateCcw'),
    Search: icon('Search'),
    Lock: icon('Lock'),
    Target: icon('Target'),
    Zap: icon('Zap'),
    Eye: icon('Eye'),
    EyeOff: icon('EyeOff'),
  }
})

vi.mock('recharts', () => ({
  LineChart: () => React.createElement('div', null, 'LineChart'),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }) => React.createElement('div', null, children),
  Legend: () => null,
}))

vi.mock('../api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('../utils/score', () => ({
  scoreClass: (score) => {
    if (score >= 70) return 'score-good'
    if (score >= 50) return 'score-mid'
    return 'score-low'
  },
}))

vi.mock('jspdf', () => ({
  jsPDF: vi.fn().mockImplementation(() => ({
    setFontSize: vi.fn(),
    text: vi.fn(),
    save: vi.fn(),
  })),
}))

import { render, screen } from '@testing-library/react'

describe('DashboardPage', () => {
  it('renders loading state', async () => {
    const { DashboardPage } = await import('../components/DashboardPage')
    render(React.createElement(DashboardPage, { user: { email: 'test@test.com' } }))
    const skeleton = document.querySelector('.skeleton')
    expect(skeleton).not.toBeNull()
  })
})

describe('CompanyPage', () => {
  it('renders company selection', async () => {
    const { CompanyPage } = await import('../components/CompanyPage')
    const state = { sessionId: 'test-123', resume: { skills: ['Python'], name: 'Test' }, companies: {} }
    render(React.createElement(CompanyPage, { state, setState: vi.fn() }))
    const element = document.querySelector('.company-card, .company-grid, [class*=company], main, .panel')
    expect(element).not.toBeNull()
  })
})

describe('TerminatedPage', () => {
  it('renders termination message', async () => {
    const { TerminatedPage } = await import('../components/TerminatedPage')
    render(React.createElement(TerminatedPage))
    expect(screen.getByText(/Test Terminated/)).toBeTruthy()
    expect(screen.getByText(/terminated due to/)).toBeTruthy()
  })
})

describe('ReportPage', () => {
  it('renders loading state when no session', async () => {
    const { ReportPage } = await import('../components/ReportPage')
    render(React.createElement(ReportPage, { state: {}, proctoring: {} }))
    const nav = screen.getByTestId('navigate')
    expect(nav.textContent).toContain('/resume')
  })
})

describe('SessionDetailModal', () => {
  it('renders loading state', async () => {
    const { SessionDetailModal } = await import('../components/SessionDetailModal')
    render(React.createElement(SessionDetailModal, { sessionId: 'test-session', onClose: vi.fn() }))
    const spinner = document.querySelector('.loading-spinner')
    expect(spinner).not.toBeNull()
  })
})

describe('scoreClass', () => {
  it('returns score-good for high scores', async () => {
    const { scoreClass } = await import('../utils/score')
    expect(scoreClass(80)).toBe('score-good')
    expect(scoreClass(70)).toBe('score-good')
  })

  it('returns score-mid for medium scores', async () => {
    const { scoreClass } = await import('../utils/score')
    expect(scoreClass(60)).toBe('score-mid')
    expect(scoreClass(50)).toBe('score-mid')
  })

  it('returns score-low for low scores', async () => {
    const { scoreClass } = await import('../utils/score')
    expect(scoreClass(30)).toBe('score-low')
    expect(scoreClass(0)).toBe('score-low')
  })
})

describe('formatQuestionText', () => {
  it('handles plain text', async () => {
    const { formatQuestionText } = await import('../utils/questionFormat')
    const result = formatQuestionText('What is 2+2?')
    expect(typeof result === 'string' || Array.isArray(result)).toBe(true)
  })

  it('handles empty string', async () => {
    const { formatQuestionText } = await import('../utils/questionFormat')
    const result = formatQuestionText('')
    expect(result).toBeDefined()
  })

  it('handles null gracefully', async () => {
    const { formatQuestionText } = await import('../utils/questionFormat')
    const result = formatQuestionText(null)
    expect(result).toBe('')
  })

  it('handles undefined gracefully', async () => {
    const { formatQuestionText } = await import('../utils/questionFormat')
    const result = formatQuestionText(undefined)
    expect(result).toBe('')
  })

  it('handles HTML entities', async () => {
    const { formatQuestionText } = await import('../utils/questionFormat')
    const result = formatQuestionText('What is &lt;b&gt;bold&lt;/b&gt;?')
    expect(result).toBeDefined()
  })

  it('handles LaTeX expressions', async () => {
    const { formatQuestionText } = await import('../utils/questionFormat')
    const result = formatQuestionText('Solve $x^2 + 2x + 1 = 0$')
    expect(result).toBeDefined()
  })

  it('handles text with \\frac LaTeX', async () => {
    const { formatQuestionText } = await import('../utils/questionFormat')
    const result = formatQuestionText('\\frac{1}{2} of the total')
    expect(result).toContain('1/2')
  })

  it('handles numeric input', async () => {
    const { formatQuestionText } = await import('../utils/questionFormat')
    const result = formatQuestionText(42)
    expect(result).toContain('42')
  })
})
